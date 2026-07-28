import os
import glob
import shutil
import logging
import platform
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

# Chromium args để tránh bị phát hiện automation
_CHROMIUM_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--no-sandbox',
    '--disable-infobars',
    '--disable-dev-shm-usage',
]

# Args để ẩn cửa sổ (đẩy ra ngoài màn hình — vẫn headless=False nên FB không detect)
_HIDDEN_ARGS = [
    '--window-position=-32000,-32000',
    '--window-size=1920,1080',
    '--disable-blink-features=AutomationControlled',
    '--no-sandbox',
    '--disable-infobars',
    '--disable-dev-shm-usage',
]


def check_session_has_cookies(session_dir: Path, min_size: int = 2000) -> bool:
    """Kiểm tra xem session_dir có chứa file Cookies hợp lệ từ Chromium hay không.

    Hỗ trợ cả Chromium cũ (Default/Cookies) và Chromium mới (Default/Network/Cookies).
    """
    if not session_dir or not session_dir.exists():
        return False

    candidate_paths = [
        session_dir / "Default" / "Network" / "Cookies",
        session_dir / "Default" / "Cookies",
        session_dir / "Network" / "Cookies",
        session_dir / "Cookies",
    ]
    for c_path in candidate_paths:
        if c_path.exists() and c_path.stat().st_size > min_size:
            return True

    try:
        for c_path in session_dir.glob("**/Cookies"):
            if c_path.is_file() and c_path.stat().st_size > min_size:
                return True
    except Exception:
        pass

    return False


class BasePublisher:
    """Base Class for Social Media Browser Automation using Playwright Persistent Session Context"""

    def __init__(self, platform_name: str, session_dir: Path):
        self.platform_name = platform_name
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def kill_orphaned_chrome(self, target_dir: Path = None):
        """Kill background chrome.exe processes locking session_dir - không dùng PowerShell."""
        try:
            dir_to_check = target_dir or self.session_dir
            # Xóa lock files trực tiếp thay vì kill process (an toàn hơn)
            for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
                lock_path = dir_to_check / lock_file
                if lock_path.exists():
                    try:
                        lock_path.unlink()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[{self.platform_name}] Lỗi cleanup lock files: {e}")

    def prepare_worker_session_dir(self, worker_id: int) -> Path:
        """Create an isolated worker session directory cloned from main session_dir."""
        if worker_id <= 0:
            return self.session_dir
        worker_dir = self.session_dir.parent / f"{self.session_dir.name}_workers" / f"worker_{worker_id}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self.session_dir.exists():
                for item in self.session_dir.iterdir():
                    if item.name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
                        continue
                    dest = worker_dir / item.name
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(item, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("Singleton*", "lockfile*"))
                        else:
                            shutil.copy2(item, dest)
        except Exception as ex:
            logger.warning(f"[{self.platform_name}] Lỗi sync worker session #{worker_id}: {ex}")
        return worker_dir

    def get_browser_context(self, p, headless: bool = False, hidden: bool = True, session_dir: Path = None) -> BrowserContext:
        """Get persistent browser context for automated posting (hidden background browser)."""
        target_dir = session_dir or self.session_dir
        self.kill_orphaned_chrome(target_dir)
        # Tự động xóa lock files còn sót từ phiên trước
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
            l_path = target_dir / lock_name
            if l_path.exists():
                try:
                    l_path.unlink()
                except Exception:
                    pass

        kwargs = {
            "user_data_dir": str(target_dir),
            "ignore_default_args": ["--enable-automation", "--password-store=basic", "--disable-component-extensions-with-background-pages"]
        }
        if os.path.exists(r"C:\Program Files\Google\Chrome\Application\chrome.exe") or os.path.exists(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
            kwargs["channel"] = "chrome"

        if headless:
            context = p.chromium.launch_persistent_context(
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                args=_CHROMIUM_ARGS,
                **kwargs
            )
        elif hidden:
            # OFF-SCREEN mode: headless=False (FB-compatible) nhưng cửa sổ ẩn
            context = p.chromium.launch_persistent_context(
                headless=False,
                no_viewport=True,
                args=_HIDDEN_ARGS,
                **kwargs
            )
            logger.info(f"[{self.platform_name}] Browser an (off-screen) - chay background.")
        else:
            context = p.chromium.launch_persistent_context(
                headless=False,
                no_viewport=True,
                args=_CHROMIUM_ARGS + ['--start-maximized'],
                **kwargs
            )
        return context

    def is_logged_in(self) -> bool:
        """Check if session directory exists and contains user browser data files"""
        if not self.session_dir.exists():
            return False
        if check_session_has_cookies(self.session_dir):
            return True
        files = [f for f in self.session_dir.iterdir() if f.name != ".DS_Store"]
        return len(files) > 0

    def logout(self) -> bool:
        """Clear session files by removing session_dir contents and recreating empty directory"""
        try:
            if self.session_dir.exists():
                shutil.rmtree(self.session_dir)
            self.session_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Da xoa phien dang nhap {self.platform_name}!")
            return True
        except Exception as e:
            logger.error(f"Loi xoa phien dang nhap {self.platform_name}: {e}")
            return False

    def interactive_login(self, login_url: str):
        """Mở trình duyệt để user đăng nhập thủ công."""
        def _p(msg):
            try:
                print(f"[interactive_login] {msg}", flush=True)
            except Exception:
                pass

        _p(f"START platform={self.platform_name}")
        _p(f"session_dir={self.session_dir}")
        _p(f"login_url={login_url}")

        # Xóa lock files còn sót từ session cũ
        for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = self.session_dir / lock_file
            if lock_path.exists():
                try:
                    lock_path.unlink()
                    _p(f"Removed lock: {lock_file}")
                except Exception:
                    pass

        try:
            from _login_browser import launch_login_browser
            launch_login_browser(str(self.session_dir.resolve()), login_url)
            _p("Đã hoàn tất interactive_login!")
        except Exception as e:
            _p(f"Lỗi interactive_login: {e}")
            raise


    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        raise NotImplementedError("Subclasses must implement post_video")
