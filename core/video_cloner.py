import os
import logging
import subprocess
import yt_dlp
import imageio_ffmpeg
from pathlib import Path
from google import genai
from PIL import Image
from config.settings import DOWNLOADS_DIR, GEMINI_API_KEY
from core.db import DatabaseManager, JobStatus
from core.script_engine import ScriptEngine

logger = logging.getLogger(__name__)

# Try import Whisper AI with graceful fallback
try:
    import whisper
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    logger.warning("Thư viện openai-whisper chưa cài đặt, sẽ dùng fallback transcription.")

class VideoCloner:
    """Downloads TikTok/Reels video, transcribes audio, analyzes visual, and remakes script"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.script_engine = ScriptEngine(self.api_key)
        self._whisper_model = None

    def _get_whisper(self):
        if HAS_WHISPER and self._whisper_model is None:
            try:
                self._whisper_model = whisper.load_model("base")
            except Exception as e:
                logger.error(f"Lỗi nạp Whisper model: {e}")
                self._whisper_model = None
        return self._whisper_model

    def download_video(self, url: str, job_id: int) -> Path:
        """Download video from URL using yt-dlp"""
        out_path = DOWNLOADS_DIR / f"clone_{job_id}.mp4"
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(out_path),
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return out_path

    def extract_audio(self, video_path: Path) -> Path:
        """Extract MP3 audio from video using FFmpeg"""
        audio_path = video_path.with_suffix(".mp3")
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(video_path),
            "-vn", "-acodec", "libmp3lame",
            "-ar", "44100", "-ac", "2",
            str(audio_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return audio_path

    def extract_keyframe(self, video_path: Path) -> Path:
        """Extract keyframe at 1s for Gemini Vision analysis"""
        frame_path = video_path.with_suffix(".jpg")
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", "00:00:01",
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(frame_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return frame_path

    def analyze_frame_vision(self, frame_path: Path) -> str:
        """Analyze keyframe visual content using Gemini 1.5 Flash"""
        if not self.api_key:
            return "Video ngắn ấn tượng"
        try:
            client = genai.Client(api_key=self.api_key)
            img = Image.open(frame_path)
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=["Hãy mô tả bối cảnh, nhân vật, hành động chính trong bức ảnh này trong 2 câu ngắn gọn.", img]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Lỗi phân tích Gemini Vision: {e}")
            return "Video ngắn 10 giây thu hút"

    def transcribe_audio(self, audio_path: Path) -> str:
        """Transcribe audio using Whisper AI or fallback"""
        if HAS_WHISPER:
            try:
                model = self._get_whisper()
                if model:
                    result = model.transcribe(str(audio_path))
                    return result.get("text", "").strip()
            except Exception as e:
                logger.error(f"Lỗi Whisper transcription: {e}")
        return "Video xu hướng ngắn 10 giây với thông điệp hấp dẫn"

    def process_clone_job(self, job_id: int):
        """Worker function: Process a CLONE job end-to-end"""
        db = DatabaseManager()
        job = db.get_job(job_id)
        if not job or job['status'] != JobStatus.PENDING.value:
            return

        try:
            url = job['source_input']
            logger.info(f"Đang tải video clone #{job_id}: {url}")
            video_path = self.download_video(url, job_id)

            logger.info(f"Tách âm thanh & hình ảnh #{job_id}")
            audio_path = self.extract_audio(video_path)
            frame_path = self.extract_keyframe(video_path)

            transcript = self.transcribe_audio(audio_path)
            vision_desc = self.analyze_frame_vision(frame_path)

            logger.info(f"Remake kịch bản mới cho job #{job_id}")
            remade = self.script_engine.remake_script(transcript, vision_desc)

            if remade:
                db.update_job(
                    job_id,
                    title=remade.get('title', 'Video Clone Remake'),
                    voiceover_text=remade.get('voiceover_text', ''),
                    veo_prompt=remade.get('veo_prompt', ''),
                    tags=remade.get('tags', []),
                    status=JobStatus.SCRIPTED.value
                )
            else:
                db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="Không remake được kịch bản")
        except Exception as e:
            logger.exception(f"Lỗi xử lý Clone Job #{job_id}: {e}")
            db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))
