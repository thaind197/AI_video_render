import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright
from config.settings import X_SESSION_DIR
from publishers.base_publisher import BasePublisher

logger = logging.getLogger(__name__)

class XPublisher(BasePublisher):
    """X / Twitter Auto Publisher using Browser Session"""

    def __init__(self):
        super().__init__("X (Twitter)", X_SESSION_DIR)

    def login_manual(self):
        self.interactive_login("https://x.com/i/flow/login")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        if not video_path.exists():
            logger.error(f"File video không tồn tại: {video_path}")
            return False

        full_caption = caption
        if tags:
            full_caption += "\n" + " ".join(tags)

        logger.info(f"Đang tự động đăng video lên X (Twitter): {video_path.name}")

        try:
            with sync_playwright() as p:
                context = self.get_browser_context(p, headless=True)
                page = context.new_page()

                page.goto("https://x.com/compose/post", wait_until="networkidle", timeout=60000)
                time.sleep(3)

                if "login" in page.url:
                    logger.error("Chưa đăng nhập X (Twitter)! Vui lòng chạy lệnh login X trước.")
                    context.close()
                    return False

                # Attach video file
                file_input = page.locator("input[type='file'][data-testid='fileInput']")
                if file_input.count() > 0:
                    file_input.first.set_input_files(str(video_path))
                    time.sleep(5)
                else:
                    logger.error("Không tìm thấy ô chọn media trên X")
                    context.close()
                    return False

                # Text area input
                text_area = page.locator("div[data-testid='tweetTextarea_0']")
                if text_area.count() > 0:
                    text_area.first.fill(full_caption)
                    time.sleep(2)

                # Post button
                post_btn = page.locator("button[data-testid='tweetButton']")
                if post_btn.count() > 0:
                    post_btn.first.click()
                    logger.info("Đã nhấn nút Post trên X. Đang hoàn tất...")
                    time.sleep(8)
                    context.close()
                    return True
                else:
                    logger.error("Không tìm thấy nút Post trên X")
                    context.close()
                    return False

        except Exception as e:
            logger.exception(f"Lỗi đăng bài lên X (Twitter): {e}")
            return False
