import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

class BasePublisher:
    """Base Class for Social Media Browser Automation using Playwright Persistent Session Context"""

    def __init__(self, platform_name: str, session_dir: Path):
        self.platform_name = platform_name
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def get_browser_context(self, p, headless: bool = True) -> BrowserContext:
        """Get persistent browser context so user logins are saved across runs"""
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(self.session_dir),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        return context

    def interactive_login(self, login_url: str):
        """Open visible browser window for user to manually log in once and save session"""
        logger.info(f"Đang mở trình duyệt để bạn đăng nhập {self.platform_name}...")
        try:
            with sync_playwright() as p:
                context = self.get_browser_context(p, headless=False)
                page = context.new_page()
                page.goto(login_url)
                print(f"\n=======================================================")
                print(f"[THÔNG BÁO] Trình duyệt {self.platform_name} đang mở.")
                print(f"Hãy đăng nhập tài khoản của bạn trên trình duyệt.")
                print(f"Sau khi hoàn tất đăng nhập, hãy TẮT trình duyệt để tự động lưu Session.")
                print(f"=======================================================\n")
                
                # Wait until the browser page is closed by the user
                while not page.is_closed():
                    time.sleep(0.5)
                
                try:
                    context.close()
                except Exception:
                    pass
                logger.info(f"Đã lưu thành công phiên đăng nhập {self.platform_name}!")
        except Exception as e:
            logger.error(f"Lỗi khi mở trình duyệt đăng nhập {self.platform_name}: {e}")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        raise NotImplementedError("Subclasses must implement post_video")

    def logout(self) -> bool:
        """Clear browser persistent session data to log out user"""
        logger.info(f"Đang xóa phiên đăng nhập {self.platform_name}...")
        try:
            if self.session_dir.exists():
                import shutil
                shutil.rmtree(self.session_dir, ignore_errors=True)
                self.session_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Đã đăng xuất thành công khỏi {self.platform_name}!")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi xóa phiên đăng nhập {self.platform_name}: {e}")
            return False

