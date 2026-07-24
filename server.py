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

# Serve Static UI & Videos
UI_DIR = Path(__file__).resolve().parent / "ui"
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
app.mount("/videos", StaticFiles(directory=str(FINAL_DIR)), name="videos")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
