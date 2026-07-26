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


class BasePublisher:
    """Base Class for Social Media Browser Automation using Playwright Persistent Session Context"""

    def __init__(self, platform_name: str, session_dir: Path):
        self.platform_name = platform_name
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def get_browser_context(self, p, headless: bool = False, hidden: bool = True) -> BrowserContext:
        """Get persistent browser context for automated posting (hidden background browser).

        Args:
            headless: True = headless mode (NOT recommended for Facebook).
            hidden:   True = off-screen (background posting). False = visible.

        NOTE: For LOGIN, use interactive_login() which launches a separate process.
        """
        if headless:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                args=_CHROMIUM_ARGS,
            )
        elif hidden:
            # OFF-SCREEN mode: headless=False (FB-compatible) nhưng cửa sổ ẩn
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=False,
                no_viewport=True,
                args=_HIDDEN_ARGS,
            )
            logger.info(f"[{self.platform_name}] Browser an (off-screen) - chay background.")
        else:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=False,
                no_viewport=True,
                args=_CHROMIUM_ARGS + ['--start-maximized'],
            )
        return context

    def is_logged_in(self) -> bool:
        """Check if session directory exists and contains user browser data files"""
        if not self.session_dir.exists():
            return False
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
        """Mo trinh duyet de user dang nhap thu cong.

        Chay _login_browser.py nhu SUBPROCESS RIENG BIET de dam bao:
        - Playwright chay trong process moi (khong bi conflict voi thread)
        - Browser window LUON hien tren man hinh
        - Moi profile co session_dir rieng -> session doc lap
        """
        def _p(msg):
            try:
                print(f"[interactive_login] {msg}", flush=True)
            except Exception:
                pass

        _p(f"START platform={self.platform_name}")
        _p(f"session_dir={self.session_dir}")
        _p(f"login_url={login_url}")

        # Xoa lock files con sot tu session cu
        for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = self.session_dir / lock_file
            if lock_path.exists():
                try:
                    lock_path.unlink()
                    _p(f"Removed lock: {lock_file}")
                except Exception:
                    pass

        # Tim duong dan python.exe dang chay
        python_exe = sys.executable
        _p(f"Python: {python_exe}")

        # Tim _login_browser.py (cung thu muc voi server.py)
        script_path = Path(__file__).parent.parent / "_login_browser.py"
        if not script_path.exists():
            # Fallback: tim trong current working dir
            script_path = Path("_login_browser.py")
        if not script_path.exists():
            _p(f"ERROR: _login_browser.py not found at {script_path}")
            raise FileNotFoundError(f"_login_browser.py not found")

        _p(f"Script: {script_path}")

        # Chay _login_browser.py nhu subprocess rieng biet
        # KHONG dung CREATE_NEW_CONSOLE de output van hien trong server console
        cmd = [python_exe, str(script_path), str(self.session_dir), login_url]
        _p(f"Launching subprocess: {' '.join(cmd[:2])} ...")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=sys.stdout,   # Forward output ve server console
                stderr=sys.stderr,
            )
            _p(f"Subprocess PID={proc.pid} - cho user dang nhap va dong browser...")

            # BLOCKING: cho den khi _login_browser.py thoat (user dong browser)
            proc.wait(timeout=660)  # 11 phut (script co timeout 10 phut)

            _p(f"Subprocess exited. PID={proc.pid} exitCode={proc.returncode}")
        except subprocess.TimeoutExpired:
            _p("Timeout - killing subprocess")
            proc.kill()
            proc.wait()
        except Exception as e:
            _p(f"ERROR: {e}")
            raise

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        raise NotImplementedError("Subclasses must implement post_video")
