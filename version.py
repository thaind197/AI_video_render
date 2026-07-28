"""
Veo Studio AI PRO - Version & Remote Update Checker
"""
import json
import urllib.request
import logging

__version__ = "2.5.0"
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

def check_remote_version(custom_url: str = None):
    """
    Kiểm tra phiên bản ứng dụng từ Firebase Realtime Database REST API hoặc Remote JSON URL.
    Trả về dict chứa trạng thái kiểm tra và cờ is_blocked.
    """
    # Lấy URL cấu hình từ settings hoặc custom_url
    target_url = custom_url
    if not target_url:
        try:
            from config.settings import FIREBASE_VERSION_URL
            target_url = FIREBASE_VERSION_URL
        except Exception:
            target_url = ""

    result = {
        "current_version": __version__,
        "is_blocked": False,
        "is_update_available": False,
        "min_version": __version__,
        "latest_version": __version__,
        "download_url": "https://veostudio.ai/download",
        "update_message": "",
        "system_maintenance": False,
        "checked_remote": False
    }

    if not target_url or not target_url.strip():
        return result

    try:
        req = urllib.request.Request(
            target_url.strip(),
            headers={"User-Agent": "VeoStudioAI-VersionChecker/2.5"}
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                raw_body = resp.read().decode('utf-8')
                data = json.loads(raw_body)
                if isinstance(data, dict):
                    result["checked_remote"] = True
                    
                    min_v = str(data.get("min_version", __version__))
                    latest_v = str(data.get("latest_version", __version__))
                    download_url = str(data.get("download_url", "https://veostudio.ai/download"))
                    msg = str(data.get("update_message", "Phiên bản ứng dụng đã hết hạn. Vui lòng tải bản cập nhật mới!"))
                    maint = bool(data.get("system_maintenance", False))
                    force = bool(data.get("force_update", False))

                    result["min_version"] = min_v
                    result["latest_version"] = latest_v
                    result["download_url"] = download_url
                    result["update_message"] = msg
                    result["system_maintenance"] = maint

                    curr_tuple = parse_version(__version__)
                    min_tuple = parse_version(min_v)
                    latest_tuple = parse_version(latest_v)

                    # Điều kiện CHẶN ứng dụng:
                    # 1. Phiên bản hiện tại nhỏ hơn min_version
                    # 2. Hoặc cờ force_update = true
                    # 3. Hoặc hệ thống đang trong chế độ bảo trì system_maintenance = true
                    if curr_tuple < min_tuple or force or maint:
                        result["is_blocked"] = True
                    
                    if curr_tuple < latest_tuple:
                        result["is_update_available"] = True
    except Exception as e:
        logger.warning(f"Không thể kết nối Remote Version Check ({target_url}): {e}")

    return result
