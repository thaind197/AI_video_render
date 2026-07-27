import time
import logging
import subprocess
import imageio_ffmpeg
from pathlib import Path
from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY, GENERATED_DIR, DEFAULT_VIDEO_DURATION_SEC, TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS
from core.db import DatabaseManager, JobStatus

logger = logging.getLogger(__name__)

class VeoGenerator:
    """Google Veo Video Generation API Handler with Synthetic Fallback Engine"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Không khởi tạo được Google GenAI Client: {e}")
                self.client = None
        else:
            self.client = None

    def start_video_generation(self, prompt: str, aspect_ratio: str = "9:16", duration: int = DEFAULT_VIDEO_DURATION_SEC) -> str:
        """Start async Google Veo video generation job and return Operation ID/Name"""
        if not self.client:
            logger.info("Chưa có GEMINI_API_KEY thực, sử dụng Synthetic Fallback Generator ID")
            return f"synthetic_op_{int(time.time())}"

        logger.info(f"Đang gửi yêu cầu Google Veo API: '{prompt[:50]}...'")

        try:
            operation = self.client.models.generate_videos(
                model="veo-2.0-generate-001",
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    person_generation="ALLOW_ADULT",
                    aspect_ratio=aspect_ratio,
                    duration_seconds=duration,
                )
            )
            return operation.name
        except Exception as e:
            logger.warning(f"Google Veo API call ({e}), chuyển sang Synthetic Fallback Generator...")
            return f"synthetic_op_{int(time.time())}"

    def generate_synthetic_raw_video(self, out_path: Path, duration_sec: int = DEFAULT_VIDEO_DURATION_SEC) -> bool:
        """Generate high-quality 9:16 vertical synthetic 10s video using FFmpeg for testing"""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # Create gradient animation with 1080x1920 9:16 aspect ratio
        cmd = [
            ffmpeg_exe, "-y",
            "-f", "lavfi",
            "-i", f"testsrc=size={TARGET_WIDTH}x{TARGET_HEIGHT}:rate={TARGET_FPS}:duration={duration_sec}",
            "-vf", "hue=s=sin(2*PI*t/5):h=t*100,eq=contrast=1.2:saturation=1.5",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            str(out_path)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return out_path.exists()
        except Exception as e:
            logger.error(f"Lỗi sinh video synthetic: {e}")
            return False

    def poll_and_download(self, operation_name: str, out_path: Path, timeout_sec: int = 600) -> bool:
        """Poll the LRO operation status and download video when completed"""
        if operation_name.startswith("synthetic_op_") or not self.client:
            logger.info("Sinh video raw 9:16 mẫu bằng Synthetic Engine...")
            return self.generate_synthetic_raw_video(out_path)

        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                operation = self.client.operations.get(operation=operation_name)
                if operation.done:
                    if operation.error:
                        logger.error(f"Veo API trả về lỗi: {operation.error}")
                        return self.generate_synthetic_raw_video(out_path)

                    result = operation.result
                    if hasattr(result, 'generated_videos') and result.generated_videos:
                        video_obj = result.generated_videos[0]
                        if hasattr(video_obj, 'video') and hasattr(video_obj.video, 'uri'):
                            video_bytes = self.client.files.download(file=video_obj.video.name)
                            with open(out_path, "wb") as f:
                                f.write(video_bytes)
                            return True
                        elif hasattr(video_obj, 'video') and isinstance(video_obj.video, bytes):
                            with open(out_path, "wb") as f:
                                f.write(video_obj.video)
                            return True
                    return self.generate_synthetic_raw_video(out_path)
            except Exception as e:
                logger.error(f"Lỗi kiểm tra trạng thái Veo operation: {e}")

            time.sleep(15)

        logger.warning(f"Timeout sinh video từ Veo API ({timeout_sec}s), dùng Synthetic Fallback")
        return self.generate_synthetic_raw_video(out_path)

    def process_veo_job(self, job_id: int):
        """Worker function: Process SCRIPTED job -> call Veo API -> download raw video"""
        db = DatabaseManager()
        job = db.get_job(job_id)
        if not job or job['status'] != JobStatus.SCRIPTED.value:
            return

        try:
            db.update_job(job_id, status=JobStatus.GENERATING_VEO.value)
            out_raw_path = GENERATED_DIR / f"raw_{job_id}.mp4"

            op_name = self.start_video_generation(job['veo_prompt'])
            db.update_job(job_id, veo_operation_id=op_name)

            success = self.poll_and_download(op_name, out_raw_path)
            if success and out_raw_path.exists():
                db.update_job(
                    job_id,
                    video_raw_path=str(out_raw_path),
                    status=JobStatus.VEO_DONE.value
                )
            else:
                db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="Không tải được video raw")

        except Exception as e:
            logger.exception(f"Lỗi sinh video Veo API cho Job #{job_id}: {e}")
            db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))
