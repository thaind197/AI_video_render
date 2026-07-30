"""
Veo Studio AI PRO - Client Licensing Manager & Session Heartbeat Engine

Manages client-side authentication, hardware MAC ID binding verification,
and 60-second periodic heartbeat check with the Licensing Service.
"""

import json
import logging
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from config.settings import STORAGE_DIR, CENTRAL_SERVER_URL
from core.hardware import get_hardware_fingerprint
from core.licensing_service import LicensingService

logger = logging.getLogger("LicensingClient")

def _safe_log(level_fn, msg: str):
    try:
        level_fn(msg)
    except Exception:
        try:
            level_fn(msg.encode('ascii', errors='replace').decode('ascii'))
        except Exception:
            pass

AUTH_SESSION_FILE = STORAGE_DIR / "auth_session.json"


class LicensingClient:
    """Client-side licensing & session manager Singleton"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LicensingClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        self.service = LicensingService()
        self.hardware_info = get_hardware_fingerprint()
        self.mac_id = self.hardware_info["mac_id"]
        self.device_name = self.hardware_info["device_name"]
        self._cached_session: Optional[dict] = None
        self.load_session()

    def get_mac_id(self) -> str:
        return self.mac_id

    def load_session(self) -> Optional[dict]:
        """Load session data from local storage"""
        if AUTH_SESSION_FILE.exists():
            try:
                with open(AUTH_SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data and isinstance(data, dict) and data.get("token"):
                        self._cached_session = data
                        return data
            except Exception as e:
                _safe_log(logger.warning, f"Lỗi đọc auth_session.json: {e}")
        self._cached_session = None
        return None

    def save_session(self, session_data: dict):
        """Save active session to local storage"""
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(AUTH_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        self._cached_session = session_data

    def clear_session(self):
        """Logout and remove local session file"""
        self._cached_session = None
        if AUTH_SESSION_FILE.exists():
            try:
                AUTH_SESSION_FILE.unlink(missing_ok=True)
            except Exception:
                pass

    def login(self, email: str, password: str, license_key: str = "") -> dict:
        """Perform client login & MAC ID binding via Central Cloudflare Server (or local DB fallback)"""
        from config.settings import CENTRAL_SERVER_URL
        central_url = (CENTRAL_SERVER_URL or "").strip().rstrip('/')

        # 1. Gọi Máy chủ Trung tâm qua HTTP POST nếu CENTRAL_SERVER_URL được định nghĩa
        if central_url and (central_url.startswith("http://") or central_url.startswith("https://")):
            try:
                payload = {
                    "email": email,
                    "password": password,
                    "license_key": license_key,
                    "mac_id": self.mac_id,
                    "device_name": self.device_name
                }
                data_bytes = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    f"{central_url}/api/auth/login",
                    data=data_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": f"VeoStudioClient/3.1 (MAC:{self.mac_id})"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    if res.get("status") == "success":
                        session_payload = {
                            "token": res.get("token"),
                            "user": res.get("user"),
                            "license": res.get("license"),
                            "mac_id": self.mac_id,
                            "device_name": self.device_name,
                            "login_at": res.get("login_at")
                        }
                        self.save_session(session_payload)
                        _safe_log(logger.info, f"Logged in successfully via Central Server ({central_url}): user={email}, mac={self.mac_id}")
                    return res
            except urllib.error.HTTPError as e:
                try:
                    err_body = json.loads(e.read().decode('utf-8'))
                    msg = err_body.get("detail") or err_body.get("message") or f"Lỗi xác thực HTTP {e.code}"
                except Exception:
                    msg = f"Lỗi phản hồi từ Máy chủ Trung tâm (HTTP {e.code})"
                _safe_log(logger.warning, f"Central Login Failed HTTP {e.code}: {msg}")
                return {"status": "error", "message": msg}
            except urllib.error.URLError as e:
                _safe_log(logger.warning, f"Không thể kết nối Máy chủ Trung tâm ({central_url}): {e.reason}. Thử fallback database nội bộ...")
            except Exception as ex:
                _safe_log(logger.warning, f"Lỗi kết nối Máy chủ Trung tâm ({ex}). Thử fallback database nội bộ...")

        # 2. Local Database Service Fallback
        res = self.service.authenticate_client(
            email=email,
            password=password,
            license_key=license_key,
            mac_id=self.mac_id,
            device_name=self.device_name
        )

        if res.get("status") == "success":
            session_payload = {
                "token": res.get("token"),
                "user": res.get("user"),
                "license": res.get("license"),
                "mac_id": self.mac_id,
                "device_name": self.device_name,
                "login_at": res.get("login_at")
            }
            self.save_session(session_payload)
            logger.info(f"✅ Registered & Logged in successfully via Local DB: user={email}, mac={self.mac_id}")

        return res

    def logout(self) -> bool:
        self.clear_session()
        return True

    def is_authenticated(self) -> bool:
        """Check if local session exists"""
        session = self.load_session()
        return bool(session and session.get("token"))

    def get_current_user(self) -> Optional[dict]:
        session = self.load_session()
        if session:
            return session.get("user")
        return None

    def get_current_license(self) -> Optional[dict]:
        session = self.load_session()
        if session:
            return session.get("license")
        return None

    def verify_heartbeat(self) -> dict:
        """Perform heartbeat verification call against central licensing service or local DB.
        If invalid, clears session.
        """
        session = self.load_session()
        if not session:
            return {"valid": False, "reason": "Chưa đăng nhập ứng dụng."}

        user = session.get("user", {})
        license_info = session.get("license", {})

        from config.settings import CENTRAL_SERVER_URL
        central_url = (CENTRAL_SERVER_URL or "").strip().rstrip('/')
        if central_url and (central_url.startswith("http://") or central_url.startswith("https://")):
            try:
                user_id = user.get("id", "")
                lic_id = license_info.get("id", "")
                url = f"{central_url}/api/auth/heartbeat?user_id={user_id}&license_id={lic_id}&mac_id={self.mac_id}"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": f"VeoStudioClient/3.1 (MAC:{self.mac_id})"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    if res and res.get("valid") is True:
                        return res
                    logger.warning(f"⚠️ Central Session Heartbeat response invalid: {res.get('reason') if res else 'Unknown'}. Falling back to local check...")
            except Exception as e:
                logger.warning(f"Central heartbeat connection error ({e}), fall back to local check.")

        # Local check
        res = self.service.verify_token_and_mac(
            user_id=user.get("id"),
            license_id=license_info.get("id"),
            mac_id=self.mac_id
        )

        if not res.get("valid"):
            logger.warning(f"⚠️ Session Heartbeat Failed: {res.get('reason')}. Logging out...")
            self.clear_session()

        return res


if __name__ == "__main__":
    client = LicensingClient()
    print("=== Client Hardware MAC ID ===")
    print("MAC ID:", client.get_mac_id())
    print("Is Authenticated:", client.is_authenticated())

