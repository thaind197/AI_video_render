"""
Veo Studio AI PRO - Version & Remote Update Checker
"""
import logging
from typing import Dict, Any

__version__ = "2.5.3"
APP_NAME = "Veo Studio AI PRO"
FULL_NAME = f"{APP_NAME} v{__version__}"

logger = logging.getLogger("VersionChecker")

def parse_version(v_str: str):
    """Chuyển chuỗi version thành tuple số nguyên để so sánh chuẩn Semantic Versioning (vd: '2.5.0' -> (2, 5, 0))"""
    try:
        clean_str = str(v_str).strip().lstrip('vV')
        parts = [int(p) for p in clean_str.split('.') if p.isdigit()]
        return tuple(parts) if parts else (0, 0, 0)
    except Exception:
        return (0, 0, 0)

def check_remote_version() -> Dict[str, Any]:
    """
    Kiểm tra phiên bản ứng dụng từ Firebase Remote Config.
    Nếu version app < version trên Remote Config → app bị block.
    """
    try:
        from remote_config import get_remote_config_manager
        mgr = get_remote_config_manager()
        status_info = mgr.check_app_status()
        
        return {
            "current_version": __version__,
            "is_blocked": status_info.get("is_blocked", False),
            "block_reason": status_info.get("block_reason", ""),
            "is_update_available": status_info.get("is_update_available", False),
            "remote_version": status_info.get("remote_version", __version__),
            "min_version": status_info.get("min_version", __version__),
            "latest_version": status_info.get("latest_version", __version__),
            "download_url": status_info.get("download_url", "https://veostudio.ai/download"),
            "update_message": status_info.get("update_message", ""),
            "system_maintenance": status_info.get("system_maintenance", False),
            "checked_remote": status_info.get("checked_remote", False),
            "features": status_info.get("features", {})
        }
    except Exception as e:
        logger.warning(f"Lỗi kiểm tra remote version: {e}")
        return {
            "current_version": __version__,
            "is_blocked": False,
            "is_update_available": False,
            "remote_version": __version__,
            "min_version": __version__,
            "latest_version": __version__,
            "download_url": "https://veostudio.ai/download",
            "update_message": "",
            "system_maintenance": False,
            "checked_remote": False
        }

