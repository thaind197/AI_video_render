import time
import logging
from pathlib import Path
from config.settings import TIKTOK_SESSION_DIR
from publishers.base_publisher import BasePublisher

logger = logging.getLogger(__name__)


class TikTokPublisher(BasePublisher):
    """TikTok Creator Studio Auto Publisher using Browser Session.
    Supports multi-account: pass profile_id to use a specific TikTok profile session.
    """

    def __init__(self, profile_id: str = None):
        if profile_id:
            from publishers.tiktok_profile_manager import TikTokProfileManager
            mgr = TikTokProfileManager()
            session_dir = mgr.get_session_dir(profile_id)
            profile = mgr.get_profile(profile_id)
            name = profile["name"] if profile else profile_id
            super().__init__(f"TikTok [{name}]", session_dir)
            self._profile_id = profile_id
        else:
            super().__init__("TikTok", TIKTOK_SESSION_DIR)
            self._profile_id = "default"

    def login_manual(self):
        self.interactive_login("https://www.tiktok.com/upload")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        if not video_path.exists():
            logger.error(f"File video không tồn tại: {video_path}")
            return False

        full_caption = caption
        if tags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags[:20])
            full_caption += f"\n\n{tag_str}"

        logger.info(f"[{self.platform_name}] Đang tự động đăng video lên TikTok (hidden mode): {video_path.name}")

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                context = self.get_browser_context(p, headless=False, hidden=True)
                page = context.new_page()

                # TikTok upload URL
                page.goto("https://www.tiktok.com/creator-center/upload?from=upload", wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)

                if "login" in page.url.lower():
                    logger.error(f"[{self.platform_name}] Chưa đăng nhập TikTok! Vui lòng chạy đăng nhập profile trước.")
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
                    logger.info(f"[{self.platform_name}] Set file upload thành công. Đang chờ TikTok xử lý...")
                    time.sleep(10)
                else:
                    logger.error(f"[{self.platform_name}] Không tìm thấy ô chọn file upload trên TikTok")
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
                    logger.info(f"[{self.platform_name}] ✅ Đã nhấn nút Đăng trên TikTok.")
                    time.sleep(10)
                    context.close()
                    return True
                else:
                    logger.error(f"[{self.platform_name}] Không tìm thấy nút Đăng trên TikTok")
                    context.close()
                    return False

        except Exception as e:
            logger.exception(f"[{self.platform_name}] Lỗi đăng TikTok: {e}")
            return False
