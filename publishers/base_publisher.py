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
        with sync_playwright() as p:
            context = self.get_browser_context(p, headless=False)
            page = context.new_page()
            page.goto(login_url)
            print(f"\n=======================================================")
            print(f"[THÔNG BÁO] Trình duyệt {self.platform_name} đang mở.")
            print(f"Hãy đăng nhập tài khoản của bạn trên trình duyệt.")
            print(f"Sau khi hoàn tất đăng nhập, nhấn ENTER tại đây để lưu Session.")
            print(f"=======================================================\n")
            input("Nhấn ENTER khi bạn đã đăng nhập xong...")
            context.close()
            logger.info(f"Đã lưu thành công phiên đăng nhập {self.platform_name}!")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        raise NotImplementedError("Subclasses must implement post_video")
