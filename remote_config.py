"""
Veo Studio AI PRO - Remote Config & Invalidation Manager
Hỗ trợ Firebase Realtime Database REST API & Remote JSON Endpoints.
"""
import json
import urllib.request
import time
import logging
import threading
from typing import Dict, Any, Tuple
from version import __version__, parse_version

logger = logging.getLogger("RemoteConfig")

DEFAULT_REMOTE_CONFIG = {
    "app_status": {
        "is_enabled": True,
        "maintenance_mode": False,
        "disabled_message": "Ứng dụng tạm thời bị vô hiệu hóa bởi Quản trị viên."
    },
    "min_version": __version__,
    "latest_version": __version__,
    "download_url": "https://veostudio.ai/download",
    "update_message": "Phiên bản mới đã sẵn sàng. Vui lòng tải bản cập nhật!",
    "force_update": False,
    "system_maintenance": False,
    "features": {
        "veo_generation": True,
        "facebook_upload": True,
        "tiktok_upload": True,
        "clone_video": True
    },
    "revoked_devices": [],
    "settings_override": {},
    "ttl_seconds": 300
}


class RemoteConfigManager:
    """Singleton quản lý Cấu hình từ xa và Vô hiệu hóa (Invalidation) từ Firebase"""
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
        self._ttl: int = 300  # Mặc định 5 phút (300 giây)
        self._config_lock = threading.Lock()
        self.allow_offline = True

    def get_url(self, custom_url: str = None) -> str:
        if custom_url:
            return custom_url.strip()
        try:
            from config.settings import FIREBASE_VERSION_URL
            return FIREBASE_VERSION_URL.strip() if FIREBASE_VERSION_URL else ""
        except Exception:
            return ""

    def invalidate_cache(self) -> None:
        """Thao tác Invalidate: Xóa cache hoàn toàn để bắt buộc refetch từ Firebase"""
        with self._config_lock:
            self._last_fetch_time = 0
            self._cached_config = {}
        logger.info("Remote Config Cache đã bị Invalidate! Lần lấy cấu hình tiếp theo sẽ refetch từ Firebase.")

    def fetch_remote_config(self, custom_url: str = None, force_reload: bool = False) -> Dict[str, Any]:
        """
        Lấy Remote Config từ Firebase REST API hoặc Cache trong bộ nhớ.
        """
        now = time.time()
        url = self.get_url(custom_url)

        with self._config_lock:
            # Nếu chưa hết hạn TTL và không yêu cầu force_reload -> Trả về cache
            if not force_reload and self._cached_config and (now - self._last_fetch_time < self._ttl):
                return self._cached_config

        if not url:
            logger.debug("Không có FIREBASE_VERSION_URL, sử dụng Remote Config mặc định.")
            return DEFAULT_REMOTE_CONFIG.copy()

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"VeoStudioAI-RemoteConfig/{__version__}",
                    "Cache-Control": "no-cache"
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    raw_body = resp.read().decode('utf-8')
                    data = json.loads(raw_body)

                    if isinstance(data, dict):
                        merged_config = DEFAULT_REMOTE_CONFIG.copy()
                        merged_config.update(data)
                        
                        # Đảm bảo app_status hợp lệ
                        if "app_status" in data and isinstance(data["app_status"], dict):
                            merged_app_status = DEFAULT_REMOTE_CONFIG["app_status"].copy()
                            merged_app_status.update(data["app_status"])
                            merged_config["app_status"] = merged_app_status

                        # Đảm bảo features hợp lệ
                        if "features" in data and isinstance(data["features"], dict):
                            merged_features = DEFAULT_REMOTE_CONFIG["features"].copy()
                            merged_features.update(data["features"])
                            merged_config["features"] = merged_features

                        # Cập nhật TTL nếu có
                        new_ttl = merged_config.get("ttl_seconds", 300)
                        if isinstance(new_ttl, (int, float)) and new_ttl > 0:
                            self._ttl = int(new_ttl)

                        with self._config_lock:
                            self._cached_config = merged_config
                            self._last_fetch_time = now
                        
                        logger.info(f"Đã cập nhật thành công Remote Config từ Firebase: {url}")
                        return merged_config
        except Exception as e:
            logger.warning(f"Lỗi truy cập Firebase Remote Config ({url}): {e}")

        # Trường hợp lỗi mạng: sử dụng cache cũ nếu có, không thì trả về default
        with self._config_lock:
            if self._cached_config:
                return self._cached_config
        return DEFAULT_REMOTE_CONFIG.copy()

    def check_app_status(self, custom_url: str = None, force_reload: bool = False) -> Dict[str, Any]:
        """
        Kiểm tra toàn bộ trạng thái Vô hiệu hóa (Invalidation) và Cập nhật của Ứng dụng.
        """
        config = self.fetch_remote_config(custom_url=custom_url, force_reload=force_reload)
        url = self.get_url(custom_url)

        curr_version = __version__
        min_v = str(config.get("min_version", curr_version))
        latest_v = str(config.get("latest_version", curr_version))
        download_url = str(config.get("download_url", "https://veostudio.ai/download"))
        update_msg = str(config.get("update_message", "Đã có phiên bản mới."))
        
        app_status = config.get("app_status", {})
        is_enabled = bool(app_status.get("is_enabled", True))
        maintenance_mode = bool(app_status.get("maintenance_mode", False)) or bool(config.get("system_maintenance", False))
        disabled_msg = str(app_status.get("disabled_message", "Ứng dụng bị vô hiệu hóa từ xa bởi Quản trị viên."))
        force_update = bool(config.get("force_update", False))

        curr_tuple = parse_version(curr_version)
        min_tuple = parse_version(min_v)
        latest_tuple = parse_version(latest_v)

        is_blocked = False
        block_reason = ""

        # 1. Kiểm tra cờ Vô hiệu hóa trực tiếp (Kill Switch từ Firebase)
        if not is_enabled:
            is_blocked = True
            block_reason = disabled_msg
        # 2. Kiểm tra chế độ bảo trì hệ thống
        elif maintenance_mode:
            is_blocked = True
            block_reason = "Hệ thống đang trong quá trình bảo trì từ xa. Vui lòng quay lại sau!"
        # 3. Kiểm tra phiên bản bắt buộc (Force Update hoặc min_version)
        elif curr_tuple < min_tuple or force_update:
            is_blocked = True
            block_reason = f"{update_msg}\n\n(Phiên bản hiện tại: v{curr_version} | Yêu cầu tối thiểu: v{min_v})"

        is_update_avail = (curr_tuple < latest_tuple)

        return {
            "is_blocked": is_blocked,
            "block_reason": block_reason,
            "is_update_available": is_update_avail,
            "current_version": curr_version,
            "min_version": min_v,
            "latest_version": latest_v,
            "download_url": download_url,
            "update_message": update_msg,
            "system_maintenance": maintenance_mode,
            "app_enabled": is_enabled,
            "checked_remote": bool(url and self._last_fetch_time > 0),
            "last_checked_time": self._last_fetch_time,
            "features": config.get("features", {}),
            "settings_override": config.get("settings_override", {})
        }

    def is_feature_enabled(self, feature_name: str, default: bool = True) -> bool:
        """Kiểm tra xem một tính năng cụ thể có bị ngắt (invalidated) từ xa hay không"""
        config = self.fetch_remote_config()
        features = config.get("features", {})
        return bool(features.get(feature_name, default))


# Helper functions
def get_remote_config_manager() -> RemoteConfigManager:
    return RemoteConfigManager()
