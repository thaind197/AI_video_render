"""
Veo Studio AI PRO - Dedicated Web Admin & Licensing Server
Standalone FastAPI Server for Cloud/VPS Web Admin Management & Central Database.
"""
import os
import sys
import logging
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import BASE_DIR, POSTGRES_URL
from core.licensing_service import LicensingService

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("AdminServer")

lic_service = LicensingService(postgres_url=POSTGRES_URL)

app = FastAPI(
    title="Veo Studio AI - Web Admin & Licensing Server",
    description="Dedicated Web Admin Panel & Central Licensing Authentication Server",
    version="3.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Request Models ────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    email: str
    password: str

class AdminCreateLicenseRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    tier: str = "pro"
    max_devices: int = 1
    valid_days: int = 30
    allowed_modules: Optional[List[str]] = None

class AdminUpdateModulesRequest(BaseModel):
    allowed_modules: List[str]

class AdminResetPasswordRequest(BaseModel):
    new_password: str

class AppLoginRequest(BaseModel):
    email: str
    password: str
    license_key: Optional[str] = ""
    mac_id: Optional[str] = None


# ── Auth & License Endpoints for Desktop Clients ──────────────────────────
@app.get("/api/auth/status")
def auth_status(request: Request):
    user_agent = request.headers.get("user-agent", "")
    mac_id = lic_service.get_mac_from_request(user_agent)
    is_registered = lic_service.is_mac_registered(mac_id)
    return {
        "authenticated": False,
        "is_mac_registered": is_registered,
        "mac_id": mac_id,
        "user": None,
        "license": None
    }

@app.post("/api/auth/login")
def client_login(req: AppLoginRequest, request: Request):
    user_agent = request.headers.get("user-agent", "")
    mac_id = req.mac_id or lic_service.get_mac_from_request(user_agent)
    res = lic_service.authenticate_client(
        email=req.email,
        password=req.password,
        license_key=req.license_key or "",
        mac_id=mac_id
    )
    if res.get("status") != "success":
        raise HTTPException(status_code=400, detail=res.get("message", "Đăng nhập thất bại"))
    return res

@app.get("/api/auth/heartbeat")
def client_heartbeat(user_id: Optional[str] = None, license_id: Optional[str] = None, mac_id: Optional[str] = None, request: Request = None):
    ua_mac = lic_service.get_mac_from_request(request.headers.get("user-agent", "")) if request else ""
    target_mac = mac_id or ua_mac
    if user_id and license_id and target_mac:
        return lic_service.verify_token_and_mac(user_id, license_id, target_mac)
    return lic_service.validate_heartbeat(target_mac)


# ── Admin Web Control Endpoints ───────────────────────────────────────────
@app.post("/api/admin/login")
def admin_login(req: AdminLoginRequest):
    res = lic_service.authenticate_admin(req.email, req.password)
    if res.get("status") != "success":
        raise HTTPException(status_code=401, detail=res.get("message", "Đăng nhập Admin thất bại"))
    return res

@app.get("/api/admin/stats")
def admin_stats():
    return lic_service.get_admin_dashboard_stats()

@app.get("/api/admin/licenses")
def admin_list_licenses():
    return {"status": "success", "licenses": lic_service.list_all_licenses()}

@app.post("/api/admin/licenses")
def admin_create_license(req: AdminCreateLicenseRequest):
    res = lic_service.create_user_and_license(
        email=req.email,
        password=req.password,
        full_name=req.full_name,
        tier=req.tier,
        max_devices=req.max_devices,
        valid_days=req.valid_days,
        allowed_modules=req.allowed_modules
    )
    if res.get("status") != "success":
        raise HTTPException(status_code=400, detail=res.get("message", "Tạo License thất bại"))
    return res

@app.post("/api/admin/licenses/{license_id}/modules")
def admin_update_license_modules(license_id: str, req: AdminUpdateModulesRequest):
    ok = lic_service.update_license_modules(license_id, req.allowed_modules)
    if not ok:
        raise HTTPException(status_code=500, detail="Không thể cập nhật danh sách module")
    return {"status": "success", "message": "Đã cập nhật quyền module thành công!"}

@app.post("/api/admin/licenses/{license_id}/reset-mac")
def admin_reset_mac(license_id: str):
    ok = lic_service.reset_license_devices(license_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Không thể gỡ MAC ID")
    return {"status": "success", "message": "Đã reset toàn bộ thiết bị (MAC ID) cho License thành công!"}

@app.post("/api/admin/users/{user_id}/block")
def admin_toggle_block(user_id: str, block: bool = True):
    ok = lic_service.toggle_user_block(user_id, block)
    if not ok:
        raise HTTPException(status_code=500, detail="Không thể cập nhật trạng thái user")
    action_text = "khóa" if block else "mở khóa"
    return {"status": "success", "message": f"Đã {action_text} tài khoản thành công!"}

@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_user_password(user_id: str, req: AdminResetPasswordRequest):
    res = lic_service.reset_user_password(user_id, req.new_password)
    if res.get("status") != "success":
        raise HTTPException(status_code=400, detail=res.get("message", "Đổi mật khẩu thất bại"))
    return res


@app.get("/api/admin/prompt-history")
def admin_prompt_history(limit: int = 50):
    return {"status": "success", "history": lic_service.get_prompt_history(limit=limit)}


# ── Mount Web Admin Static Frontend ───────────────────────────────────────
ADMIN_DIR = BASE_DIR / "admin"
if not ADMIN_DIR.exists():
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/")
def root():
    return RedirectResponse(url="/admin/")

app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
