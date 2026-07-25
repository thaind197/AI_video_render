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
        """Auto-add 'default' profile nếu chưa có trong config."""
        config = self._load_config()
        ids = [p["id"] for p in config.get("profiles", [])]
        if "default" not in ids:
            config.setdefault("profiles", []).insert(0, self.DEFAULT_PROFILE.copy())
            self._save_config(config)

    # ---------------------------------------------------------
    # Profile session dir resolution
    # ---------------------------------------------------------

    def get_session_dir(self, profile_id: str) -> Path:
        if profile_id == "default":
            return self._default_session_dir
        return self._profiles_dir / profile_id

    def is_logged_in(self, profile_id: str) -> bool:
        """True nếu session dir tồn tại và có dữ liệu (đã đăng nhập)."""
        session_dir = self.get_session_dir(profile_id)
        if not session_dir.exists():
            return False
        files = [f for f in session_dir.iterdir() if f.name != ".DS_Store"]
        return len(files) > 0

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
        }
        # Tạo thư mục session
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
        """Mở browser TOÀN MÀN HÌNH để user đăng nhập. Blocking."""
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
        pub.interactive_login("https://www.facebook.com/")

    def logout_profile(self, profile_id: str) -> bool:
        """Xóa session data của profile (logout)."""
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
