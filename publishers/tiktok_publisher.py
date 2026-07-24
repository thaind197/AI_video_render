import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright
from config.settings import TIKTOK_SESSION_DIR
from publishers.base_publisher import BasePublisher

logger = logging.getLogger(__name__)

class TikTokPublisher(BasePublisher):
    """TikTok Creator Studio Auto Publisher using Browser Session"""

    def __init__(self):
        super().__init__("TikTok", TIKTOK_SESSION_DIR)

    def login_manual(self):
        self.interactive_login("https://www.tiktok.com/login")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        if not video_path.exists():
            logger.error(f"File video không tồn tại: {video_path}")
            return False

        full_caption = caption
        if tags:
            full_caption += " " + " ".join(tags)

        logger.info(f"Đang tự động đăng video lên TikTok: {video_path.name}")

        try:
            with sync_playwright() as p:
                context = self.get_browser_context(p, headless=True)
                page = context.new_page()

                # TikTok upload URL
                page.goto("https://www.tiktok.com/creator-center/upload?from=upload", wait_until="networkidle", timeout=60000)
                time.sleep(5)

                if "login" in page.url:
                    logger.error("Chưa đăng nhập TikTok! Vui lòng chạy lệnh login TikTok trước.")
                    context.close()
                    return False

                # Handle iframe if TikTok upload form is inside iframe
                upload_frame = page
                for frame in page.frames:
                    if "upload" in frame.url or frame.locator("input[type='file']").count() > 0:
                        upload_frame = frame
                        break

                file_input = upload_frame.locator("input[type='file']")
                if file_input.count() > 0:
                    file_input.first.set_input_files(str(video_path))
                    time.sleep(10) # TikTok video processing delay
                else:
                    logger.error("Không tìm thấy ô chọn file upload trên TikTok")
                    context.close()
                    return False

                # Caption input area
                caption_elem = upload_frame.locator("div[contenteditable='true'], textarea")
                if caption_elem.count() > 0:
                    caption_elem.first.fill(full_caption)
                    time.sleep(2)

                # Post button
                post_btn = upload_frame.locator("button:has-text('Đăng'), button:has-text('Post')")
                if post_btn.count() > 0:
                    post_btn.first.click()
                    logger.info("Đã nhấn nút Đăng trên TikTok. Đang chờ hoàn tất...")
                    time.sleep(10)
                    context.close()
                    return True
                else:
                    logger.error("Không tìm thấy nút Đăng trên TikTok")
                    context.close()
                    return False

        except Exception as e:
            logger.exception(f"Lỗi đăng TikTok: {e}")
            return False
