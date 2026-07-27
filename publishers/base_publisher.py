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

    def kill_orphaned_chrome(self):
        """Kill background chrome.exe processes locking this session_dir"""
        try:
            norm_dir = str(self.session_dir.resolve()).lower().replace("/", "\\")
            cmd = [
                "powershell", "-NoProfile", "-Command",
                f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | Where-Object {{ $_.CommandLine -like '*{norm_dir}*' }} | Stop-Process -Force"
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception as e:
            logger.warning(f"[{self.platform_name}] Lỗi check orphan Chrome: {e}")

    def get_browser_context(self, p, headless: bool = False, hidden: bool = True) -> BrowserContext:
        """Get persistent browser context for automated posting (hidden background browser)."""
        self.kill_orphaned_chrome()
        # Tự động xóa lock files còn sót từ phiên trước
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
            l_path = self.session_dir / lock_name
            if l_path.exists():
                try:
                    l_path.unlink()
                except Exception:
                    pass

        kwargs = {
            "user_data_dir": str(self.session_dir),
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

        # Chay _login_browser.py nhu subprocess ngam (CREATE_NO_WINDOW) de khong hien cua so Console
        cmd = [python_exe, str(script_path), str(self.session_dir.resolve()), login_url]
        _p(f"Launching subprocess: {' '.join(cmd[:2])} ...")

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
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
