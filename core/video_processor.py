import os
import asyncio
import logging
import subprocess
import imageio_ffmpeg
import edge_tts
from pathlib import Path
from config.settings import FINAL_DIR, TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS
from core.db import DatabaseManager, JobStatus

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Handles TTS Audio generation, Subtitles, and FFmpeg video merging/scaling to 9:16 format"""

    def __init__(self, voice: str = "vi-VN-HoaiMyNeural"):
        self.voice = voice
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    def concat_videos(self, video_paths: list, output_path: Path) -> bool:
        """Concatenate multiple 9:16 MP4 video files into a single long combined video using FFmpeg"""
        if not video_paths:
            return False

        txt_file = output_path.with_suffix(".txt")
        try:
            with open(txt_file, "w", encoding="utf-8") as f:
                for vp in video_paths:
                    escaped_path = str(vp).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                self.ffmpeg_exe, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(txt_file),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "192k",
                str(output_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            if txt_file.exists():
                txt_file.unlink(missing_ok=True)
            return output_path.exists()
        except Exception as e:
            logger.error(f"Lỗi ghép nối video FFmpeg: {e}")
            if txt_file.exists():
                txt_file.unlink(missing_ok=True)
            return False

    def generate_fallback_audio(self, output_mp3: Path, duration_sec: float = 10.0) -> bool:
        """Generate silent audio track if TTS fails"""
        cmd = [
            self.ffmpeg_exe, "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration_sec),
            "-c:a", "libmp3lame",
            str(output_mp3)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return output_mp3.exists()
        except Exception:
            return False

    def generate_tts_sync(self, text: str, output_mp3: Path, voice: str = None) -> bool:
        """Synchronous wrapper for Edge-TTS audio generation with fallback"""
        target_voice = voice or self.voice
        async def _gen():
            communicate = edge_tts.Communicate(text, target_voice)
            await communicate.save(str(output_mp3))

        try:
            asyncio.run(_gen())
            if output_mp3.exists():
                return True
            return self.generate_fallback_audio(output_mp3)
        except Exception as e:
            logger.warning(f"Lỗi tạo giọng đọc TTS ({e}), chuyển sang fallback silent audio...")
            return self.generate_fallback_audio(output_mp3)

    def create_srt_subtitles(self, text: str, srt_path: Path, duration_sec: float = 10.0):
        """Create simple synchronized SRT subtitles split by phrases"""
        words = text.split()
        if not words:
            words = ["Video", "Shorts", "AI", "2026"]

        chunk_size = 4
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        chunk_duration = duration_sec / max(len(chunks), 1)

        srt_content = ""
        for idx, chunk in enumerate(chunks):
            start_t = idx * chunk_duration
            end_t = (idx + 1) * chunk_duration

            start_str = f"00:00:{int(start_t):02d},{int((start_t % 1) * 1000):03d}"
            end_str = f"00:00:{int(end_t):02d},{int((end_t % 1) * 1000):03d}"

            srt_content += f"{idx + 1}\n{start_str} --> {end_str}\n{chunk}\n\n"

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

    def merge_video_audio_subtitles(self, raw_video: Path, audio_mp3, srt_path, final_out: Path) -> bool:
        """Scale video to 1080x1920, optionally replace audio and/or burn subtitles"""
        try:
            # Build video filter chain
            scale_crop = (
                f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}"
            )
            if srt_path and Path(srt_path).exists():
                try:
                    srt_escaped = os.path.relpath(Path(srt_path), Path.cwd()).replace("\\", "/").replace(":", "\\:")
                except Exception:
                    srt_escaped = str(Path(srt_path).resolve()).replace("\\", "/").replace(":", "\\:")
                vf_filter = (
                    scale_crop +
                    f",subtitles='{srt_escaped}':force_style='FontName=Arial,FontSize=20,"
                    f"PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=60'"
                )
            else:
                vf_filter = scale_crop

            # Build FFmpeg command
            if audio_mp3 and Path(audio_mp3).exists():
                # Replace audio with TTS voiceover
                cmd = [
                    self.ffmpeg_exe, "-y",
                    "-i", str(raw_video),
                    "-i", str(audio_mp3),
                    "-vf", vf_filter,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    "-r", str(TARGET_FPS),
                    str(final_out)
                ]
            else:
                # Keep original video audio (no TTS replacement)
                cmd = [
                    self.ffmpeg_exe, "-y",
                    "-i", str(raw_video),
                    "-vf", vf_filter,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "192k",
                    "-r", str(TARGET_FPS),
                    str(final_out)
                ]

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            return final_out.exists()
        except subprocess.CalledProcessError as cpe:
            logger.error(f"FFmpeg render failed: {cpe.stderr.decode('utf-8', errors='ignore')}")
            # Fallback: simple render without subtitle filter
            try:
                if audio_mp3 and Path(audio_mp3).exists():
                    cmd_simple = [
                        self.ffmpeg_exe, "-y",
                        "-stream_loop", "-1",
                        "-i", str(raw_video),
                        "-i", str(audio_mp3),
                        "-vf", scale_crop,
                        "-c:v", "libx264", "-preset", "fast",
                        "-c:a", "aac", "-shortest",
                        "-r", str(TARGET_FPS),
                        str(final_out)
                    ]
                else:
                    cmd_simple = [
                        self.ffmpeg_exe, "-y",
                        "-i", str(raw_video),
                        "-vf", scale_crop,
                        "-c:v", "libx264", "-preset", "fast",
                        "-c:a", "aac",
                        "-r", str(TARGET_FPS),
                        str(final_out)
                    ]
                subprocess.run(cmd_simple, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return final_out.exists()
            except Exception:
                return False
        except Exception as e:
            logger.error(f"Lỗi ghép video FFmpeg: {e}")
            return False

    def process_render_job(self, job_id: int):
        """Worker function: Process VEO_DONE job -> TTS audio -> FFmpeg 9:16 final render"""
        db = DatabaseManager()
        job = db.get_job(job_id)
        if not job or job['status'] != JobStatus.VEO_DONE.value:
            return

        try:
            db.update_job(job_id, status=JobStatus.PROCESSING_FFMPEG.value)
            raw_video_path = Path(job['video_raw_path'])
            if not raw_video_path.exists():
                db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="File video raw không tồn tại")
                return

            add_voiceover = bool(job.get('add_voiceover', 1))
            add_subtitle = bool(job.get('add_subtitle', 1))

            audio_mp3 = FINAL_DIR / f"voice_{job_id}.mp3"
            srt_path = FINAL_DIR / f"sub_{job_id}.srt"
            final_video = FINAL_DIR / f"final_{job_id}.mp4"

            job_voice = job.get('voice') or self.voice

            if add_voiceover:
                text_to_speak = job['voiceover_text'] or job['title'] or "Video ngắn ấn tượng năm 2026"
                logger.info(f"Đang sinh giọng đọc TTS ({job_voice}) cho Job #{job_id}")
                self.generate_tts_sync(text_to_speak, audio_mp3, voice=job_voice)
            else:
                # No voiceover — generate silent placeholder audio so FFmpeg doesn't fail
                logger.info(f"Bỏ qua TTS, dùng âm thanh gốc cho Job #{job_id}")
                audio_mp3 = None  # Signal to merge function to keep original audio

            if add_subtitle and add_voiceover:
                text_to_speak = job['voiceover_text'] or job['title'] or ""
                self.create_srt_subtitles(text_to_speak, srt_path)
            else:
                srt_path = None  # No subtitle

            logger.info(f"Đang render FFmpeg 9:16 cho Job #{job_id} | voice={add_voiceover} | sub={add_subtitle}")
            success = self.merge_video_audio_subtitles(raw_video_path, audio_mp3, srt_path, final_video)

            if success and final_video.exists():
                db.update_job(
                    job_id,
                    audio_path=str(audio_mp3) if audio_mp3 else None,
                    video_final_path=str(final_video),
                    status=JobStatus.READY_TO_POST.value
                )
            else:
                db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="Lỗi render FFmpeg")

        except Exception as e:
            logger.exception(f"Lỗi xử lý render video Job #{job_id}: {e}")
            db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))

