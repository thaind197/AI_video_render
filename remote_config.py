"""
Veo Studio AI PRO - Firebase Remote Config Manager
Sử dụng Firebase Remote Config REST API v1 với Service Account authentication.
Đọc parameters từ Firebase Console > Remote Config.
"""
import json
import gzip
import os
import time
import logging
import threading
import urllib.request
from pathlib import Path
from typing import Dict, Any

from version import __version__, parse_version

logger = logging.getLogger("RemoteConfig")

# ── Default Config (offline fallback) ────────────────────────────────────
DEFAULT_REMOTE_CONFIG = {
    "version": __version__,
    "min_version": __version__,
    "force_update": False,
    "system_maintenance": False,
    "app_enabled": True,
    "disabled_message": "Ứng dụng tạm thời bị vô hiệu hóa bởi Quản trị viên.",
    "download_url": "https://veostudio.ai/download",
    "update_message": "Phiên bản mới đã sẵn sàng. Vui lòng tải bản cập nhật!",
    "features": {
        "veo_generation": True,
        "facebook_upload": True,
        "tiktok_upload": True,
        "clone_video": True
    },
    "ttl_seconds": 30
}


def _find_service_account_path() -> str:
    """Tìm file service account JSON."""
    from config.settings import BASE_DIR

    candidates = [
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        str(BASE_DIR / "config" / "firebase_service_account.json"),
        str(BASE_DIR / "config" / "serviceAccountKey.json"),
        str(BASE_DIR / "firebase_service_account.json"),
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return ""


class RemoteConfigManager:
    """Singleton quản lý Firebase Remote Config.

    Đọc parameters từ Firebase Remote Config REST API v1.
    Cần file service account JSON để authenticate.

    Trên Firebase Console > Remote Config, tạo parameters:
      - version (string): "2.5.1" — phiên bản tối thiểu yêu cầu
      - force_update (string): "false"
      - system_maintenance (string): "false"
      - app_enabled (string): "true"
      - disabled_message (string): "..."
      - features (string/JSON): '{"veo_generation": true, ...}'
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RemoteConfigManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        self._cached_config: Dict[str, Any] = {}
        self._last_fetch_time: float = 0
        self._ttl: int = 300
        self._config_lock = threading.Lock()
        self._sa_path: str = ""
        self._project_id: str = ""
        self._credentials = None
        self._setup_credentials()

    def _setup_credentials(self):
        """Load service account và lấy project_id."""
        self._sa_path = _find_service_account_path()
        if not self._sa_path:
            logger.info("Không tìm thấy Firebase service account. Remote Config offline mode.")
            return

        try:
            with open(self._sa_path, "r", encoding="utf-8") as f:
                sa_data = json.load(f)
            self._project_id = sa_data.get("project_id", "")

            from google.oauth2 import service_account as sa_module
            self._credentials = sa_module.Credentials.from_service_account_file(
                self._sa_path,
                scopes=["https://www.googleapis.com/auth/firebase.remoteconfig"]
            )
            logger.info(f"Firebase credentials loaded: project={self._project_id}")
        except ImportError:
            logger.warning("Package 'google-auth' chưa cài. Chạy: pip install google-auth")
        except Exception as e:
            logger.warning(f"Lỗi load Firebase credentials: {e}")

    def _get_access_token(self) -> str:
        """Lấy hoặc refresh OAuth2 access token."""
        if not self._credentials:
            return ""
        try:
            from google.auth.transport.requests import Request
            if not self._credentials.valid:
                self._credentials.refresh(Request())
            return self._credentials.token or ""
        except Exception as e:
            logger.warning(f"Lỗi refresh access token: {e}")
            return ""

    def invalidate_cache(self) -> None:
        """Xóa cache để bắt buộc refetch."""
        with self._config_lock:
            self._last_fetch_time = 0
            self._cached_config = {}
        logger.info("Remote Config Cache đã bị Invalidate!")

    def _fetch_from_firebase(self) -> Dict[str, Any]:
        """Gọi Firebase Remote Config REST API v1 để lấy parameters."""
        if not self._project_id or not self._credentials:
            return {}

        token = self._get_access_token()
        if not token:
            return {}

        url = f"https://firebaseremoteconfig.googleapis.com/v1/projects/{self._project_id}/remoteConfig"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": f"VeoStudioAI/{__version__}",
        })

        resp = urllib.request.urlopen(req, timeout=8)
        raw = resp.read()

        # Handle gzip
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            body = gzip.decompress(raw).decode("utf-8")

        data = json.loads(body)
        parameters = data.get("parameters", {})

        # Parse parameters → config dict
        config = DEFAULT_REMOTE_CONFIG.copy()
        for key, param in parameters.items():
            raw_value = param.get("defaultValue", {}).get("value", "")
            if raw_value == "":
                continue
            config[key] = self._parse_value(key, raw_value)

        return config

    def _parse_value(self, key: str, raw: str):
        """Parse raw string value từ Remote Config thành kiểu phù hợp."""
        raw = str(raw).strip()

        # JSON objects
        if key in ("features", "settings_override", "revoked_devices"):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return DEFAULT_REMOTE_CONFIG.get(key, raw)

        # Booleans
        if key in ("force_update", "system_maintenance", "app_enabled"):
            return raw.lower() in ("true", "1", "yes")

        # Numbers
        if key == "ttl_seconds":
            try:
                return int(raw)
            except ValueError:
                return 300

        # Strings (version, min_version, download_url, etc.)
        return raw

    def fetch_remote_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """Lấy Remote Config: Firebase API → Cache → Default."""
        now = time.time()

        with self._config_lock:
            if not force_reload and self._cached_config and (now - self._last_fetch_time < self._ttl):
                return self._cached_config

        config = None

        # Gọi Firebase Remote Config REST API
        if self._project_id:
            try:
                config = self._fetch_from_firebase()
                logger.info(f"Đã lấy Remote Config từ Firebase (project: {self._project_id})")
            except Exception as e:
                logger.warning(f"Lỗi fetch Firebase Remote Config: {e}")

        # Fallback: cache cũ hoặc default
        if not config:
            with self._config_lock:
                if self._cached_config:
                    return self._cached_config
            return DEFAULT_REMOTE_CONFIG.copy()

        # Cập nhật TTL
        new_ttl = config.get("ttl_seconds", 300)
        if isinstance(new_ttl, (int, float)) and new_ttl > 0:
            self._ttl = int(new_ttl)

        with self._config_lock:
            self._cached_config = config
            self._last_fetch_time = now

        return config

    def check_app_status(self, force_reload: bool = False) -> Dict[str, Any]:
        """Kiểm tra trạng thái app: version check, kill switch, bảo trì.

        Logic chính:
        - Nếu version app < version từ Remote Config → BLOCK (force update)
        - Nếu app_enabled = false → BLOCK (kill switch)
        - Nếu system_maintenance = true → BLOCK (bảo trì)
        """
        config = self.fetch_remote_config(force_reload=force_reload)

        curr_version = __version__
        remote_version = str(config.get("version", curr_version))
        min_v = str(config.get("min_version", remote_version))
        download_url = str(config.get("download_url", "https://veostudio.ai/download"))
        update_msg = str(config.get("update_message", "Đã có phiên bản mới."))
        disabled_msg = str(config.get("disabled_message", "Ứng dụng bị vô hiệu hóa."))

        is_enabled = config.get("app_enabled", True)
        maintenance = config.get("system_maintenance", False)
        force_update = config.get("force_update", False)

        curr_tuple = parse_version(curr_version)
        remote_tuple = parse_version(remote_version)
        min_tuple = parse_version(min_v)

        is_blocked = False
        block_reason = ""

        # 1. Kill Switch: app_enabled = false
        if not is_enabled:
            is_blocked = True
            block_reason = disabled_msg

        # 2. Maintenance mode
        elif maintenance:
            is_blocked = True
            block_reason = "Hệ thống đang trong quá trình bảo trì. Vui lòng quay lại sau!"

        # 3. Version check: app version < remote "version" → BLOCK
        elif curr_tuple < remote_tuple:
            is_blocked = True
            block_reason = (
                f"{update_msg}\n\n"
                f"Phiên bản hiện tại: v{curr_version}\n"
                f"Phiên bản yêu cầu: v{remote_version}\n\n"
                f"Tải bản mới tại: {download_url}"
            )

        # 4. Force update check (nếu dùng min_version riêng)
        elif curr_tuple < min_tuple or force_update:
            is_blocked = True
            block_reason = (
                f"{update_msg}\n\n"
                f"Phiên bản hiện tại: v{curr_version}\n"
                f"Yêu cầu tối thiểu: v{min_v}"
            )

        return {
            "is_blocked": is_blocked,
            "block_reason": block_reason,
            "is_update_available": curr_tuple < remote_tuple,
            "current_version": curr_version,
            "remote_version": remote_version,
            "min_version": min_v,
            "latest_version": remote_version,
            "download_url": download_url,
            "update_message": update_msg,
            "system_maintenance": maintenance,
            "app_enabled": is_enabled,
            "checked_remote": self._last_fetch_time > 0,
            "last_checked_time": self._last_fetch_time,
            "features": config.get("features", {}),
            "settings_override": config.get("settings_override", {})
        }

    def is_feature_enabled(self, feature_name: str, default: bool = True) -> bool:
        """Kiểm tra feature flag từ Remote Config."""
        config = self.fetch_remote_config()
        features = config.get("features", {})
        return bool(features.get(feature_name, default))


# ── Helper ───────────────────────────────────────────────────────────────
def get_remote_config_manager() -> RemoteConfigManager:
    return RemoteConfigManager()
