import os
import time
import logging
import requests
from pathlib import Path
from config.settings import LABS_GOOGLE_SESSION_DIR, GENERATED_DIR, BASE_DIR
from publishers.base_publisher import BasePublisher

logger = logging.getLogger(__name__)

LABS_GOOGLE_URL = "https://labs.google/fx/tools/video-fx"

class LabsGoogleGenerator(BasePublisher):
    """Google Labs (labs.google) VideoFX / Veo Browser Automation Generator.

    Uses Playwright browser automation with persistent session context to:
    1. Navigate to labs.google
    2. Input prompt
    3. Click generate
    4. Wait for video render completion
    5. Download completed mp4 video to output directory
    """

    def __init__(self):
        super().__init__("LabsGoogle", LABS_GOOGLE_SESSION_DIR)

    def login_manual(self):
        """Open interactive browser window for manual Google account login to labs.google"""
        self.interactive_login(LABS_GOOGLE_URL)

    def is_logged_in(self) -> bool:
        """Check if user session cookies/data exist in LABS_GOOGLE_SESSION_DIR"""
        cookies_file = self.session_dir / "Default" / "Cookies"
        if cookies_file.exists() and cookies_file.stat().st_size > 2000:
            return True
        return super().is_logged_in()

    def generate_video(self, prompt: str, out_path: Path, timeout_sec: int = 600) -> bool:
        """Automate labs.google to paste prompt, generate video, and download .mp4 output file.

        Args:
            prompt: Text description of video to render
            out_path: Path where output mp4 video should be saved
            timeout_sec: Maximum time to wait for rendering in seconds

        Returns:
            bool: True if video rendered and downloaded successfully
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright chưa được cài đặt. Vui lòng chạy: pip install playwright")
            return False

        logger.info(f"[LabsGoogle] Bắt đầu tự động tạo video từ prompt trên labs.google: '{prompt[:60]}...'")

        try:
            with sync_playwright() as p:
                # hidden=False: Hiển thị màn hình trình duyệt trực quan cho người dùng thấy
                context = self.get_browser_context(p, headless=False, hidden=False)
                page = context.new_page()
                page.set_default_timeout(60000)

                # Step 1: Navigate to Labs Google VideoFX
                logger.info(f"[LabsGoogle] Điều hướng tới {LABS_GOOGLE_URL}...")
                page.goto(LABS_GOOGLE_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)

                # Check if redirected to login page
                if "accounts.google.com" in page.url.lower() or "signin" in page.url.lower():
                    logger.error("[LabsGoogle] Chưa đăng nhập tài khoản Google! Vui lòng thực hiện Đăng Nhập Labs Google trước.")
                    self._screenshot(page, "labs_google_login_required")
                    context.close()
                    return False

                self._screenshot(page, "labs_01_landed")

                # Step 1.5: If landing page has a 'Create with Google Flow' / 'Get Started' button, click it to enter tool workspace
                launch_selectors = [
                    "button:has-text('Create with Google Flow')",
                    "a:has-text('Create with Google Flow')",
                    "button:has-text('Create')",
                    "button:has-text('Get Started')",
                    "button:has-text('Try VideoFX')",
                    "button:has-text('Launch')",
                    "a:has-text('Try')"
                ]
                for l_sel in launch_selectors:
                    try:
                        btn = page.locator(l_sel).first
                        if btn.is_visible(timeout=3000):
                            logger.info(f"[LabsGoogle] Bấm nút vào công cụ: {l_sel}")
                            btn.click()
                            time.sleep(4)
                            self._screenshot(page, "labs_01b_workspace_opened")

                            if "accounts.google.com" in page.url.lower() or "signin" in page.url.lower():
                                logger.error("[LabsGoogle] Yêu cầu đăng nhập tài khoản Google để tiếp tục! Vui lòng mở tab Google Labs Session trong ứng dụng để đăng nhập 1 lần.")
                                self._screenshot(page, "labs_google_login_required")
                                context.close()
                                return False
                            break
                    except Exception:
                        pass

                # Step 2: Locate prompt input area
                prompt_input = None
                input_selectors = [
                    "textarea[placeholder*='prompt' i]",
                    "textarea[placeholder*='mô tả' i]",
                    "textarea[placeholder*='Create' i]",
                    "textarea[placeholder*='Describe' i]",
                    "textarea:visible:not([name*='recaptcha'])",
                    "div[contenteditable='true']:visible",
                    "input[type='text']:visible",
                    "[aria-label*='prompt' i]",
                    "[placeholder*='Create' i]",
                    "[placeholder*='Describe' i]"
                ]

                for sel in input_selectors:
                    try:
                        locator = page.locator(sel)
                        for idx in range(locator.count()):
                            candidate = locator.nth(idx)
                            name_attr = candidate.get_attribute("name") or ""
                            if "recaptcha" in name_attr.lower():
                                continue
                            if candidate.is_visible(timeout=2000):
                                prompt_input = candidate
                                logger.info(f"[LabsGoogle] Đã tìm thấy ô nhập prompt ({sel} #{idx})")
                                break
                        if prompt_input:
                            break
                    except Exception:
                        pass

                if not prompt_input:
                    logger.error("[LabsGoogle] Không tìm thấy ô nhập prompt trên trang labs.google")
                    self._screenshot(page, "labs_error_no_prompt_input")
                    context.close()
                    return False

                # Step 3: Enter prompt
                prompt_input.click()
                time.sleep(1)
                prompt_input.fill(prompt)
                time.sleep(2)
                logger.info(f"[LabsGoogle] Đã nhập prompt thành công: '{prompt[:50]}...'")
                self._screenshot(page, "labs_02_prompt_entered")

                # Step 4: Click Generate button
                gen_button = None
                btn_selectors = [
                    "button:has-text('Generate')",
                    "button:has-text('Tạo')",
                    "button:has-text('Create')",
                    "button:has-text('Submit')",
                    "button[type='submit']",
                    "[aria-label*='Generate' i]",
                    "[aria-label*='Tạo' i]"
                ]

                for sel in btn_selectors:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=3000):
                            gen_button = btn
                            logger.info(f"[LabsGoogle] Đã tìm thấy nút Generate: {sel}")
                            break
                    except Exception:
                        pass

                if not gen_button:
                    # Press Enter as fallback
                    logger.info("[LabsGoogle] Thử nhấn Enter để submit prompt...")
                    prompt_input.press("Enter")
                else:
                    gen_button.click()

                logger.info("[LabsGoogle] Đã gửi yêu cầu sinh video. Đang chờ render hoàn tất...")
                self._screenshot(page, "labs_03_generating")

                # Step 5: Wait for generated video / download link
                start_time = time.time()
                video_downloaded = False

                # Listen for download event or video element / link
                download_info = []

                def handle_download(download):
                    try:
                        dl_path = out_path
                        download.save_as(str(dl_path))
                        download_info.append(dl_path)
                        logger.info(f"[LabsGoogle] ✅ Đã tải video qua sự kiện browser download: {dl_path.name}")
                    except Exception as ex:
                        logger.warning(f"[LabsGoogle] Lỗi lưu browser download: {ex}")

                page.on("download", handle_download)

                while time.time() - start_time < timeout_sec:
                    # Check if browser download event fired
                    if download_info and out_path.exists() and out_path.stat().st_size > 100000:
                        video_downloaded = True
                        break

                    # Check for video element with src blob/http
                    try:
                        video_elems = page.locator("video")
                        count = video_elems.count()
                        for i in range(count):
                            v_src = video_elems.nth(i).get_attribute("src") or ""
                            if v_src and ("http" in v_src or "blob" in v_src):
                                # Look for download button nearby or click download menu
                                dl_btns = page.locator("button:has-text('Download'), a[download], [aria-label*='Download' i], [title*='Download' i]")
                                if dl_btns.count() > 0:
                                    for d_idx in range(dl_btns.count()):
                                        try:
                                            b = dl_btns.nth(d_idx)
                                            if b.is_visible(timeout=1000):
                                                with page.expect_download(timeout=10000) as download_info_ctx:
                                                    b.click()
                                                dl = download_info_ctx.value
                                                dl.save_as(str(out_path))
                                                logger.info(f"[LabsGoogle] ✅ Đã tải video thành công qua nút Download!")
                                                video_downloaded = True
                                                break
                                        except Exception:
                                            pass
                                if video_downloaded:
                                    break
                    except Exception:
                        pass

                    if video_downloaded:
                        break

                    time.sleep(5)

                if not video_downloaded:
                    # Check if any video element is present on page and fetch via HTTP if direct src exists
                    try:
                        video_elems = page.locator("video")
                        if video_elems.count() > 0:
                            v_src = video_elems.first.get_attribute("src")
                            if v_src and v_src.startswith("http"):
                                r = requests.get(v_src, timeout=60)
                                if r.status_code == 200 and len(r.content) > 100000:
                                    with open(out_path, "wb") as f:
                                        f.write(r.content)
                                    logger.info(f"[LabsGoogle] ✅ Đã tải trực tiếp mp4 từ video src HTTP!")
                                    video_downloaded = True
                    except Exception as ex:
                        logger.warning(f"[LabsGoogle] Lỗi fetch video src: {ex}")

                self._screenshot(page, "labs_04_finish")
                context.close()

                if video_downloaded and out_path.exists():
                    logger.info(f"[LabsGoogle] ✅ Hoàn thành tạo video từ prompt trên labs.google: {out_path.name}")
                    return True
                else:
                    logger.error("[LabsGoogle] Không tải được file video hoàn chỉnh sau khi render.")
                    return False

        except Exception as e:
            logger.exception(f"[LabsGoogle] Lỗi tự động hóa labs.google: {e}")
            return False

    def _screenshot(self, page, name: str):
        try:
            log_dir = BASE_DIR / "storage" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{name}.png"
            page.screenshot(path=str(path))
            logger.info(f"[LabsGoogle] Screenshot saved: {path}")
        except Exception as ex:
            logger.warning(f"[LabsGoogle] Không lưu được screenshot: {ex}")
