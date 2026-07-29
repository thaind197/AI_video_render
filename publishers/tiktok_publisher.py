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
        self.interactive_login("https://www.tiktok.com/login?lang=vi-VN")

    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        if not video_path.exists():
            logger.error(f"File video không tồn tại: {video_path}")
            return False

        full_caption = caption.strip() if caption else ""
        if tags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags[:20])
            full_caption += f"\n\n{tag_str}"

        logger.info(f"[{self.platform_name}] Bắt đầu đăng video lên TikTok (mở trình duyệt): {video_path.name}")

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                # hidden=False: mở trình duyệt trực tiếp trên màn hình để quan sát
                context = self.get_browser_context(p, headless=False, hidden=False)
                page = context.new_page()
                page.set_default_timeout(60000)

                # ── Step 1: Navigate to TikTok Upload / Studio ──
                target_urls = [
                    "https://www.tiktok.com/tiktokstudio/upload",
                    "https://www.tiktok.com/creator-center/upload?from=upload",
                    "https://www.tiktok.com/upload"
                ]
                
                navigated = False
                for u in target_urls:
                    try:
                        logger.info(f"[{self.platform_name}] Điều hướng tới: {u}")
                        page.goto(u, wait_until="domcontentloaded", timeout=45000)
                        time.sleep(5)
                        if "login" not in page.url.lower():
                            navigated = True
                            break
                    except Exception as ex:
                        logger.warning(f"[{self.platform_name}] Không mở được {u}: {ex}")

                if "login" in page.url.lower():
                    logger.error(f"[{self.platform_name}] Chưa đăng nhập TikTok! Vui lòng đăng nhập profile trước.")
                    self._screenshot(page, "tiktok_login_expired")
                    context.close()
                    return False

                self._screenshot(page, "tiktok_01_landed")

                # ── Step 2: Auto-close common popups/modals ──
                self._close_popups(page)

                # ── Step 3: Find upload frame / file input ──
                upload_frame = page
                for frame in page.frames:
                    try:
                        if "upload" in frame.url or frame.locator("input[type='file']").count() > 0:
                            upload_frame = frame
                            break
                    except Exception:
                        pass

                file_input = upload_frame.locator("input[type='file']")
                if file_input.count() == 0:
                    # Retry in main page
                    file_input = page.locator("input[type='file']")

                if file_input.count() > 0:
                    file_input.first.set_input_files(str(video_path))
                    logger.info(f"[{self.platform_name}] ✅ Đã chọn file video: {video_path.name}. Chờ TikTok tải lên...")
                    time.sleep(8)
                else:
                    logger.error(f"[{self.platform_name}] Không tìm thấy ô chọn file upload (input[type='file']) trên TikTok")
                    self._screenshot(page, "tiktok_no_file_input")
                    context.close()
                    return False

                self._close_popups(page)

                # ── Step 4: Poll upload & processing ──
                logger.info(f"[{self.platform_name}] Chờ video xử lý hoàn tất...")
                time.sleep(6)

                # ── Step 5: Caption input area ──
                caption_filled = False
                caption_selectors = [
                    "div[contenteditable='true']",
                    "div.notranslate[contenteditable='true']",
                    "div[role='combobox']",
                    "div[role='textbox']",
                    "textarea",
                    "[placeholder*='mô tả']",
                    "[placeholder*='caption']",
                    "[placeholder*='Describe']"
                ]

                for sel in caption_selectors:
                    try:
                        elem = upload_frame.locator(sel).first
                        if not elem.is_visible(timeout=2000):
                            elem = page.locator(sel).first
                        if elem.is_visible(timeout=2000):
                            elem.click()
                            time.sleep(1)
                            # Control+A & Fill
                            page.keyboard.press("Control+A")
                            page.keyboard.press("Backspace")
                            time.sleep(0.5)
                            elem.fill(full_caption)
                            time.sleep(1.5)
                            caption_filled = True
                            logger.info(f"[{self.platform_name}] ✅ Đã nhập caption: {len(full_caption)} ký tự")
                            break
                    except Exception:
                        pass

                if not caption_filled:
                    logger.warning(f"[{self.platform_name}] Không tìm thấy ô caption, đăng mặc định...")

                self._screenshot(page, "tiktok_02_caption_filled")

                # ── Step 6: Click Post button ──
                posted = False
                post_button_selectors = [
                    "button[data-e2e='post_video_button']",
                    "button:has-text('Đăng')",
                    "button:has-text('Post')",
                    "div[role='button']:has-text('Đăng')",
                    "div[role='button']:has-text('Post')",
                    "button:has-text('Chia sẻ')"
                ]

                # Wait for post button to be enabled (upload complete)
                for attempt in range(30):  # Wait up to 60s for post button
                    for sel in post_button_selectors:
                        try:
                            btn = upload_frame.locator(sel).first
                            if not btn.is_visible(timeout=1000):
                                btn = page.locator(sel).first
                            if btn.is_visible(timeout=1000) and btn.is_enabled():
                                btn.click()
                                logger.info(f"[{self.platform_name}] ✅ Đã nhấn nút Đăng trên TikTok! ({sel})")
                                time.sleep(12)  # Wait for submission
                                self._screenshot(page, f"tiktok_03_posted_{video_path.stem}")
                                posted = True
                                break
                        except Exception:
                            pass
                    if posted:
                        break
                    time.sleep(2)

                if not posted:
                    logger.error(f"[{self.platform_name}] Không thể nhấn nút Đăng trên TikTok")
                    self._screenshot(page, "tiktok_post_btn_failed")

                context.close()
                return posted

        except Exception as e:
            logger.exception(f"[{self.platform_name}] Lỗi đăng TikTok: {e}")
            return False

    def _close_popups(self, page):
        """Đóng các popup / modal hội thoại chặn tương tác trên TikTok"""
        for sel in [
            "button:has-text('Đã hiểu')", "button:has-text('Got it')",
            "button:has-text('Cho phép')", "button:has-text('Allow')",
            "button:has-text('Bỏ qua')", "button:has-text('Skip')",
            "button:has-text('Chấp nhận')", "button:has-text('Accept')",
            ".tiktok-modal__close", "[aria-label='Close']"
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    time.sleep(1)
            except Exception:
                pass

    def _screenshot(self, page, name: str):
        try:
            from config.settings import BASE_DIR
            log_dir = BASE_DIR / "storage" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{name}.png"
            page.screenshot(path=str(path))
            logger.info(f"[TikTok] Screenshot: {path}")
        except Exception as ex:
            logger.warning(f"[TikTok] Không lưu được screenshot: {ex}")
