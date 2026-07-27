import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright
from config.settings import FACEBOOK_SESSION_DIR
from publishers.base_publisher import BasePublisher

logger = logging.getLogger(__name__)

class FacebookPublisher(BasePublisher):
    """Facebook Reels Auto Publisher using Browser Session"""

    def __init__(self):
        super().__init__("Facebook", FACEBOOK_SESSION_DIR)

    def login_manual(self):
        self.interactive_login("https://www.facebook.com/")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        if not video_path.exists():
            logger.error(f"File video không tồn tại: {video_path}")
            return False

        full_caption = caption
        if tags:
            full_caption += "\n\n" + " ".join(tags)

        logger.info(f"Đang tự động đăng video lên Facebook Reels: {video_path.name}")

        try:
            with sync_playwright() as p:
                context = self.get_browser_context(p, headless=True)
                page = context.new_page()

                # Go to Facebook Reels creation page
                page.goto("https://www.facebook.com/reels/create", wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # Check if logged in
                if "login" in page.url:
                    logger.error("Chưa đăng nhập Facebook! Vui lòng chạy lệnh login Facebook trước.")
                    context.close()
                    return False

                # Upload video file via input element
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0:
                    file_input.first.set_input_files(str(video_path))
                    time.sleep(5)
                else:
                    logger.error("Không tìm thấy ô chọn file video trên Facebook Reels")
                    context.close()
                    return False

                # Next step / Add description
                next_btn = page.locator("div[role='button']:has-text('Tiếp'), div[role='button']:has-text('Next')")
                if next_btn.count() > 0:
                    next_btn.first.click()
                    time.sleep(3)

                # Caption input area
                caption_area = page.locator("div[role='textbox'], textarea")
                if caption_area.count() > 0:
                    caption_area.first.fill(full_caption)
                    time.sleep(2)

                # Post button
                post_btn = page.locator("div[role='button']:has-text('Đăng'), div[role='button']:has-text('Publish'), div[role='button']:has-text('Post')")
                if post_btn.count() > 0:
                    post_btn.first.click()
                    logger.info("Đã nhấn nút Đăng Reels trên Facebook. Đang chờ tải lên...")
                    time.sleep(10) # Wait for post submission
                    context.close()
                    return True
                else:
                    logger.error("Không thấy nút Đăng trên Facebook Reels")
                    context.close()
                    return False

        except Exception as e:
            logger.exception(f"Lỗi đăng Facebook Reels: {e}")
            return False
