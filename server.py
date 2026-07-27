import threading
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel
import uvicorn

from config.settings import STORAGE_DIR, FINAL_DIR, BASE_DIR, FACEBOOK_SESSION_DIR, TIKTOK_SESSION_DIR, X_SESSION_DIR
from core.db import DatabaseManager, JobStatus
from queue_manager import MultiThreadQueueManager
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

# Pydantic Schemas
class PromptBatchRequest(BaseModel):
    topic: str
    count: int = 10

class CloneVideoRequest(BaseModel):
    url: str

class SocialLoginRequest(BaseModel):
    platform: str

class SocialLogoutRequest(BaseModel):
    platform: str


class SettingsRequest(BaseModel):
    gemini_api_key: str
    max_concurrent_veo_jobs: int
    max_concurrent_processing: int
    max_concurrent_post_jobs: int

class SocialPostRequest(BaseModel):
    job_id: int
    platform: str

# Helper functions for reading/writing .env config
def read_env_values():
    env_path = BASE_DIR / ".env"
    values = {
        "GEMINI_API_KEY": "",
        "MAX_CONCURRENT_VEO_JOBS": "5",
        "MAX_CONCURRENT_PROCESSING": "4",
        "MAX_CONCURRENT_POST_JOBS": "2"
    }
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.strip().split("=", 1)
                        values[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            logger.error(f"Lỗi đọc .env: {e}")
    return values

def write_env_values(new_values: dict):
    env_path = BASE_DIR / ".env"
    current = read_env_values()
    current.update(new_values)
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in current.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        logger.error(f"Lỗi ghi .env: {e}")

def check_session_active(session_dir: Path) -> bool:
    if not session_dir.exists():
        return False
    # Playwright launch_persistent_context creates "Default" folder
    default_folder = session_dir / "Default"
    if default_folder.exists():
        # Check if there are files/folders inside
        try:
            return len(list(default_folder.iterdir())) > 0
        except Exception:
            return False
    try:
        return len(list(session_dir.iterdir())) > 0
    except Exception:
        return False

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

@app.get("/api/jobs")
def get_jobs(status: str = None, limit: int = 100):
    """Retrieve video jobs list from SQLite DB"""
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
    return {"status": "success", "count": len(jobs), "data": jobs}

@app.post("/api/generate-prompt")
def generate_prompt_batch(req: PromptBatchRequest, background_tasks: BackgroundTasks):
    """Generate batch of 10s video scripts & prompts from a topic"""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập chủ đề video")

    # Add jobs asynchronously
    def _create():
        queue_mgr.add_prompt_batch(req.topic.strip(), count=req.count)

    background_tasks.add_task(_create)
    return {
        "status": "success",
        "message": f"Đã nhận yêu cầu sinh {req.count} video kịch bản cho chủ đề: '{req.topic}'"
    }

@app.post("/api/clone-video")
def clone_video(req: CloneVideoRequest):
    """Add a TikTok/Reels clone video URL job"""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập link video")

    job_id = queue_mgr.add_clone_job(req.url.strip())
    return {
        "status": "success",
        "job_id": job_id,
        "message": f"Đã thêm Job Clone #{job_id} vào hàng chờ remake"
    }

@app.post("/api/engine/toggle")
def toggle_engine():
    """Start or Stop the multi-threaded Queue Worker Manager loop"""
    global engine_thread
    if queue_mgr.is_running:
        queue_mgr.stop()
        return {"status": "success", "is_running": False, "message": "Đã dừng Queue Manager đa luồng"}
    else:
        def _run():
            queue_mgr.start_loop(poll_interval_sec=5)

        engine_thread = threading.Thread(target=_run, daemon=True)
        engine_thread.start()
        return {"status": "success", "is_running": True, "message": "Đã khởi chạy Queue Manager đa luồng ngầm!"}

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
    """Clear persistent session context for social network platform(s)"""
    platform = req.platform.lower()
    success_platforms = []
    
    if platform in ["facebook", "all"]:
        if FacebookPublisher().logout():
            success_platforms.append("Facebook")
    if platform in ["tiktok", "all"]:
        if TikTokPublisher().logout():
            success_platforms.append("TikTok")
    if platform in ["x", "twitter", "all"]:
        if XPublisher().logout():
            success_platforms.append("X (Twitter)")

    if not success_platforms:
        raise HTTPException(status_code=400, detail="Không thể đăng xuất hoặc nền tảng không hợp lệ")

    return {
        "status": "success",
        "message": f"Đã đăng xuất thành công các tài khoản: {', '.join(success_platforms)}"
    }


@app.get("/api/social/status")
def get_social_status():
    """Get active login session status for FB, TikTok, X"""
    return {
        "status": "success",
        "data": {
            "facebook": check_session_active(FACEBOOK_SESSION_DIR),
            "tiktok": check_session_active(TIKTOK_SESSION_DIR),
            "x": check_session_active(X_SESSION_DIR)
        }
    }

@app.post("/api/social/post")
def social_post_now(req: SocialPostRequest, background_tasks: BackgroundTasks):
    """Publish video immediately in the background"""
    job = db.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy video job")
    
    if job['status'] not in [JobStatus.READY_TO_POST.value, JobStatus.PUBLISHED.value, JobStatus.FAILED.value]:
        raise HTTPException(status_code=400, detail="Video chưa sẵn sàng để đăng (đang xử lý hoặc render)")

    platform = req.platform.lower()
    if platform not in ["facebook", "tiktok", "x"]:
        raise HTTPException(status_code=400, detail="Mạng xã hội không hỗ trợ")

    def _post_task():
        # Temporarily mark as publishing in DB if appropriate
        db.update_job(req.job_id, status=JobStatus.PUBLISHING.value)
        video_path = Path(job['video_final_path'])
        caption = f"{job['title']}\n\n{job['voiceover_text']}"
        tags = job.get('tags', [])
        
        success = False
        if platform == "facebook":
            pub = FacebookPublisher()
            success = pub.post_video(video_path, caption, tags)
            if success:
                db.update_job(req.job_id, fb_posted=1)
        elif platform == "tiktok":
            pub = TikTokPublisher()
            success = pub.post_video(video_path, caption, tags)
            if success:
                db.update_job(req.job_id, tiktok_posted=1)
        elif platform == "x":
            pub = XPublisher()
            success = pub.post_video(video_path, caption, tags)
            if success:
                db.update_job(req.job_id, x_posted=1)

        # Update final job status
        updated_job = db.get_job(req.job_id)
        if updated_job.get('fb_posted') or updated_job.get('tiktok_posted') or updated_job.get('x_posted'):
            db.update_job(req.job_id, status=JobStatus.PUBLISHED.value)
        else:
            db.update_job(req.job_id, status=JobStatus.FAILED.value, error_msg=f"Đăng lên {platform} thất bại")

    background_tasks.add_task(_post_task)
    return {"status": "success", "message": f"Đang bắt đầu đăng Reels lên {req.platform} ngầm!"}

@app.get("/api/settings")
def get_settings():
    """Retrieve current thread & API settings"""
    vals = read_env_values()
    return {
        "status": "success",
        "data": {
            "gemini_api_key": vals.get("GEMINI_API_KEY", ""),
            "max_concurrent_veo_jobs": int(vals.get("MAX_CONCURRENT_VEO_JOBS", 5)),
            "max_concurrent_processing": int(vals.get("MAX_CONCURRENT_PROCESSING", 4)),
            "max_concurrent_post_jobs": int(vals.get("MAX_CONCURRENT_POST_JOBS", 2))
        }
    }

@app.post("/api/settings")
def save_settings(req: SettingsRequest):
    """Save thread & API configurations to .env file"""
    new_vals = {
        "GEMINI_API_KEY": req.gemini_api_key,
        "MAX_CONCURRENT_VEO_JOBS": str(req.max_concurrent_veo_jobs),
        "MAX_CONCURRENT_PROCESSING": str(req.max_concurrent_processing),
        "MAX_CONCURRENT_POST_JOBS": str(req.max_concurrent_post_jobs)
    }
    write_env_values(new_vals)
    return {"status": "success", "message": "Đã lưu cài đặt thành công! Cần khởi động lại server hoặc Engine để áp dụng."}

# Serve Static UI & Videos
UI_DIR = Path(__file__).resolve().parent / "ui"
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
app.mount("/videos", StaticFiles(directory=str(FINAL_DIR)), name="videos")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
