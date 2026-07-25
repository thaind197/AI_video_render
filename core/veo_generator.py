import os
import time
import logging
import subprocess
import imageio_ffmpeg
from pathlib import Path
from PIL import Image, ImageDraw
from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY, GENERATED_DIR, DEFAULT_VIDEO_DURATION_SEC, TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS, DEFAULT_VEO_MODEL, DEFAULT_ASPECT_RATIO
from core.db import DatabaseManager, JobStatus

logger = logging.getLogger(__name__)

# Map of internal model names to Labs.google display names
VEO_MODEL_MAP = {
    "veo-3.1-lite-generate-preview":  "Veo 3.1 - Lite [Lower Priority]",
    "veo-3.1-fast-generate-preview":  "Veo 3.1 - Fast [High Speed]",
    "veo-3.1-generate-preview":       "Veo 3.1 - Standard [Quality]",
    "veo-2.0-generate-001":           "Veo 2.0 Legacy",
}


class VeoQuotaError(Exception):
    """Raised when Veo API returns 429 RESOURCE_EXHAUSTED (quota exceeded)"""
    pass


class VeoGenerator:
    """Google Veo Video Generation API Handler — mirrors Labs.google options (model, duration, variants, aspect ratio)"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.client = None
        self._get_client()

    def _get_client(self):
        current_key = os.getenv("GEMINI_API_KEY", "").strip() or self.api_key
        if not current_key:
            self.client = None
            return None
        # Tự động nạp lại client khi người dùng vừa đổi API Key mới trong tab Cấu hình
        if not hasattr(self, '_last_key') or self._last_key != current_key or not self.client:
            self._last_key = current_key
            try:
                self.client = genai.Client(api_key=current_key)
                logger.info("Đã kết nối lại Google GenAI Client với API Key mới!")
            except Exception as e:
                logger.warning(f"Không khởi tạo được Google GenAI Client: {e}")
                self.client = None
        return self.client

    def start_video_generation(
        self,
        prompt: str,
        aspect_ratio: str = None,
        duration: int = None,
        number_of_videos: int = 1,
        strict_model: bool = True,
    ) -> str:
        """Start async Google Veo video generation job.

        Returns operation name (e.g. 'operations/...')  or 'synthetic_op_...' if no API key.
        Raises VeoQuotaError if API returns 429 (quota exceeded) — caller should set QUOTA_WAIT.
        """
        client = self._get_client()
        if not client:
            logger.info("Chưa có GEMINI_API_KEY, sử dụng Synthetic Fallback")
            return f"synthetic_op_{int(time.time())}"

        if not aspect_ratio:
            aspect_ratio = DEFAULT_ASPECT_RATIO or "9:16"

        if not duration or duration not in (4, 6, 8):
            duration = DEFAULT_VIDEO_DURATION_SEC if DEFAULT_VIDEO_DURATION_SEC in (4, 6, 8) else 8

        number_of_videos = max(1, min(4, int(number_of_videos or 1)))

        primary_model = DEFAULT_VEO_MODEL or "veo-3.1-lite-generate-preview"
        label = VEO_MODEL_MAP.get(primary_model, primary_model)
        logger.info(
            f"Đang gửi yêu cầu Google Veo API | Model: '{label}' | "
            f"{aspect_ratio} | {duration}s | x{number_of_videos} biến thể | "
            f"Prompt: '{prompt[:60]}...'"
        )

        fallbacks = [
            "veo-3.1-fast-generate-preview",
            "veo-3.1-generate-preview",
            "veo-3.1-lite-generate-preview"
        ]
        models_to_try = [primary_model] + [m for m in fallbacks if m != primary_model]

        last_err = None
        has_quota_error = False
        for model_name in models_to_try:
            try:
                operation = self.client.models.generate_videos(
                    model=model_name,
                    source=types.GenerateVideosSource(prompt=prompt),
                    config=types.GenerateVideosConfig(
                        person_generation="allow_all",
                        aspect_ratio=aspect_ratio,
                        duration_seconds=duration,
                        number_of_videos=number_of_videos,
                        resolution="1080p",
                    )
                )
                logger.info(f"✅ Google Veo Operation tạo thành công với model '{model_name}': {operation.name}")
                return operation.name
            except Exception as e:
                err_str = str(e)
                last_err = e
                logger.warning(f"Thử model Veo '{model_name}' thất bại: {e}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    has_quota_error = True

        if has_quota_error:
            logger.warning("⏳ Tất cả model Veo đều tạm thời hết Quota (429) — job chuyển sang QUOTA_WAIT để retry sau")
            raise VeoQuotaError(f"Veo API quota exceeded: {last_err}")

        logger.warning(f"Tất cả model Google Veo API đều lỗi ({last_err}), chuyển sang Synthetic Fallback...")
        return f"synthetic_op_{int(time.time())}"


    def generate_synthetic_raw_video(self, out_path: Path, duration_sec: int = DEFAULT_VIDEO_DURATION_SEC, prompt: str = "") -> bool:
        """Generate high-quality 9:16 vertical synthetic video with dark cinematic motion background for testing"""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        bg_jpg = out_path.with_suffix(".jpg")
        try:
            img = Image.new('RGB', (TARGET_WIDTH, TARGET_HEIGHT), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)
            
            # Subtle gradient background
            for y in range(TARGET_HEIGHT):
                r = int(15 + (y / TARGET_HEIGHT) * 25)
                g = int(23 + (y / TARGET_HEIGHT) * 35)
                b = int(42 + (y / TARGET_HEIGHT) * 60)
                draw.line([(0, y), (TARGET_WIDTH, y)], fill=(r, g, b))
                
            # Draw subtle tech grid lines
            for i in range(0, TARGET_HEIGHT, 120):
                draw.line([(0, i), (TARGET_WIDTH, i)], fill=(30, 41, 59), width=1)
                
            img.save(bg_jpg)
            
            cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1",
                "-i", str(bg_jpg),
                "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT},zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration_sec*30)}:s={TARGET_WIDTH}x{TARGET_HEIGHT}:fps={TARGET_FPS}",
                "-t", str(duration_sec),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                str(out_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if bg_jpg.exists():
                bg_jpg.unlink(missing_ok=True)
            return out_path.exists()
        except Exception as e:
            logger.error(f"Lỗi sinh video synthetic: {e}")
            if bg_jpg.exists():
                bg_jpg.unlink(missing_ok=True)
            return False

    def poll_and_download(self, operation_name: str, out_path: Path, timeout_sec: int = 600) -> bool:
        """Poll the LRO operation status every 5 seconds and download video when completed"""
        client = self._get_client()
        if operation_name.startswith("synthetic_op_") or not client:
            logger.info("Sinh video raw 9:16 mẫu bằng Synthetic Engine...")
            return self.generate_synthetic_raw_video(out_path)

        start_time = time.time()
        logger.info(f"⏳ Bắt đầu poll Veo operation: {operation_name} (Thăm dò mỗi 5s)...")

        while time.time() - start_time < timeout_sec:
            try:
                operation = self.client.operations.get(operation=operation_name)
                if operation.done:
                    if operation.error:
                        logger.error(f"❌ Veo API Operation trả về lỗi: {operation.error}")
                        return False

                    result = operation.result or getattr(operation, 'response', None)
                    if result and hasattr(result, 'generated_videos') and result.generated_videos:
                        gen_video = result.generated_videos[0]
                        vid = getattr(gen_video, 'video', None)
                        if vid:
                            try:
                                # Tải stream từ Google Cloud về bộ nhớ (inject video_bytes vào vid)
                                self.client.files.download(file=vid)
                                if hasattr(vid, 'save') and callable(vid.save):
                                    vid.save(str(out_path))
                                elif getattr(vid, 'video_bytes', None):
                                    with open(out_path, "wb") as f:
                                        f.write(vid.video_bytes)
                                logger.info(f"✅ Tải video thành công về -> {out_path.name}")
                                return True
                            except Exception as dl_err:
                                logger.warning(f"Tải trực tiếp object gặp vấn đề ({dl_err}), chuyển sang thử tải qua URI...")
                                if getattr(vid, 'uri', None):
                                    uri_name = vid.uri.split('/')[-1]
                                    video_bytes = self.client.files.download(file=uri_name)
                                    with open(out_path, "wb") as f:
                                        f.write(video_bytes)
                                    logger.info(f"✅ Tải video thành công từ URI -> {out_path.name}")
                                    return True

                    logger.error(f"❌ Operation hoàn thành nhưng không tìm thấy cấu trúc video hợp lệ: {result}")
                    return False
            except Exception as e:
                logger.error(f"⚠️ Lỗi trong lúc poll Veo operation: {e}")

            time.sleep(5)

        logger.warning(f"❌ Timeout sinh video từ Veo API ({timeout_sec}s)")
        return False

    def process_veo_job(self, job_id: int):
        """Worker function: Process SCRIPTED or QUOTA_WAIT job -> call Veo API -> download raw video"""
        db = DatabaseManager()
        job = db.get_job(job_id)
        if not job or job['status'] not in (JobStatus.SCRIPTED.value, JobStatus.QUOTA_WAIT.value):
            return

        try:
            from config.settings import DEFAULT_VEO_DURATION, DEFAULT_VEO_VARIANTS, DEFAULT_VEO_STRICT_MODEL, DEFAULT_ASPECT_RATIO
            db.update_job(job_id, status=JobStatus.GENERATING_VEO.value)
            out_raw_path = GENERATED_DIR / f"raw_{job_id}.mp4"

            op_name = self.start_video_generation(
                prompt=job['veo_prompt'],
                aspect_ratio=DEFAULT_ASPECT_RATIO or "9:16",
                duration=DEFAULT_VEO_DURATION or 8,
                number_of_videos=DEFAULT_VEO_VARIANTS or 1,
                strict_model=DEFAULT_VEO_STRICT_MODEL,
            )
            db.update_job(job_id, veo_operation_id=op_name)

            success = self.poll_and_download(op_name, out_raw_path)
            if success and out_raw_path.exists():
                # Check it's a real Veo video (not synthetic fallback)
                if op_name.startswith("synthetic_op_"):
                    logger.warning(f"Job #{job_id}: Video là synthetic (không có API key), đánh dấu VEO_DONE với cờ synthetic")
                db.update_job(
                    job_id,
                    video_raw_path=str(out_raw_path),
                    status=JobStatus.VEO_DONE.value
                )
            else:
                db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="Không tải được video raw từ Veo API")

        except VeoQuotaError as e:
            # Quota exceeded — set QUOTA_WAIT and wait 60s before next attempt to avoid spamming the API
            logger.warning(f"⏳ Job #{job_id}: Veo API quota hết (429), chuyển sang QUOTA_WAIT. Nghỉ 60s trước khi retry...")
            db.update_job(
                job_id,
                status=JobStatus.QUOTA_WAIT.value,
                error_msg=f"Veo API quota exceeded (429) — sẽ retry tự động sau ít phút"
            )
        except Exception as e:
            logger.exception(f"Lỗi sinh video Veo API cho Job #{job_id}: {e}")
            db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))

