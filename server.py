import sys
import threading
import logging

from contextlib import asynccontextmanager
from pathlib import Path
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from config.settings import STORAGE_DIR, FINAL_DIR
from core.db import DatabaseManager, JobStatus
from queue_manager import MultiThreadQueueManager
from core.video_processor import VideoProcessor
from publishers.facebook_publisher import FacebookPublisher
from publishers.tiktok_publisher import TikTokPublisher
from publishers.x_publisher import XPublisher
from version import __version__, APP_NAME, FULL_NAME, check_remote_version

logger = logging.getLogger("FastAPIServer")

# Initialize Manager & DB
db = DatabaseManager()
queue_mgr = MultiThreadQueueManager()
engine_thread = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-start Queue Manager on server startup using modern lifespan API"""
    global engine_thread
    if not queue_mgr.is_running:
        def _run():
            queue_mgr.start_loop(poll_interval_sec=3)
        engine_thread = threading.Thread(target=_run, daemon=True)
        engine_thread.start()
        logger.info("Đã tự động khởi chạy Queue Manager đa luồng khi server startup!")
    yield
    # Shutdown
    if queue_mgr.is_running:
        queue_mgr.stop()

app = FastAPI(
    title=APP_NAME,
    description="Backend REST API Server for AI Short Video Automation & Social Publishing",
    version=__version__,
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/version")
def get_version():
    remote_data = check_remote_version()
    return {
        "status": "success",
        "version": __version__,
        "app_name": APP_NAME,
        "full_name": FULL_NAME,
        "remote": remote_data
    }

@app.get("/api/remote-config")
def get_remote_config():
    mgr = get_remote_config_manager()
    status_info = mgr.check_app_status()
    return {
        "status": "success",
        "config": status_info
    }

@app.post("/api/remote-config/refresh")
def refresh_remote_config():
    mgr = get_remote_config_manager()
    mgr.invalidate_cache()
    status_info = mgr.check_app_status(force_reload=True)
    return {
        "status": "success",
        "message": "Đã invalidate cache và làm mới cấu hình từ xa thành công!",
        "config": status_info
    }

def verify_app_not_blocked(feature_name: str = None):
    mgr = get_remote_config_manager()
    status_info = mgr.check_app_status()
    if status_info.get("is_blocked"):
        reason = status_info.get("block_reason", "Ứng dụng bị khóa từ xa.")
        raise HTTPException(status_code=403, detail=reason)
    if feature_name and not mgr.is_feature_enabled(feature_name):
        raise HTTPException(status_code=403, detail=f"Tính năng '{feature_name}' tạm thời bị vô hiệu hóa từ xa bởi Quản trị viên.")



# Pydantic Schemas
class PromptBatchRequest(BaseModel):
    topic: str
    count: int = 10
    styles: list[str] = ["cinematic"]
    voices: list[str] = ["vi-VN-HoaiMyNeural"]
    keep_context: bool = True
    custom_context: str = ""
    aspect_ratio: str = "9:16"
    duration: int = 8
    variants: int = 1
    veo_model: str = "veo-3.1-lite-generate-preview"
    quality: str = "1080p"

class CloneVideoRequest(BaseModel):
    url: str
    add_voiceover: bool = False
    add_subtitle: bool = False

class DeleteBatchRequest(BaseModel):
    job_ids: list[int]

class ConcatVideosRequest(BaseModel):
    job_ids: list[int]
    title: str = "Video Tổng Hợp 9:16"

from config.settings import update_env_settings, reload_settings

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: str = None
    max_workers: int = 5
    max_labs_workers: int = 3
    gen_engine: str = "labs"
    storage_dir: str = None
    veo_model: str = "veo-3.1-lite-generate-preview"
    image_model: str = "imagen-3.0-generate-002"
    aspect_ratio: str = "9:16"
    require_confirmation: bool = False
    veo_duration: int = 8
    veo_variants: int = 1
    veo_strict_model: bool = True

class SocialLoginRequest(BaseModel):
    platform: str

class LabsGoogleGenerateRequest(BaseModel):
    prompt: str
    title: str = ""
    quality: str = "1080p"
    aspect_ratio: str = "9:16"
    duration: int = 8
    variants: int = 1
    veo_model: str = "veo-3.1-lite-generate-preview"
    add_subtitle: bool = True
    add_voiceover: bool = True

class SocialLogoutRequest(BaseModel):
    platform: str



# API Endpoints
@app.get("/api/stats")
def get_statistics():
    """Return real-time job statistics from SQLite DB"""
    stats = db.get_statistics()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(fb_posted) as fb, SUM(tiktok_posted) as tiktok, SUM(x_posted) as x, COUNT(*) as total FROM jobs")
        row = cursor.fetchone()
        social = {
            "fb": row['fb'] or 0,
            "tiktok": row['tiktok'] or 0,
            "x": row['x'] or 0,
            "total": row['total'] or 0
        }
    return {
        "status": "success",
        "data": stats,
        "social": social,
        "is_engine_running": queue_mgr.is_running
    }

def _get_video_duration(video_path: str) -> float | None:
    """Return video duration in seconds using ffmpeg -i stderr parsing"""
    import subprocess, imageio_ffmpeg, re
    if not video_path:
        return None
    p = Path(video_path)
    if not p.exists():
        return None
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        res = subprocess.run(
            [ffmpeg_exe, "-i", str(p)],
            capture_output=True, text=True, timeout=8
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            total = h * 3600 + mn * 60 + s
            return round(total, 1)
    except Exception:
        pass
    return None

@app.get("/api/jobs")
def get_jobs(status: str = None, limit: int = 100):
    """Retrieve video jobs list from SQLite DB with actual video duration"""
    if status:
        try:
            enum_status = JobStatus(status.upper())
            jobs = db.get_jobs_by_status(enum_status, limit=limit)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Trạng thái '{status}' không hợp lệ")
    else:
        # Get recent jobs
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            jobs = [dict(r) for r in rows]

    # Inject actual video duration into each job
    for job in jobs:
        video_path = job.get("video_final_path") or job.get("video_raw_path")
        dur = _get_video_duration(video_path)
        job["duration_sec"] = dur

    return {"status": "success", "count": len(jobs), "data": jobs}

@app.delete("/api/jobs/{job_id}")
def delete_single_job(job_id: int):
    """Delete a video job and cleanup associated files"""
    success = db.delete_job(job_id)
    if success:
        return {"status": "success", "message": f"Đã xóa thành công Job #{job_id}"}
    else:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Job #{job_id} để xóa")

@app.post("/api/jobs/retry-batch")
def retry_batch_jobs(req: DeleteBatchRequest):
    """Reset multiple video jobs by IDs back to SCRIPTED or PENDING for retry"""
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất 1 Job để retry")

    retried_count = 0
    with db._get_connection() as conn:
        cursor = conn.cursor()
        for jid in req.job_ids:
            job = db.get_job(jid)
            if job:
                # If it's CLONE job, reset to PENDING; if PROMPT, reset to SCRIPTED
                new_status = JobStatus.PENDING.value if job['source_type'] == 'CLONE' else JobStatus.SCRIPTED.value
                cursor.execute(
                    "UPDATE jobs SET status=?, veo_operation_id=NULL, video_raw_path=NULL, video_final_path=NULL, error_msg=NULL WHERE id=?",
                    (new_status, jid)
                )
                retried_count += 1
        conn.commit()

    return {
        "status": "success",
        "retried_count": retried_count,
        "message": f"Đã reset {retried_count} Job để chạy lại tự động!"
    }

@app.post("/api/jobs/delete-batch")
def delete_batch_jobs(req: DeleteBatchRequest):
    """Delete multiple video jobs by IDs"""
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất 1 Job để xóa")

    deleted_count = 0
    for jid in req.job_ids:
        if db.delete_job(jid):
            deleted_count += 1

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "message": f"Đã xóa thành công {deleted_count} Job!"
    }

@app.post("/api/jobs/retry-synthetic")
def retry_synthetic_jobs():
    """Reset all jobs with synthetic fallback videos back to SCRIPTED so they re-run with real Veo API"""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, video_raw_path, video_final_path FROM jobs WHERE veo_operation_id LIKE 'synthetic_op_%' AND status NOT IN ('FAILED', 'PUBLISHED')"
            )
            rows = cursor.fetchall()
            count = 0
            for row in rows:
                for fpath in [row['video_raw_path'], row['video_final_path']]:
                    if fpath:
                        try: Path(fpath).unlink(missing_ok=True)
                        except Exception: pass
                cursor.execute(
                    "UPDATE jobs SET status='SCRIPTED', veo_operation_id=NULL, video_raw_path=NULL, video_final_path=NULL, error_msg=NULL WHERE id=?",
                    (row['id'],)
                )
                count += 1
            conn.commit()
        return {"status": "success", "message": f"Đã reset {count} job synthetic về SCRIPTED để retry với Veo API thực", "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi reset jobs: {e}")

@app.get("/api/settings")
def get_settings():
    """Get current system settings"""
    from config import settings as cfg
    import importlib; importlib.reload(cfg)
    return {
        "status": "success",
        "data": {
            "gemini_api_key": cfg.GEMINI_API_KEY,
            "max_workers": cfg.MAX_CONCURRENT_VEO_JOBS,
            "max_labs_workers": getattr(cfg, 'MAX_CONCURRENT_LABS_JOBS', 3),
            "gen_engine": getattr(cfg, 'DEFAULT_GEN_ENGINE', 'labs'),
            "storage_dir": str(cfg.FINAL_DIR),
            "veo_model": cfg.DEFAULT_VEO_MODEL,
            "image_model": cfg.DEFAULT_IMAGE_MODEL,
            "aspect_ratio": cfg.DEFAULT_ASPECT_RATIO,
            "require_confirmation": cfg.REQUIRE_CONFIRMATION,
            "veo_duration": cfg.DEFAULT_VEO_DURATION,
            "veo_variants": cfg.DEFAULT_VEO_VARIANTS,
            "veo_strict_model": cfg.DEFAULT_VEO_STRICT_MODEL,
            "fb_page_id": getattr(cfg, 'FB_PAGE_ID', ''),
            "fb_page_token": "****" if getattr(cfg, 'FB_PAGE_ACCESS_TOKEN', '') else "",
        }
    }

@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest):
    """Update system settings (API Key, Max Workers, Storage Directory, Labs.google Agent options)"""
    try:
        update_env_settings(
            api_key=req.gemini_api_key,
            max_workers=req.max_workers,
            max_labs_workers=req.max_labs_workers,
            gen_engine=req.gen_engine,
            storage_dir=req.storage_dir,
            veo_model=req.veo_model,
            image_model=req.image_model,
            aspect_ratio=req.aspect_ratio,
            require_confirmation=req.require_confirmation,
            veo_duration=req.veo_duration,
            veo_variants=req.veo_variants,
            veo_strict_model=req.veo_strict_model,
        )
        return {
            "status": "success",
            "message": "Đã lưu và cập nhật cấu hình thành công!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể lưu cấu hình: {e}")

class FbApiConfigRequest(BaseModel):
    page_id: str
    page_access_token: str

@app.post("/api/social/fb-api-config")
def save_fb_api_config(req: FbApiConfigRequest):
    """Save Facebook Page ID and Page Access Token for Graph API publishing"""
    try:
        update_env_settings(
            fb_page_id=req.page_id.strip(),
            fb_page_access_token=req.page_access_token.strip()
        )
        return {"status": "success", "message": "Facebook Graph API config đã được lưu thành công!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lưu Facebook API config: {e}")

@app.post("/api/generate-prompt")
def generate_prompt_batch(req: PromptBatchRequest, background_tasks: BackgroundTasks):
    """Generate batch of 10s video scripts & prompts from a topic"""
    verify_app_not_blocked("veo_generation")
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập chủ đề video")

    # Add jobs asynchronously
    def _create():
        queue_mgr.add_prompt_batch(
            req.topic.strip(),
            count=req.count,
            styles=req.styles,
            voices=req.voices,
            keep_context=req.keep_context,
            custom_context=req.custom_context.strip(),
            aspect_ratio=req.aspect_ratio,
            duration=req.duration,
            variants=req.variants,
            veo_model=req.veo_model,
            quality=req.quality
        )

    background_tasks.add_task(_create)
    return {
        "status": "success",
        "message": f"Đã nhận yêu cầu sinh {req.count} video kịch bản cho chủ đề: '{req.topic}' (Khóa Context: {'Bật' if req.keep_context else 'Tắt'})"
    }

@app.post("/api/clone-video")
def clone_video(req: CloneVideoRequest):
    """Add a TikTok/Reels clone video URL job"""
    verify_app_not_blocked("clone_video")
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập link video")

    job_id = queue_mgr.add_clone_job(
        req.url.strip(),
        add_voiceover=req.add_voiceover,
        add_subtitle=req.add_subtitle
    )
    opts = []
    if req.add_voiceover: opts.append("giọng đọc AI")
    if req.add_subtitle: opts.append("phụ đề")
    opts_str = f" + {', '.join(opts)}" if opts else " (chỉ tải video gốc)"
    return {
        "status": "success",
        "job_id": job_id,
        "message": f"Đã thêm Job Clone #{job_id}: tải video{opts_str}"
    }

@app.post("/api/concat-videos")
def concat_videos(req: ConcatVideosRequest):
    """Concatenate selected video jobs into a single long 9:16 video"""
    if not req.job_ids or len(req.job_ids) < 2:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất 2 video để ghép thành 1 video dài")

    video_paths = []
    with db._get_connection() as conn:
        cursor = conn.cursor()
        for jid in req.job_ids:
            cursor.execute("SELECT video_final_path, video_raw_path FROM jobs WHERE id = ?", (jid,))
            row = cursor.fetchone()
            if row:
                vpath = row['video_final_path'] or row['video_raw_path']
                if vpath and Path(vpath).exists():
                    video_paths.append(Path(vpath))

    if not video_paths:
        raise HTTPException(status_code=400, detail="Không tìm thấy các file video hợp lệ để ghép")

    # Create new combined job in DB
    concat_job_id = db.create_job(
        source_type="CONCAT",
        source_input=f"Concat {len(video_paths)} videos: {req.job_ids}",
        title=req.title or f"Video Tổng Hợp ({len(video_paths)} đoạn)",
        voiceover_text=f"Video tổng hợp ghép từ {len(video_paths)} đoạn clip ngắn 9:16.",
        veo_prompt=f"Concatenation of jobs {req.job_ids}",
        tags=["#VideoFull", "#ConcatSeries", "#AI2026"]
    )

    final_concat_path = FINAL_DIR / f"concat_{concat_job_id}.mp4"
    proc = VideoProcessor()
    success = proc.concat_videos(video_paths, final_concat_path)

    if success and final_concat_path.exists():
        db.update_job(
            concat_job_id,
            video_final_path=str(final_concat_path),
            status=JobStatus.READY_TO_POST.value
        )
        return {
            "status": "success",
            "job_id": concat_job_id,
            "filename": final_concat_path.name,
            "message": f"Ghép thành công {len(video_paths)} video thành 1 video dài!"
        }
    else:
        db.update_job(concat_job_id, status=JobStatus.FAILED.value, error_msg="Lỗi ghép nối video FFmpeg")
        raise HTTPException(status_code=500, detail="Không thể ghép nối video bằng FFmpeg")

@app.post("/api/engine/toggle")
def toggle_engine():
    """Start or Stop the multi-threaded Queue Worker Manager loop"""
    global engine_thread, queue_mgr
    if queue_mgr.is_running:
        queue_mgr.stop()
        return {"status": "success", "is_running": False, "message": "Đã dừng Queue Manager đa luồng"}
    else:
        # Recreate queue_mgr to get fresh thread pools (old pools are unusable after shutdown)
        queue_mgr = MultiThreadQueueManager()

        def _run():
            queue_mgr.start_loop(poll_interval_sec=3)

        engine_thread = threading.Thread(target=_run, daemon=True)
        engine_thread.start()
        return {"status": "success", "is_running": True, "message": "Đã khởi chạy Queue Manager đa luồng ngầm!"}

@app.get("/api/social/status")
def get_social_status():
    """Get login session status for all social media platforms"""
    fb_pub = FacebookPublisher()
    tt_pub = TikTokPublisher()
    x_pub = XPublisher()
    from core.labs_google_generator import LabsGoogleGenerator
    labs_gen = LabsGoogleGenerator()
    return {
        "status": "success",
        "data": {
            "facebook": fb_pub.is_logged_in(),
            "tiktok": tt_pub.is_logged_in(),
            "x": x_pub.is_logged_in(),
            "labs_google": labs_gen.is_logged_in()
        }
    }

ACTIVE_LOGIN_THREADS = {}
login_thread_lock = threading.Lock()

def is_login_thread_active(key: str) -> bool:
    with login_thread_lock:
        t = ACTIVE_LOGIN_THREADS.get(key)
        return t is not None and t.is_alive()

def register_login_thread(key: str, thread: threading.Thread):
    with login_thread_lock:
        ACTIVE_LOGIN_THREADS[key] = thread

@app.get("/api/labs-google/status")
def get_labs_google_status():
    from core.labs_google_generator import LabsGoogleGenerator
    gen = LabsGoogleGenerator()
    return {"status": "success", "logged_in": gen.is_logged_in()}

@app.post("/api/labs-google/login")
def labs_google_login():
    if is_login_thread_active("labs_google"):
        return {"status": "warning", "message": "Trình duyệt đăng nhập Labs.google đã mở sẵn trên thanh tác vụ!"}
    from core.labs_google_generator import LabsGoogleGenerator
    gen = LabsGoogleGenerator()
    t = threading.Thread(target=gen.login_manual, daemon=True, name="login_labs_google")
    register_login_thread("labs_google", t)
    t.start()
    return {"status": "success", "message": "Đã mở cửa sổ đăng nhập Labs.google"}

@app.post("/api/labs-google/generate")
def labs_google_generate(req: LabsGoogleGenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt không được để trống")
    quality = req.quality.strip() if req.quality else "1080p"
    job_id = db.create_job(
        source_type="LABS_PROMPT",
        source_input=req.prompt.strip(),
        title=req.title.strip() or req.prompt.strip()[:50],
        veo_prompt=req.prompt.strip(),
        quality=quality,
        aspect_ratio=req.aspect_ratio,
        duration=req.duration,
        variants=req.variants,
        veo_model=req.veo_model,
        add_subtitle=req.add_subtitle,
        add_voiceover=req.add_voiceover
    )
    sub_msg = " + Sub" if req.add_subtitle else ""
    return {"status": "success", "job_id": job_id, "message": f"Đã tạo Job #{job_id} cho Labs.google ({quality}{sub_msg})"}

@app.post("/api/social/login")
def social_login(req: SocialLoginRequest):
    """Trigger browser window for manual user login to social network"""
    platform = req.platform.lower()
    if is_login_thread_active(platform):
        return {"status": "warning", "message": f"Trình duyệt đăng nhập {req.platform} đã được mở sẵn!"}

    if platform == "facebook":
        pub = FacebookPublisher()
        login_url = "https://www.facebook.com/"
    elif platform == "tiktok":
        pub = TikTokPublisher()
        login_url = "https://www.tiktok.com/login"
    elif platform in ["x", "twitter"]:
        pub = XPublisher()
        login_url = "https://x.com/i/flow/login"
    else:
        raise HTTPException(status_code=400, detail="Mạng xã hội không hỗ trợ")

    # Dùng Thread riêng để tránh xung đột asyncio + sync_playwright
    t = threading.Thread(target=pub.interactive_login, args=(login_url,), daemon=True, name=f"login_{platform}")
    register_login_thread(platform, t)
    t.start()
    return {"status": "success", "message": f"Đã kích hoạt cửa sổ đăng nhập {req.platform}"}

@app.post("/api/social/logout")
def social_logout(req: SocialLogoutRequest):
    """Logout / clear browser session for the specified social media network"""
    platform = req.platform.lower()
    if platform == "facebook":
        pub = FacebookPublisher()
    elif platform == "tiktok":
        pub = TikTokPublisher()
    elif platform in ["x", "twitter"]:
        pub = XPublisher()
    else:
        raise HTTPException(status_code=400, detail="Mạng xã hội không hỗ trợ")

    success = pub.logout()
    if success:
        return {"status": "success", "message": f"Đã đăng xuất tài khoản {req.platform} thành công!"}
    else:
        raise HTTPException(status_code=500, detail=f"Không thể xóa session của {req.platform}")

class TestPostRequest(BaseModel):
    job_id: int
    platform: str = "facebook"  # facebook | tiktok | x

@app.post("/api/social/test-post")
def social_test_post(req: TestPostRequest, background_tasks: BackgroundTasks):
    """Manually trigger posting a specific job to a social platform (for testing)"""
    job = db.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Job #{req.job_id}")

    video_final = job.get("video_final_path") or job.get("video_raw_path")
    if not video_final or not Path(video_final).exists():
        raise HTTPException(status_code=400, detail=f"Job #{req.job_id} chưa có file video hoàn chỉnh")

    platform = req.platform.lower()

    import json
    title = (job.get("title") or "").strip()
    voiceover = (job.get("voiceover_text") or "").strip()
    base = f"{title}\n\n" if title else ""
    remaining = 2000 - len(base)
    if len(voiceover) > remaining:
        voiceover = voiceover[:remaining].rsplit(' ', 1)[0] + "..."
    caption = base + voiceover

    raw_tags = job.get("tags", [])
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except Exception:
            raw_tags = []
    tags = raw_tags if isinstance(raw_tags, list) else []

    def _do_post():
        video_path = Path(video_final)
        if platform == "facebook":
            pub = FacebookPublisher()
        elif platform == "tiktok":
            pub = TikTokPublisher()
        elif platform in ["x", "twitter"]:
            pub = XPublisher()
        else:
            return
        ok = pub.post_video(video_path, caption, tags)
        if ok:
            if platform == "facebook":
                db.update_job(req.job_id, fb_posted=1)
            elif platform == "tiktok":
                db.update_job(req.job_id, tiktok_posted=1)
            elif platform in ["x", "twitter"]:
                db.update_job(req.job_id, x_posted=1)
            db.update_job(req.job_id, status=JobStatus.PUBLISHED.value)

    background_tasks.add_task(_do_post)
    return {"status": "success", "message": f"Đang đăng Job #{req.job_id} lên {req.platform} trong nền..."}

# ─────────────────────────────────────────────────────────────────────────────
# ─── Facebook Multi-Profile Management ───────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/fb-profiles")
def list_fb_profiles():
    """Lấy danh sách tất cả FB profiles kèm trạng thái đăng nhập."""
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    return {"profiles": mgr.list_profiles()}


class CreateProfileRequest(BaseModel):
    name: str

@app.post("/api/fb-profiles")
def create_fb_profile(req: CreateProfileRequest):
    """Tạo profile FB mới."""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Tên profile không được để trống")
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    profile = mgr.create_profile(req.name)
    return {"status": "success", "profile": profile}


@app.delete("/api/fb-profiles/{profile_id}")
def delete_fb_profile(profile_id: str):
    """Xóa profile FB + toàn bộ session data."""
    if profile_id == "default":
        raise HTTPException(status_code=400, detail="Không thể xóa profile 'Mặc Định'")
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    ok = mgr.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' không tồn tại")
    return {"status": "success", "message": f"Đã xóa profile {profile_id}"}


_login_in_progress = {}  # profile_id -> True khi dang login

@app.post("/api/fb-profiles/{profile_id}/login")
def login_fb_profile(profile_id: str):
    """Mở browser fullscreen để user đăng nhập profile (chạy ngầm trong thread riêng)."""
    from publishers.fb_profile_manager import FBProfileManager

    # Chan login trung lap
    if _login_in_progress.get(profile_id):
        return {"status": "error", "message": "Đang mở browser đăng nhập cho profile này rồi. Vui lòng đợi."}

    mgr = FBProfileManager()
    profile = mgr.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' không tồn tại")

    def _safe_print(msg: str):
        try:
            print(msg.encode('ascii', errors='replace').decode(), flush=True)
        except Exception:
            pass

    def _do_login():
        import traceback
        try:
            _login_in_progress[profile_id] = True
            _safe_print(f"[Login-Thread] START: profile '{profile['name']}' ({profile_id})")
            mgr.login_profile(profile_id)
            _safe_print(f"[Login-Thread] DONE: profile '{profile['name']}' ({profile_id})")
        except Exception as e:
            _safe_print(f"[Login-Thread] ERROR: {str(e)}")
            traceback.print_exc()
        finally:
            _login_in_progress.pop(profile_id, None)

    t = threading.Thread(target=_do_login, daemon=True, name=f"fb_login_{profile_id}")
    t.start()
    return {"status": "success", "message": f"Đang mở browser đăng nhập profile '{profile['name']}'..."}


@app.post("/api/fb-profiles/{profile_id}/logout")
def logout_fb_profile(profile_id: str):
    """Xóa session của profile (logout)."""
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    ok = mgr.logout_profile(profile_id)
    return {"status": "success" if ok else "error", "message": "Đã logout" if ok else "Không tìm thấy session"}


@app.get("/api/fb-profiles/{profile_id}/status")
def get_fb_profile_status(profile_id: str):
    """Kiểm tra trạng thái đăng nhập của một profile."""
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    profile = mgr.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' không tồn tại")
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# ─── TikTok Multi-Profile Management ────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/tiktok-profiles")
def list_tiktok_profiles():
    """Lấy danh sách tất cả TikTok profiles kèm trạng thái đăng nhập."""
    from publishers.tiktok_profile_manager import TikTokProfileManager
    mgr = TikTokProfileManager()
    return {"profiles": mgr.list_profiles()}


@app.post("/api/tiktok-profiles")
def create_tiktok_profile(req: CreateProfileRequest):
    """Tạo profile TikTok mới."""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Tên profile không được để trống")
    from publishers.tiktok_profile_manager import TikTokProfileManager
    mgr = TikTokProfileManager()
    profile = mgr.create_profile(req.name)
    return {"status": "success", "profile": profile}


@app.delete("/api/tiktok-profiles/{profile_id}")
def delete_tiktok_profile(profile_id: str):
    """Xóa profile TikTok + toàn bộ session data."""
    if profile_id == "default":
        raise HTTPException(status_code=400, detail="Không thể xóa profile 'Mặc Định'")
    from publishers.tiktok_profile_manager import TikTokProfileManager
    mgr = TikTokProfileManager()
    ok = mgr.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' không tồn tại")
    return {"status": "success", "message": f"Đã xóa profile TikTok {profile_id}"}


_tiktok_login_in_progress = {}

@app.post("/api/tiktok-profiles/{profile_id}/login")
def login_tiktok_profile(profile_id: str):
    """Mở browser để user đăng nhập profile TikTok."""
    from publishers.tiktok_profile_manager import TikTokProfileManager

    if _tiktok_login_in_progress.get(profile_id):
        return {"status": "error", "message": "Đang mở browser đăng nhập cho profile này rồi. Vui lòng đợi."}

    mgr = TikTokProfileManager()
    profile = mgr.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' không tồn tại")

    def _safe_print(msg: str):
        try:
            print(msg.encode('ascii', errors='replace').decode(), flush=True)
        except Exception:
            pass

    def _do_login():
        import traceback
        try:
            _tiktok_login_in_progress[profile_id] = True
            _safe_print(f"[TikTokLogin-Thread] START: profile '{profile['name']}' ({profile_id})")
            mgr.login_profile(profile_id)
            _safe_print(f"[TikTokLogin-Thread] DONE: profile '{profile['name']}' ({profile_id})")
        except Exception as e:
            _safe_print(f"[TikTokLogin-Thread] ERROR: {str(e)}")
            traceback.print_exc()
        finally:
            _tiktok_login_in_progress.pop(profile_id, None)

    t = threading.Thread(target=_do_login, daemon=True, name=f"tiktok_login_{profile_id}")
    t.start()
    return {"status": "success", "message": f"Đang mở browser đăng nhập profile TikTok '{profile['name']}'..."}


@app.post("/api/tiktok-profiles/{profile_id}/logout")
def logout_tiktok_profile(profile_id: str):
    """Xóa session của profile TikTok (logout)."""
    from publishers.tiktok_profile_manager import TikTokProfileManager
    mgr = TikTokProfileManager()
    ok = mgr.logout_profile(profile_id)
    return {"status": "success" if ok else "error", "message": "Đã logout TikTok" if ok else "Không tìm thấy session"}


# ─── Post to multiple profiles (parallel) ───

class PostToProfilesRequest(BaseModel):
    job_id: int
    profile_ids: list   # ["default", "abc123", "def456"]
    max_workers: int = 3
    custom_caption: str = None

@app.post("/api/social/post-to-profiles")
def post_to_profiles(req: PostToProfilesRequest, background_tasks: BackgroundTasks):
    """Đăng 1 job lên nhiều FB profiles ĐỒNG THỜI (parallel Playwright)."""
    job = db.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Job #{req.job_id}")

    video_path_str = job.get("video_final_path") or job.get("video_raw_path")
    if not video_path_str or not Path(video_path_str).exists():
        raise HTTPException(status_code=400, detail=f"Job #{req.job_id} chưa có video")

    if not req.profile_ids:
        raise HTTPException(status_code=400, detail="Chưa chọn profile nào")

    import json as _json
    if req.custom_caption and req.custom_caption.strip():
        caption = req.custom_caption.strip()
    else:
        title = (job.get("title") or "").strip()
        voiceover = (job.get("voiceover_text") or "").strip()
        base = f"{title}\n\n" if title else ""
        remaining = 2000 - len(base)
        if len(voiceover) > remaining:
            voiceover = voiceover[:remaining].rsplit(' ', 1)[0] + "..."
        caption = base + voiceover

    raw_tags = job.get("tags", [])
    if isinstance(raw_tags, str):
        try: raw_tags = _json.loads(raw_tags)
        except Exception: raw_tags = []
    tags = raw_tags if isinstance(raw_tags, list) else []

    # Tạo log entries ngay lập tức
    log_ids = {}
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    for pid in req.profile_ids:
        profile = mgr.get_profile(pid)
        pname = profile["name"] if profile else pid
        log_id = db.log_fb_post(req.job_id, pid, pname)
        log_ids[pid] = log_id

    def _do_parallel():
        video_path = Path(video_path_str)

        def on_result(pid, ok, err):
            status = "success" if ok else "failed"
            db.update_fb_post_log(log_ids[pid], status, err)
            if ok:
                # Nếu ít nhất 1 profile thành công → mark job fb_posted
                db.update_job(req.job_id, fb_posted=1, status=JobStatus.PUBLISHED.value)

        # Update all to "posting"
        for pid, lid in log_ids.items():
            db.update_fb_post_log(lid, "posting")

        mgr.post_to_profiles_parallel(
            video_path=video_path,
            caption=caption,
            profile_ids=req.profile_ids,
            max_workers=min(req.max_workers, 5),  # giới hạn tối đa 5
            on_result=on_result,
            tags=tags,
        )

    background_tasks.add_task(_do_parallel)
    profile_names = [mgr.get_profile(p)["name"] if mgr.get_profile(p) else p for p in req.profile_ids]
    return {
        "status": "success",
        "message": f"Đang đăng Job #{req.job_id} lên {len(req.profile_ids)} profiles: {', '.join(profile_names)}",
        "log_ids": log_ids,
    }


@app.get("/api/fb-post-logs/{job_id}")
def get_fb_post_logs(job_id: int):
    """Xem lịch sử đăng FB của 1 job (per-profile)."""
    return {"logs": db.get_fb_post_logs(job_id)}


@app.post("/api/social/post-to-tiktok-profiles")
def post_to_tiktok_profiles(req: PostToProfilesRequest, background_tasks: BackgroundTasks):
    """Đăng 1 job lên nhiều TikTok profiles ĐỒNG THỜI (parallel Playwright)."""
    job = db.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Job #{req.job_id}")

    video_path_str = job.get("video_final_path") or job.get("video_raw_path")
    if not video_path_str or not Path(video_path_str).exists():
        raise HTTPException(status_code=400, detail=f"Job #{req.job_id} chưa có video")

    if not req.profile_ids:
        raise HTTPException(status_code=400, detail="Chưa chọn profile TikTok nào")

    import json as _json
    if req.custom_caption and req.custom_caption.strip():
        caption = req.custom_caption.strip()
    else:
        title = (job.get("title") or "").strip()
        voiceover = (job.get("voiceover_text") or "").strip()
        base = f"{title}\n\n" if title else ""
        remaining = 2000 - len(base)
        if len(voiceover) > remaining:
            voiceover = voiceover[:remaining].rsplit(' ', 1)[0] + "..."
        caption = base + voiceover

    raw_tags = job.get("tags", [])
    if isinstance(raw_tags, str):
        try: raw_tags = _json.loads(raw_tags)
        except Exception: raw_tags = []
    tags = raw_tags if isinstance(raw_tags, list) else []

    log_ids = {}
    from publishers.tiktok_profile_manager import TikTokProfileManager
    mgr = TikTokProfileManager()
    for pid in req.profile_ids:
        profile = mgr.get_profile(pid)
        pname = profile["name"] if profile else pid
        log_id = db.log_tiktok_post(req.job_id, pid, pname)
        log_ids[pid] = log_id

    def _do_parallel():
        video_path = Path(video_path_str)

        def on_result(pid, ok, err):
            status = "success" if ok else "failed"
            db.update_tiktok_post_log(log_ids[pid], status, err)
            if ok:
                db.update_job(req.job_id, tiktok_posted=1, status=JobStatus.PUBLISHED.value)

        for pid, lid in log_ids.items():
            db.update_tiktok_post_log(lid, "posting")

        mgr.post_to_profiles_parallel(
            video_path=video_path,
            caption=caption,
            profile_ids=req.profile_ids,
            max_workers=min(req.max_workers, 5),
            on_result=on_result,
            tags=tags,
        )

    background_tasks.add_task(_do_parallel)
    profile_names = [mgr.get_profile(p)["name"] if mgr.get_profile(p) else p for p in req.profile_ids]
    return {
        "status": "success",
        "message": f"Đang đăng Job #{req.job_id} lên {len(req.profile_ids)} profiles TikTok: {', '.join(profile_names)}",
        "log_ids": log_ids,
    }


@app.get("/api/tiktok-post-logs/{job_id}")
def get_tiktok_post_logs(job_id: int):
    """Xem lịch sử đăng TikTok của 1 job (per-profile)."""
    logs = db.get_tiktok_post_logs(job_id)
    total = len(logs)
    success = sum(1 for l in logs if l["status"] == "success")
    return {
        "job_id": job_id,
        "total": total,
        "success": success,
        "failed": sum(1 for l in logs if l["status"] == "failed"),
        "pending": sum(1 for l in logs if l["status"] in ("pending", "posting")),
        "logs": logs,
    }

# ─── (end of FB multi-profile endpoints) ───────────────────────────────────



# ─── Video Preview API (Auto-transcode HEVC→H.264 for browser compatibility) ───
@app.get("/api/video-preview/{job_id}")
def video_preview(job_id: int):
    """Stream video with auto-transcode: HEVC/H.265 → H.264 so all browsers can play it."""
    import subprocess
    import imageio_ffmpeg

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT video_final_path, video_raw_path FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Job #{job_id}")

    video_path = row["video_final_path"] or row["video_raw_path"]
    if not video_path:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} chưa có video")

    path = Path(video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File không tồn tại: {video_path}")

    # Detect codec
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [ffmpeg_exe, "-i", str(path)],
        capture_output=True, text=True, timeout=10
    )
    needs_transcode = "hevc" in probe.stderr.lower() or "hvc1" in probe.stderr.lower()

    if needs_transcode:
        # Transcode HEVC → H.264 on-the-fly via pipe
        cmd = [
            ffmpeg_exe,
            "-i", str(path),
            "-vcodec", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-acodec", "aac",
            "-movflags", "frag_keyframe+empty_moov+faststart",
            "-f", "mp4",
            "pipe:1"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def iter_transcode():
            try:
                while True:
                    chunk = proc.stdout.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                proc.stdout.close()
                proc.wait()

        headers = {"Cache-Control": "no-cache", "Accept-Ranges": "none"}
        return StreamingResponse(iter_transcode(), media_type="video/mp4", headers=headers)
    else:
        # Already H.264 — use range-based streaming
        file_size = os.path.getsize(str(path))
        CHUNK_SIZE = 1024 * 1024

        def iter_full():
            with open(str(path), "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        headers = {"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
        return StreamingResponse(iter_full(), media_type="video/mp4", headers=headers)


# ─── Video Stream API (Smart — works for both clone & generated videos) ───
@app.get("/api/video-stream/{job_id}")
def video_stream(job_id: int, request: Request):
    """Serve video file for preview with proper HTTP Range support for browser HTML5 video player"""

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT video_final_path, video_raw_path FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy Job #{job_id}")

    video_path = row["video_final_path"] or row["video_raw_path"]
    if not video_path:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} chưa có video")

    path = Path(video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File không tồn tại: {video_path}")

    # Check if video is HEVC (H.265) — if so, delegate to video_preview for H.264 transcode
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        probe = subprocess.run([ffmpeg_exe, "-i", str(path)], capture_output=True, text=True, timeout=5)
        if "hevc" in probe.stderr.lower() or "hvc1" in probe.stderr.lower():
            return video_preview(job_id)
    except Exception:
        pass

    file_size = os.path.getsize(str(path))
    range_header = request.headers.get("range", None)

    # Chunk size: 1MB
    CHUNK_SIZE = 1024 * 1024

    if range_header:
        # Parse Range: bytes=start-end
        byte_range = range_header.replace("bytes=", "").strip()
        start_str, _, end_str = byte_range.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        def iter_file():
            with open(str(path), "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(iter_file(), status_code=206, headers=headers, media_type="video/mp4")
    else:
        # Full file response
        def iter_full():
            with open(str(path), "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(iter_full(), status_code=200, headers=headers, media_type="video/mp4")

# Serve Static UI & Videos
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

UI_DIR = BASE_DIR / "ui"
DOWNLOADS_DIR = BASE_DIR / "storage" / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
app.mount("/videos", StaticFiles(directory=str(FINAL_DIR)), name="videos")
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

if __name__ == "__main__":
    # reload=False: cần thiết để threading.Thread có thể mở browser window trên desktop
    # (reload=True tạo child process riêng, browser window sẽ không hiện trên màn hình)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
