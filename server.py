import threading
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel
import uvicorn

from config.settings import STORAGE_DIR, FINAL_DIR
from core.db import DatabaseManager, JobStatus
from queue_manager import MultiThreadQueueManager
from core.video_processor import VideoProcessor
from publishers.facebook_publisher import FacebookPublisher
from publishers.tiktok_publisher import TikTokPublisher
from publishers.x_publisher import XPublisher

logger = logging.getLogger("FastAPIServer")

app = FastAPI(
    title="Veo Studio AI PRO API",
    description="Backend REST API Server for AI Short Video Automation & Social Publishing",
    version="2.5.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Manager & DB
db = DatabaseManager()
queue_mgr = MultiThreadQueueManager()
engine_thread = None

@app.on_event("startup")
def startup_event():
    global engine_thread
    if not queue_mgr.is_running:
        def _run():
            queue_mgr.start_loop(poll_interval_sec=3)

        engine_thread = threading.Thread(target=_run, daemon=True)
        engine_thread.start()
        logger.info("Đã tự động khởi chạy Queue Manager đa luồng khi server startup!")

# Pydantic Schemas
class PromptBatchRequest(BaseModel):
    topic: str
    count: int = 10
    styles: list[str] = ["cinematic"]
    voices: list[str] = ["vi-VN-HoaiMyNeural"]
    keep_context: bool = True
    custom_context: str = ""

class CloneVideoRequest(BaseModel):
    url: str
    add_voiceover: bool = True
    add_subtitle: bool = True

class DeleteBatchRequest(BaseModel):
    job_ids: list[int]

class ConcatVideosRequest(BaseModel):
    job_ids: list[int]
    title: str = "Video Tổng Hợp 9:16"

from config.settings import update_env_settings, reload_settings

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: str = None
    max_workers: int = 5
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
            custom_context=req.custom_context.strip()
        )

    background_tasks.add_task(_create)
    return {
        "status": "success",
        "message": f"Đã nhận yêu cầu sinh {req.count} video kịch bản cho chủ đề: '{req.topic}' (Khóa Context: {'Bật' if req.keep_context else 'Tắt'})"
    }

@app.post("/api/clone-video")
def clone_video(req: CloneVideoRequest):
    """Add a TikTok/Reels clone video URL job"""
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
    return {
        "status": "success",
        "data": {
            "facebook": fb_pub.is_logged_in(),
            "tiktok": tt_pub.is_logged_in(),
            "x": x_pub.is_logged_in()
        }
    }

@app.post("/api/social/login")
def social_login(req: SocialLoginRequest, background_tasks: BackgroundTasks):
    """Trigger browser window for manual user login to social network"""
    platform = req.platform.lower()
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

    background_tasks.add_task(pub.interactive_login, login_url)
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


@app.post("/api/fb-profiles/{profile_id}/login")
def login_fb_profile(profile_id: str, background_tasks: BackgroundTasks):
    """Mở browser fullscreen để user đăng nhập profile (chạy background)."""
    from publishers.fb_profile_manager import FBProfileManager
    mgr = FBProfileManager()
    if not mgr.get_profile(profile_id):
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' không tồn tại")

    def _do_login():
        mgr.login_profile(profile_id)

    background_tasks.add_task(_do_login)
    return {"status": "success", "message": f"Đang mở browser đăng nhập profile '{profile_id}'..."}


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


# ─── Post to multiple profiles (parallel) ───

class PostToProfilesRequest(BaseModel):
    job_id: int
    profile_ids: list   # ["default", "abc123", "def456"]
    max_workers: int = 3

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
    logs = db.get_fb_post_logs(job_id)
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



# ─── Video Stream API (Smart — works for both clone & generated videos) ───
@app.get("/api/video-stream/{job_id}")
def video_stream(job_id: int):
    """Serve video file for preview — handles both clone (downloads/) and generated (final/) videos"""
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

    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )

# Serve Static UI & Videos
UI_DIR = Path(__file__).resolve().parent / "ui"
DOWNLOADS_DIR = Path(__file__).resolve().parent / "storage" / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
app.mount("/videos", StaticFiles(directory=str(FINAL_DIR)), name="videos")
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
