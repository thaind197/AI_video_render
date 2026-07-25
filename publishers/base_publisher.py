import os
import shutil
import logging
import platform
import subprocess
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
    '--window-position=-32000,-32000',   # Đẩy cửa sổ ra ngoài màn hình
    '--window-size=1920,1080',
    '--disable-blink-features=AutomationControlled',
    '--no-sandbox',
    '--disable-infobars',
    '--disable-dev-shm-usage',
]

def _hide_chromium_window_macos():
    """Dùng osascript để minimize cửa sổ Chromium trên macOS."""
    try:
        script = 'tell application "Chromium" to set miniaturized of every window to true'
        subprocess.Popen(['osascript', '-e', script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class BasePublisher:
    """Base Class for Social Media Browser Automation using Playwright Persistent Session Context"""

    def __init__(self, platform_name: str, session_dir: Path):
        self.platform_name = platform_name
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def get_browser_context(self, p, headless: bool = False, hidden: bool = True) -> BrowserContext:
        """Get persistent browser context.

        Args:
            headless: True = headless mode (NOT recommended for Facebook — hides file inputs).
            hidden:   True = visible browser BUT đẩy cửa sổ ra ngoài màn hình (khuyến nghị).
                      False = cửa sổ toàn màn hình (dùng để debug hoặc đăng nhập).

        NOTE: Facebook REQUIRES headless=False to render file upload inputs.
        Use hidden=True for background posting — browser chạy ẩn mà FB không detect.
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
            # macOS: minimize via osascript ngay sau khi mở
            if platform.system() == "Darwin":
                import threading
                threading.Timer(2.0, _hide_chromium_window_macos).start()
            logger.info(f"[{self.platform_name}] Browser ẩn (off-screen) — chạy background.")
        else:
            # VISIBLE / FULLSCREEN mode: dùng cho login hoặc debug
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=False,
                no_viewport=True,
                args=_CHROMIUM_ARGS + ['--start-maximized'],
            )
            logger.info(f"[{self.platform_name}] Browser toàn màn hình.")
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
            logger.info(f"Đã xóa thành công phiên đăng nhập {self.platform_name}!")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi xóa phiên đăng nhập {self.platform_name}: {e}")
            return False

    def interactive_login(self, login_url: str):
        """Open FULLSCREEN visible browser window for user to manually log in once and save session"""
        logger.info(f"Đang mở trình duyệt TOÀN MÀN HÌNH để bạn đăng nhập {self.platform_name}...")
        try:
            with sync_playwright() as p:
                # Always headless=False + maximized for login
                context = self.get_browser_context(p, headless=False)
                page = context.new_page()
                # Maximize via JS as fallback
                try:
                    page.evaluate("window.moveTo(0,0); window.resizeTo(screen.availWidth, screen.availHeight);")
                except Exception:
                    pass
                page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                logger.info(
                    f"✅ Trình duyệt {self.platform_name} đã mở TOÀN MÀN HÌNH. "
                    "Hãy đăng nhập và ĐÓNG CỬA SỔ TRÌNH DUYỆT khi hoàn tất."
                )

                # Wait until user closes the page window (up to 10 minutes)
                try:
                    page.wait_for_event("close", timeout=600000)
                except Exception:
                    pass

                context.close()
                logger.info(f"✅ Đã lưu phiên đăng nhập {self.platform_name}!")
        except Exception as e:
            logger.exception(f"Lỗi mở trình duyệt đăng nhập {self.platform_name}: {e}")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        raise NotImplementedError("Subclasses must implement post_video")
