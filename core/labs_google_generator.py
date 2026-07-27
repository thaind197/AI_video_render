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

    def generate_video(self, prompt: str, out_path: Path, quality: str = "1080p", timeout_sec: int = 600) -> bool:
        """Automate labs.google to paste prompt, generate video, and download .mp4 output file.

        Args:
            prompt: Text description of video to render
            out_path: Path where output mp4 video should be saved
            quality: Video quality option ('1080p', '720p', '4K', '270p')
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
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                page = context.new_page()
                page.set_default_timeout(60000)
                time.sleep(3.0)  # Đợi 3s ngay khi mở trình duyệt theo yêu cầu

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

                # Step 1.5: If page requires clicking 'Dự án mới' / 'New project' / 'Create', click to open project workspace
                launch_selectors = [
                    "button:has-text('Dự án mới')",
                    "button:has-text('New project')",
                    "button:has-text('New Project')",
                    "button:has-text('Create project')",
                    "button:has-text('Create Project')",
                    "button:has-text('Tạo dự án')",
                    "button:has-text('New flow')",
                    "button:has-text('Tạo mới')",
                    "button:has-text('New')",
                    "button:has-text('Create with Google Flow')",
                    "a:has-text('Dự án mới')",
                    "a:has-text('New project')",
                    "a:has-text('Create with Google Flow')",
                    "a:has-text('Create')",
                    "[aria-label*='Dự án mới' i]",
                    "[aria-label*='New project' i]",
                    "[aria-label*='Create' i]",
                    "[aria-label*='Tạo' i]",
                    "button:has-text('Get Started')",
                    "button:has-text('Try VideoFX')",
                    "button:has-text('Launch')",
                    "a:has-text('Try')"
                ]
                for l_sel in launch_selectors:
                    try:
                        btn = page.locator(l_sel).first
                        if btn.is_visible(timeout=2500):
                            logger.info(f"[LabsGoogle] Bấm nút vào Dự Án Mới / Công Cụ: {l_sel}")
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
                    "textarea[placeholder*='Flow' i]",
                    "textarea[placeholder*='video' i]",
                    "textarea:visible:not([name*='recaptcha'])",
                    "[contenteditable='true']",
                    "[contenteditable]",
                    "div[role='textbox']",
                    "span[role='textbox']",
                    "[aria-label*='prompt' i]",
                    "[aria-label*='Describe' i]",
                    "[aria-label*='Create' i]",
                    "[aria-label*='mô tả' i]",
                    "[placeholder*='prompt' i]",
                    "[placeholder*='Create' i]",
                    "[placeholder*='Describe' i]",
                    "[placeholder*='video' i]",
                    "[data-placeholder]",
                    ".ProseMirror",
                    "input[type='text']:visible"
                ]

                for sel in input_selectors:
                    try:
                        locator = page.locator(sel)
                        count = locator.count()
                        for idx in range(count):
                            candidate = locator.nth(idx)
                            name_attr = candidate.get_attribute("name") or ""
                            if "recaptcha" in name_attr.lower():
                                continue
                            if candidate.is_visible(timeout=1500):
                                prompt_input = candidate
                                logger.info(f"[LabsGoogle] Đã tìm thấy ô nhập prompt ({sel} #{idx})")
                                break
                        if prompt_input:
                            break
                    except Exception:
                        pass

                # Fallback: Thử tìm trong main container
                if not prompt_input:
                    try:
                        body_inputs = page.locator("main textarea, main [contenteditable='true'], main div[role='textbox']")
                        if body_inputs.count() > 0:
                            prompt_input = body_inputs.first
                            logger.info("[LabsGoogle] Đã tìm thấy ô nhập prompt qua fallback main container")
                    except Exception:
                        pass

                if not prompt_input:
                    logger.error("[LabsGoogle] Không tìm thấy ô nhập prompt trên trang labs.google")
                    self._screenshot(page, "labs_error_no_prompt_input")
                    context.close()
                    return False

                # Step 3: Enter prompt
                try:
                    prompt_input.click()
                except Exception:
                    pass
                time.sleep(0.5)

                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                time.sleep(0.5)

                try:
                    prompt_input.fill(prompt)
                except Exception:
                    page.keyboard.insert_text(prompt)

                time.sleep(1.5)
                logger.info(f"[LabsGoogle] Đã nhập prompt thành công: '{prompt[:50]}...'")
                self._screenshot(page, "labs_02_prompt_entered")

                # Step 4: Submit prompt by pressing Enter
                logger.info("[LabsGoogle] Nhấn phím Enter để gửi prompt...")
                page.keyboard.press("Enter")
                time.sleep(1.0)
                page.keyboard.press("Enter")

                logger.info("[LabsGoogle] Đã gửi yêu cầu sinh video. Đang chờ 50 giây cho Google Labs render hoàn tất...")
                self._screenshot(page, "labs_03_generating")
                time.sleep(50)

                # Step 5: Wait for generated video & download via 3-dots menu -> Tải xuống -> 1080p
                start_time = time.time()
                video_downloaded = False

                download_info = []

                def handle_download(download):
                    try:
                        download.save_as(str(out_path))
                        download_info.append(out_path)
                        logger.info(f"[LabsGoogle] ✅ Đã lưu video tải về: {out_path.name}")
                    except Exception as ex:
                        logger.warning(f"[LabsGoogle] Lỗi lưu browser download: {ex}")

                page.on("download", handle_download)

                while time.time() - start_time < timeout_sec:
                    # 1. Kiểm tra sự kiện download tự động đã bắn ra hay chưa
                    if download_info and out_path.exists() and out_path.stat().st_size > 100000:
                        video_downloaded = True
                        break

                    try:
                        # 1. Tìm khung chứa video card mới nhất trên màn hình
                        video_cards = page.locator("div:has(video)")
                        if video_cards.count() == 0:
                            video_cards = page.locator("video")

                        if video_cards.count() > 0:
                            # Lấy video card mới nhất (hoặc đầu tiên)
                            card = video_cards.last
                            try:
                                card.scroll_into_view_if_needed()
                                card.hover()
                                time.sleep(1.0)
                                logger.info("[LabsGoogle] Đã rê chuột vào khung video card vừa tạo")
                            except Exception:
                                pass

                            # 2. Tìm nút 3 chấm [⋮] NẰM TRONG KHUNG VIDEO CARD này
                            three_dots_btn = None
                            cand_btns = card.locator("button")
                            count_b = cand_btns.count()

                            for b_idx in range(count_b):
                                b_elem = cand_btns.nth(b_idx)
                                b_aria = (b_elem.get_attribute("aria-label") or "").lower()
                                b_text = (b_elem.text_content() or "").lower()
                                if "khác" in b_aria or "more" in b_aria or "more_vert" in b_text or "..." in b_text or "⋮" in b_text:
                                    three_dots_btn = b_elem
                                    logger.info(f"[LabsGoogle] Đã tìm thấy nút 3 chấm qua text/aria: {b_aria or b_text}")
                                    break

                            # Nếu không tìm được theo text, lấy nút thứ 3 trong thanh điều khiển góc trên video card
                            if not three_dots_btn and count_b >= 3:
                                three_dots_btn = cand_btns.nth(2)
                                logger.info("[LabsGoogle] Chọn nút thứ 3 trong thanh điều khiển video làm nút 3 chấm [⋮]")
                            elif not three_dots_btn and count_b > 0:
                                three_dots_btn = cand_btns.last

                            if three_dots_btn:
                                logger.info("[LabsGoogle] Click nút 3 chấm [⋮] trên video card...")
                                try:
                                    three_dots_btn.hover()
                                    time.sleep(0.5)
                                    three_dots_btn.click(force=True)
                                    time.sleep(1.5)
                                    self._screenshot(page, "labs_03b_3dots_menu_opened")
                                except Exception as ex_c:
                                    logger.warning(f"[LabsGoogle] Lỗi click nút 3 chấm: {ex_c}")

                                # 3. Tìm DOM element 'Tải xuống' bằng get_by_text, get_by_role & role=menuitem
                                dl_menu_item = None
                                try:
                                    cand1 = page.get_by_text("Tải xuống", exact=False)
                                    if cand1.count() > 0 and cand1.first.is_visible(timeout=1500):
                                        dl_menu_item = cand1.first
                                    else:
                                        cand2 = page.get_by_role("menuitem").filter(has_text="Tải xuống")
                                        if cand2.count() > 0 and cand2.first.is_visible(timeout=1500):
                                            dl_menu_item = cand2.first
                                        else:
                                            cand3 = page.locator("[role='menuitem']:has-text('Tải xuống'), li:has-text('Tải xuống'), div:has-text('Tải xuống'), span:has-text('Tải xuống')")
                                            if cand3.count() > 0 and cand3.first.is_visible(timeout=1500):
                                                dl_menu_item = cand3.first
                                except Exception as ex_dl_find:
                                    logger.warning(f"[LabsGoogle] Lỗi tìm DOM element Tải xuống: {ex_dl_find}")

                                if dl_menu_item:
                                    logger.info("[LabsGoogle] Đã tìm thấy DOM element 'Tải xuống', rê chuột & click mở sub-menu...")
                                    try:
                                        dl_menu_item.scroll_into_view_if_needed()
                                        dl_menu_item.hover()
                                        time.sleep(0.8)
                                        dl_menu_item.click(force=True)
                                        time.sleep(1.2)
                                        self._screenshot(page, "labs_03c_download_sub_menu")
                                    except Exception as ex_h:
                                        logger.warning(f"[LabsGoogle] Lỗi hover/click Tải xuống: {ex_h}")

                                    # 4. Tìm DOM element chất lượng video mong muốn trong sub-menu vừa mở
                                    target_q = (quality or "1080p").strip()
                                    opt_quality = None
                                    try:
                                        cand_q1 = page.get_by_text(target_q, exact=False)
                                        if cand_q1.count() > 0 and cand_q1.first.is_visible(timeout=1500):
                                            opt_quality = cand_q1.first
                                        else:
                                            cand_q2 = page.get_by_role("menuitem").filter(has_text=target_q)
                                            if cand_q2.count() > 0 and cand_q2.first.is_visible(timeout=1500):
                                                opt_quality = cand_q2.first
                                            else:
                                                cand_q3 = page.locator(f"[role='menuitem']:has-text('{target_q}'), li:has-text('{target_q}'), div:has-text('{target_q}'), span:has-text('{target_q}')")
                                                if cand_q3.count() > 0 and cand_q3.first.is_visible(timeout=1500):
                                                    opt_quality = cand_q3.first
                                    except Exception:
                                        pass

                                    if opt_quality:
                                        logger.info(f"[LabsGoogle] Đã tìm thấy tùy chọn chất lượng '{target_q}', click để tải video...")
                                        try:
                                            with page.expect_download(timeout=25000) as download_info_ctx:
                                                opt_quality.click(force=True)
                                            dl = download_info_ctx.value
                                            dl.save_as(str(out_path))
                                            logger.info(f"[LabsGoogle] ✅ Tải video chất lượng {target_q} thành công về: {out_path.name}")
                                            video_downloaded = True
                                            break
                                        except Exception as ex_dl_q:
                                            logger.warning(f"[LabsGoogle] Lỗi chờ file download {target_q}: {ex_dl_q}")
                                    else:
                                        # Fallback chọn 1080p -> 720p nếu chất lượng mong muốn không thấy
                                        logger.warning(f"[LabsGoogle] Không thấy tùy chọn {target_q}, thử chọn fallback 1080p / 720p...")
                                        try:
                                            opt_fb = page.get_by_text("1080p", exact=False).first
                                            if not opt_fb.is_visible(timeout=1000):
                                                opt_fb = page.get_by_text("720p", exact=False).first
                                            if opt_fb.is_visible(timeout=1000):
                                                with page.expect_download(timeout=20000) as download_info_ctx:
                                                    opt_fb.click(force=True)
                                                dl = download_info_ctx.value
                                                dl.save_as(str(out_path))
                                                logger.info(f"[LabsGoogle] ✅ Tải video fallback thành công!")
                                                video_downloaded = True
                                                break
                                        except Exception:
                                            pass
                    except Exception as ex_loop:
                        pass

                    if video_downloaded:
                        break

                    time.sleep(5)

                if not video_downloaded:
                    # Fallback cuối cùng: Tải trực tiếp qua URL HTTP của thẻ video nếu có
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
