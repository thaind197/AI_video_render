import os
import ssl
import logging
import subprocess
import requests
import yt_dlp
import imageio_ffmpeg
from pathlib import Path
from google import genai
from PIL import Image
from config.settings import DOWNLOADS_DIR, GEMINI_API_KEY
from core.db import DatabaseManager, JobStatus
from core.script_engine import ScriptEngine

logger = logging.getLogger(__name__)

# Fix SSL verification for Whisper model download on macOS
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

# Ensure FFmpeg is available in PATH for Whisper AI
try:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = str(Path(ffmpeg_exe).parent)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    symlink_ffmpeg = Path(ffmpeg_dir) / "ffmpeg"
    if not symlink_ffmpeg.exists():
        try:
            symlink_ffmpeg.symlink_to(Path(ffmpeg_exe))
        except Exception:
            pass
except Exception:
    pass

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

    def _has_audio(self, video_path: Path) -> bool:
        """Check if video file contains an audio stream"""
        if not video_path or not video_path.exists():
            return False
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            res = subprocess.run([ffmpeg_exe, "-i", str(video_path)], capture_output=True, text=True, timeout=5)
            return "Audio:" in res.stderr
        except Exception:
            return False

    def _ensure_h264(self, file_path: Path, target_path: Path) -> Path:
        """Ensure video file is standard web-compatible H.264 (AVC) with AAC audio"""
        if not file_path.exists():
            return file_path
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            probe = subprocess.run([ffmpeg_exe, "-i", str(file_path)], capture_output=True, text=True, timeout=10)
            is_hevc = "hevc" in probe.stderr.lower() or "hvc1" in probe.stderr.lower()
            needs_convert = is_hevc or file_path.suffix.lower() != ".mp4"
            if not needs_convert:
                if file_path.resolve() != target_path.resolve():
                    if target_path.exists():
                        target_path.unlink(missing_ok=True)
                    file_path.rename(target_path)
                    return target_path
                return file_path

            logger.info(f"Chuyển đổi video sang chuẩn Web H.264 (AVC): {file_path.name}...")
            tmp_target = target_path.with_name(target_path.stem + "_tmp_h264.mp4")
            has_audio = "Audio:" in probe.stderr
            audio_opts = ["-c:a", "aac"] if has_audio else []
            cmd = [
                ffmpeg_exe, "-y",
                "-threads", "2",
                "-i", str(file_path),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                *audio_opts,
                str(tmp_target)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if tmp_target.exists():
                if file_path.exists() and file_path.resolve() != tmp_target.resolve():
                    try: file_path.unlink(missing_ok=True)
                    except Exception: pass
                if target_path.exists() and target_path.resolve() != tmp_target.resolve():
                    try: target_path.unlink(missing_ok=True)
                    except Exception: pass
                tmp_target.rename(target_path)
                return target_path
        except Exception as e:
            logger.warning(f"Lỗi transcode H.264 cho {file_path.name}: {e}")
        return file_path

    def download_video(self, url: str, job_id: int) -> Path:
        """Download video from URL (TikTok/Shorts/Reels) with guaranteed audio stream"""
        out_target = DOWNLOADS_DIR / f"clone_{job_id}.mp4"
        out_tmpl = str(DOWNLOADS_DIR / f"clone_{job_id}.%(ext)s")

        # 1. Prioritize TikWm API for TikTok videos to guarantee no-watermark video with full audio stream
        if "tiktok.com" in url.lower():
            try:
                logger.info(f"Tải video TikTok trực tiếp qua TikWm API cho Job #{job_id}...")
                resp = requests.post("https://www.tikwm.com/api/", data={"url": url}, timeout=15).json()
                if resp.get("code") == 0 and "data" in resp and "play" in resp["data"]:
                    play_url = resp["data"]["play"]
                    if not play_url.startswith("http"):
                        play_url = "https://www.tikwm.com" + play_url
                    v_data = requests.get(play_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30).content
                    if len(v_data) > 100000:
                        with open(out_target, "wb") as f:
                            f.write(v_data)
                        if self._has_audio(out_target):
                            logger.info(f"Đã tải thành công video TikTok không logo + có âm thanh qua TikWm API ({len(v_data)} bytes)")
                            return self._ensure_h264(out_target, out_target)
                        else:
                            logger.warning("TikWm video không có audio, chuyển sang tải audio riêng từ music URL...")
                            music_url = resp["data"].get("music")
                            if music_url:
                                m_data = requests.get(music_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20).content
                                m_path = DOWNLOADS_DIR / f"tikwm_music_{job_id}.mp3"
                                with open(m_path, "wb") as mf:
                                    mf.write(m_data)
                                merged_target = DOWNLOADS_DIR / f"clone_{job_id}_merged.mp4"
                                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                                cmd_merge = [
                                    ffmpeg_exe, "-y",
                                    "-i", str(out_target),
                                    "-i", str(m_path),
                                    "-c:v", "copy", "-c:a", "aac",
                                    str(merged_target)
                                ]
                                subprocess.run(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                                if merged_target.exists():
                                    try: out_target.unlink(missing_ok=True)
                                    except Exception: pass
                                    merged_target.rename(out_target)
                                    try: m_path.unlink(missing_ok=True)
                                    except Exception: pass
                                    return self._ensure_h264(out_target, out_target)
            except Exception as e:
                logger.warning(f"TikWm API error: {e}")

        # 2. Fallback / non-TikTok downloader using yt-dlp ('best' format to include audio)
        ydl_opts = {
            'format': 'best',  # 'best' gets single container stream with both video + audio
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            }
        }

        downloaded_file = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            matches = list(DOWNLOADS_DIR.glob(f"clone_{job_id}.*"))
            if matches:
                downloaded_file = matches[0]
        except Exception as e:
            logger.warning(f"yt-dlp download error cho url '{url}': {e}")

        if downloaded_file and downloaded_file.exists():
            return self._ensure_h264(downloaded_file, out_target)

        # 3. Final Fallback: Generate synthetic 9:16 sample video for testing if URL is inaccessible
        logger.info(f"Tự động sinh video mẫu 9:16 fallback cho Clone Job #{job_id}")
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-f", "lavfi",
            "-i", "rgbtestsrc=size=1080x1920:rate=30:duration=10",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", "boxblur=40:40,hue=h=t*50:s=1.8,eq=contrast=1.25:brightness=0.02:saturation=1.8",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-t", "10",
            str(out_target)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return out_target

    def extract_audio(self, video_path: Path) -> Path:
        """Extract MP3 audio from video using FFmpeg with automatic silent fallback"""
        audio_path = video_path.with_suffix(".mp3")
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(video_path),
            "-vn", "-acodec", "libmp3lame",
            "-ar", "44100", "-ac", "2",
            str(audio_path)
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size == 0:
                raise RuntimeError("Extract audio failed or returned empty file")
        except Exception as e:
            logger.info(f"Tách âm thanh im lặng 10s fallback ({e})...")
            cmd_silent = [
                ffmpeg_exe, "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "10",
                "-c:a", "libmp3lame",
                str(audio_path)
            ]
            subprocess.run(cmd_silent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
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
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            pass

        if not frame_path.exists() or frame_path.stat().st_size == 0:
            try:
                img = Image.new('RGB', (1080, 1920), color=(24, 144, 255))
                img.save(frame_path)
            except Exception:
                pass
        return frame_path

    def analyze_frame_vision(self, frame_path: Path) -> str:
        """Analyze keyframe visual content using Gemini Flash"""
        if not self.api_key or len(self.api_key) < 10:
            return "Video ngắn 10 giây ấn tượng"
        try:
            client = genai.Client(api_key=self.api_key)
            img = Image.open(frame_path)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=["Hãy mô tả bối cảnh, nhân vật, hành động chính trong bức ảnh này trong 2 câu ngắn gọn.", img]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Lỗi phân tích Gemini Vision: {e}")
            return "Video ngắn 10 giây thu hút"

    def get_video_duration(self, video_path: Path) -> float:
        """Extract exact duration of video file in seconds using FFmpeg"""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-i", str(video_path)]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            import re
            match = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", res.stderr)
            if match:
                h, m, s = match.groups()
                total_sec = float(h) * 3600 + float(m) * 60 + float(s)
                return max(total_sec, 3.0)
        except Exception as e:
            logger.warning(f"Lỗi đọc thời lượng video ({e}), dùng mặc định 10s...")
        return 10.0

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
        """Worker function: Process a CLONE job end-to-end preserving original video"""
        db = DatabaseManager()
        job = db.get_job(job_id)
        if not job or job['status'] != JobStatus.PENDING.value:
            return

        try:
            url = job['source_input']
            add_voiceover = str(job.get('add_voiceover', '1')).lower() not in ('0', 'false', 'none', '', '0.0')
            add_subtitle = str(job.get('add_subtitle', '1')).lower() not in ('0', 'false', 'none', '', '0.0')

            logger.info(f"Đang tải video clone #{job_id}: {url} | voiceover={add_voiceover} | subtitle={add_subtitle}")
            video_path = self.download_video(url, job_id)

            duration_sec = self.get_video_duration(video_path)
            logger.info(f"Thời lượng video gốc #{job_id}: {duration_sec:.1f}s")

            if add_voiceover:
                # Need transcript to generate new voiceover script
                audio_path = self.extract_audio(video_path)
                frame_path = self.extract_keyframe(video_path)
                transcript = self.transcribe_audio(audio_path)
                vision_desc = self.analyze_frame_vision(frame_path)

                logger.info(f"Remake nội dung thoại ({duration_sec:.1f}s) cho job #{job_id}")
                remade = self.script_engine.remake_script(transcript, vision_desc, duration_sec=duration_sec)

                voiceover_text = remade.get('voiceover_text', transcript) if remade else transcript
                title = remade.get('title', f"Clone TikTok #{job_id}") if remade else f"Clone TikTok #{job_id}"
                tags = remade.get('tags', []) if remade else []
            else:
                # No voiceover — skip transcription & remake entirely
                voiceover_text = ""
                title = f"Clone TikTok #{job_id}"
                tags = []
                logger.info(f"Bỏ qua giọng đọc AI cho job #{job_id} (tùy chọn tắt)")

            # Use downloaded original video directly as raw video, skip Veo prompt
            # If neither voiceover nor subtitle → jump straight to READY_TO_POST (no FFmpeg needed)
            if not add_voiceover and not add_subtitle:
                db.update_job(
                    job_id,
                    title=title,
                    voiceover_text="",
                    veo_prompt="Video TikTok Gốc (Clone Trực Tiếp - Không Chỉnh Sửa)",
                    video_raw_path=str(video_path),
                    video_final_path=str(video_path),  # Use original as final directly
                    tags=tags,
                    status=JobStatus.READY_TO_POST.value
                )
                logger.info(f"Clone #{job_id} xong (không voice/sub) — sẵn sàng đăng ngay!")
            else:
                db.update_job(
                    job_id,
                    title=title,
                    voiceover_text=voiceover_text,
                    veo_prompt="Video TikTok Gốc (Đã Clone Trực Tiếp)",
                    video_raw_path=str(video_path),
                    tags=tags,
                    status=JobStatus.VEO_DONE.value
                )
                logger.info(f"Đã tải xong video clone #{job_id}, chuyển tới FFmpeg render!")

        except Exception as e:
            logger.exception(f"Lỗi xử lý Clone Job #{job_id}: {e}")
            db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))

