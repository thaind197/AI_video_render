"""
FBProfileManager — Quản lý nhiều Facebook profiles (multi-account)

Mỗi profile = 1 folder session riêng biệt cho Playwright Chromium.
Cho phép đăng nhập 1 lần / profile, sau đó đăng video đồng thời (parallel).
"""
import json
import uuid
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from publishers.base_publisher import check_session_has_cookies

logger = logging.getLogger(__name__)


class FBProfileManager:
    """
    Quản lý nhiều Facebook browser session profiles.

    Profile structure:
      storage/browser_sessions/
        facebook/               <- legacy "default" profile session
        facebook_profiles/
          <profile_id>/         <- session dir cho mỗi profile mới
      storage/fb_profiles.json  <- metadata JSON

    Usage:
        mgr = FBProfileManager()
        mgr.create_profile("Fanpage 2")
        mgr.login_profile("abc123")
        mgr.post_to_profiles_parallel(video_path, caption, ["default", "abc123"])
    """

    DEFAULT_PROFILE = {
        "id": "default",
        "name": "Mặc Định",
        "created_at": datetime.now().isoformat(),
    }

    def __init__(self):
        from config.settings import (
            FACEBOOK_SESSION_DIR,
            FACEBOOK_PROFILES_DIR,
            FACEBOOK_PROFILES_CONFIG,
        )
        self._default_session_dir = FACEBOOK_SESSION_DIR
        self._profiles_dir = FACEBOOK_PROFILES_DIR
        self._config_path = FACEBOOK_PROFILES_CONFIG
        self._lock = threading.Lock()
        self._ensure_default_profile()

    # ---------------------------------------------------------
    # Config helpers
    # ---------------------------------------------------------

    def _load_config(self) -> dict:
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"profiles": []}

    def _save_config(self, config: dict):
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def _ensure_default_profile(self):
        """Auto-add 'default' profile nếu chưa có. Migration: thêm field logged_in cho profiles cũ."""
        config = self._load_config()
        changed = False
        ids = [p["id"] for p in config.get("profiles", [])]

        # Thêm default nếu chưa có
        if "default" not in ids:
            config.setdefault("profiles", []).insert(0, self.DEFAULT_PROFILE.copy())
            changed = True

        # Migration: thêm field logged_in cho profiles cũ chưa có hoặc chưa nhận diện đúng
        for p in config.get("profiles", []):
            sess = self.get_session_dir(p["id"])
            has_cookies = check_session_has_cookies(sess)
            if "logged_in" not in p or (not p.get("logged_in") and has_cookies):
                p["logged_in"] = has_cookies
                changed = True

        if changed:
            self._save_config(config)

    # ---------------------------------------------------------
    # Profile session dir resolution
    # ---------------------------------------------------------

    def get_session_dir(self, profile_id: str) -> Path:
        if profile_id == "default":
            return self._default_session_dir
        return self._profiles_dir / profile_id

    def is_logged_in(self, profile_id: str) -> bool:
        """True nếu profile đã đăng nhập (đọc từ JSON config hoặc kiểm tra cookies thực tế)."""
        config = self._load_config()
        for p in config.get("profiles", []):
            if p["id"] == profile_id:
                if p.get("logged_in", False):
                    return True
                # Fallback: kiểm tra cookies thực tế trên đĩa (nếu config chưa sync)
                sess = self.get_session_dir(profile_id)
                if check_session_has_cookies(sess):
                    self._set_login_status(profile_id, True)
                    return True
                return False
        return False

    def _set_login_status(self, profile_id: str, logged_in: bool):
        """Cập nhật trạng thái logged_in trong JSON config."""
        with self._lock:
            config = self._load_config()
            for p in config.get("profiles", []):
                if p["id"] == profile_id:
                    p["logged_in"] = logged_in
                    break
            self._save_config(config)

    # ---------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------

    def list_profiles(self) -> list:
        """Trả về tất cả profiles kèm trạng thái đăng nhập."""
        config = self._load_config()
        result = []
        for p in config.get("profiles", []):
            result.append({
                **p,
                "logged_in": self.is_logged_in(p["id"]),
            })
        return result

    def create_profile(self, name: str) -> dict:
        """Tạo profile mới. Trả về profile dict."""
        profile_id = uuid.uuid4().hex[:8]
        now = datetime.now().isoformat()
        profile = {
            "id": profile_id,
            "name": name.strip() or f"Profile {profile_id[:4]}",
            "created_at": now,
            "logged_in": False,   # Explicit: chưa đăng nhập
        }
        # Tạo thư mục session (sẽ trống cho đến khi user thực sự login)
        session_dir = self.get_session_dir(profile_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            config = self._load_config()
            config.setdefault("profiles", []).append(profile)
            self._save_config(config)

        logger.info(f"[FBProfileManager] Tạo profile '{profile['name']}' id={profile_id}")
        return {**profile, "logged_in": False}

    def delete_profile(self, profile_id: str) -> bool:
        """Xóa profile + toàn bộ session data. Không thể xóa 'default'."""
        if profile_id == "default":
            logger.warning("[FBProfileManager] Không thể xóa profile 'default'")
            return False

        with self._lock:
            config = self._load_config()
            before = len(config.get("profiles", []))
            config["profiles"] = [p for p in config["profiles"] if p["id"] != profile_id]
            if len(config["profiles"]) == before:
                return False
            self._save_config(config)

        # Xóa session dir
        session_dir = self.get_session_dir(profile_id)
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)

        logger.info(f"[FBProfileManager] Đã xóa profile {profile_id}")
        return True

    def get_profile(self, profile_id: str):
        config = self._load_config()
        for p in config.get("profiles", []):
            if p["id"] == profile_id:
                return {**p, "logged_in": self.is_logged_in(profile_id)}
        return None

    # ---------------------------------------------------------
    # Login / Logout
    # ---------------------------------------------------------

    def login_profile(self, profile_id: str):
        """Mở browser TOÀN MÀN HÌNH để user đăng nhập. Blocking.

        Sau khi user đóng cửa sổ browser, tự động set logged_in=True trong config.
        """
        from publishers.base_publisher import BasePublisher

        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile không tồn tại: {profile_id}")

        session_dir = self.get_session_dir(profile_id)
        pub = BasePublisher(
            platform_name=f"Facebook [{profile['name']}]",
            session_dir=session_dir,
        )
        logger.info(f"[FBProfileManager] Mở browser đăng nhập: {profile['name']}")

        # Reset trạng thái trước khi mở browser
        self._set_login_status(profile_id, False)

        # Mở browser — BLOCKING cho đến khi user đóng cửa sổ
        pub.interactive_login("https://www.facebook.com/")

        # Chỉ set logged_in=True SAU KHI user đóng browser (interactive_login đã return)
        # Kiểm tra session dir có dữ liệu thực sự (Cookies file từ Chromium)
        if check_session_has_cookies(session_dir):
            self._set_login_status(profile_id, True)
            logger.info(f"[FBProfileManager] Đã lưu session login: {profile['name']}")
        else:
            logger.warning(f"[FBProfileManager] Browser đóng nhưng không tìm thấy cookie — có thể chưa login: {profile['name']}")

    def logout_profile(self, profile_id: str) -> bool:
        """Xóa session data của profile (logout)."""
        # Set logged_in=False trước
        self._set_login_status(profile_id, False)
        # Xóa session dir để clear cookies/data
        session_dir = self.get_session_dir(profile_id)
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            session_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[FBProfileManager] Đã logout profile {profile_id}")
            return True
        return False

    # ---------------------------------------------------------
    # Parallel Posting
    # ---------------------------------------------------------

    def post_to_profiles_parallel(
        self,
        video_path: Path,
        caption: str,
        profile_ids: list,
        max_workers: int = 3,
        on_result=None,
        tags: list = None,
    ) -> dict:
        """
        Đăng video lên nhiều profiles ĐỒNG THỜI bằng ThreadPoolExecutor.

        Mỗi profile chạy Playwright trong 1 thread riêng (không xung đột).
        Browser ẩn (off-screen) nên không hiện ra màn hình.

        Args:
            video_path:  Path đến file video
            caption:     Caption/mô tả bài đăng
            profile_ids: Danh sách profile_id cần đăng
            max_workers: Số browser chạy đồng thời (default 3, tối đa ~5)
            on_result:   Callback(profile_id, success: bool, error: str | None)
            tags:        Hashtags (optional)

        Returns:
            dict {profile_id: True/False}
        """
        results = {}

        def _post_one(profile_id: str):
            from publishers.facebook_publisher import FacebookPublisher
            profile = self.get_profile(profile_id)
            pname = profile["name"] if profile else profile_id
            logger.info(f"[Thread-{profile_id}] Bắt đầu đăng: {pname}")
            try:
                pub = FacebookPublisher(profile_id=profile_id)
                ok = pub.post_video(video_path, caption, tags)
                logger.info(f"[Thread-{profile_id}] {'OK' if ok else 'FAIL'}: {pname}")
                return (profile_id, ok, None)
            except Exception as e:
                logger.exception(f"[Thread-{profile_id}] Lỗi: {e}")
                return (profile_id, False, str(e))

        logger.info(
            f"[FBProfileManager] Bắt đầu parallel: {len(profile_ids)} profiles, "
            f"max_workers={max_workers}, video={video_path.name}"
        )

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fbpost") as pool:
            futures = {
                pool.submit(_post_one, pid): pid
                for pid in profile_ids
            }
            for future in as_completed(futures):
                pid, ok, err = future.result()
                results[pid] = ok
                if on_result:
                    try:
                        on_result(pid, ok, err)
                    except Exception:
                        pass

        success_count = sum(1 for v in results.values() if v)
        logger.info(
            f"[FBProfileManager] Xong: {success_count}/{len(profile_ids)} profiles thanh cong"
        )
        return results
