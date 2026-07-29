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

    def _configure_labs_settings(self, page, aspect_ratio: str, duration: int, variants: int, model: str):
        """Automate clicking settings popover on Google Labs UI matching tool configuration."""
        try:
            logger.info(f"[LabsGoogle] Cấu hình tùy chọn Google Labs UI: aspect_ratio={aspect_ratio}, duration={duration}s, variants={variants}x, model={model}")

            # 1. Tìm và click nút mở Bảng Cài Đặt (Settings Popover/Modal)
            settings_selectors = [
                "button:has-text('Video')",
                "button:has-text('Khung hình')",
                "button:has-text('Thành phần')",
                "button:has-text('8s')",
                "button:has-text('6s')",
                "button:has-text('4s')",
                "button:has-text('1x')",
                "button:has-text('x2')",
                "button:has-text('x3')",
                "button:has-text('x4')",
                "[aria-label*='Cài đặt' i]",
                "[aria-label*='Settings' i]"
            ]

            popover_opened = False
            for sel in settings_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        time.sleep(1.0)
                        popover_opened = True
                        logger.info(f"[LabsGoogle] Đã click mở Popover Cài Đặt via '{sel}'")
                        break
                except Exception:
                    pass

            # 2. Đảm bảo chọn tab Video (nếu có lựa chọn Hình ảnh / Video)
            try:
                vid_tab = page.locator("button:has-text('Video'), div[role='tab']:has-text('Video')").first
                if vid_tab.is_visible(timeout=1000):
                    vid_tab.click()
                    time.sleep(0.5)
            except Exception:
                pass

            # 3. Chọn Tỷ lệ Khung hình (Aspect Ratio: 9:16 vs 16:9)
            if aspect_ratio:
                target_ar = aspect_ratio.strip()  # "9:16" or "16:9"
                ar_selectors = [
                    f"button:has-text('{target_ar}')",
                    f"div:has-text('{target_ar}'):not(:has(*))",
                    f"[aria-label*='{target_ar}']"
                ]
                for ar_sel in ar_selectors:
                    try:
                        elem = page.locator(ar_sel).first
                        if elem.is_visible(timeout=1000):
                            elem.click()
                            logger.info(f"[LabsGoogle] ✅ Đã chọn tỷ lệ khung hình '{target_ar}' trên Google Labs UI")
                            time.sleep(0.5)
                            break
                    except Exception:
                        pass

            # 4. Chọn Số lượng biến thể / bản tạo (Variants: 1x, x2, x3, x4)
            if variants:
                v_str = f"{variants}x" if not str(variants).endswith("x") else str(variants)
                alt_v_str = f"x{variants}"
                v_selectors = [
                    f"button:has-text('{v_str}')",
                    f"button:has-text('{alt_v_str}')",
                    f"div:has-text('{v_str}'):not(:has(*))"
                ]
                for v_sel in v_selectors:
                    try:
                        elem = page.locator(v_sel).first
                        if elem.is_visible(timeout=1000):
                            elem.click()
                            logger.info(f"[LabsGoogle] ✅ Đã chọn số bản tạo '{v_str}' trên Google Labs UI")
                            time.sleep(0.5)
                            break
                    except Exception:
                        pass

            # 5. Chọn Thời lượng (Duration: 4s, 6s, 8s)
            if duration:
                d_str = f"{duration}s"
                d_selectors = [
                    f"button:has-text('{d_str}')",
                    f"div:has-text('{d_str}'):not(:has(*))"
                ]
                for d_sel in d_selectors:
                    try:
                        elem = page.locator(d_sel).first
                        if elem.is_visible(timeout=1000):
                            elem.click()
                            logger.info(f"[LabsGoogle] ✅ Đã chọn thời lượng video '{d_str}' trên Google Labs UI")
                            time.sleep(0.5)
                            break
                    except Exception:
                        pass

            # 6. Chọn Model Veo từ Dropdown
            if model:
                model_label = model
                from core.veo_generator import VEO_MODEL_MAP
                if model in VEO_MODEL_MAP:
                    model_label = VEO_MODEL_MAP[model]

                try:
                    model_dropdown = page.locator("button:has-text('Veo'), div[role='combobox']:has-text('Veo'), div[role='button']:has-text('Veo')").first
                    if model_dropdown.is_visible(timeout=1000):
                        model_dropdown.click()
                        time.sleep(0.8)

                        opt = page.locator(f"[role='option']:has-text('{model_label[:10]}'), button:has-text('{model_label[:10]}'), div:has-text('{model_label[:10]}')").first
                        if opt.is_visible(timeout=1500):
                            opt.click()
                            logger.info(f"[LabsGoogle] ✅ Đã chọn Model '{model_label}' trên Google Labs UI")
                            time.sleep(0.5)
                except Exception as ex_m:
                    logger.warning(f"[LabsGoogle] Không chọn được Model dropdown: {ex_m}")

            # Đóng popover nếu đang mở
            try:
                page.keyboard.press("Escape")
                time.sleep(0.5)
            except Exception:
                pass

        except Exception as ex:
            logger.warning(f"[LabsGoogle] Lỗi thao tác cài đặt UI Google Labs: {ex}")

    def generate_video(
        self,
        prompt: str,
        out_path: Path,
        aspect_ratio: str = "9:16",
        duration: int = 8,
        variants: int = 1,
        model: str = None,
        quality: str = "1080p",
        timeout_sec: int = 600,
        worker_id: int = 0
    ) -> bool:
        """Automate labs.google to paste prompt, generate video, and download .mp4 output file.

        Args:
            prompt: Text description of video to render
            out_path: Path where output mp4 video should be saved
            aspect_ratio: Video aspect ratio ('9:16' or '16:9')
            duration: Video duration in seconds (4, 6, 8)
            variants: Number of video variants to generate (1, 2, 3, 4)
            model: Veo model name option
            quality: Video quality option ('1080p', '720p', '4K', '270p')
            timeout_sec: Maximum time to wait for rendering in seconds
            worker_id: Worker thread ID for session isolation

        Returns:
            bool: True if video rendered and downloaded successfully
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright chưa được cài đặt. Vui lòng chạy: pip install playwright")
            return False

        logger.info(f"[LabsGoogle Worker #{worker_id}] Bắt đầu tự động tạo video từ prompt trên labs.google: '{prompt[:60]}...'")

        try:
            target_session_dir = self.prepare_worker_session_dir(worker_id)
            with sync_playwright() as p:
                context = self.get_browser_context(p, headless=False, hidden=False, session_dir=target_session_dir)
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                page = context.new_page()
                page.set_default_timeout(60000)
                time.sleep(3.0)  # Đợi 3s ngay khi mở trình duyệt theo yêu cầu

                # Step 1: Navigate to Labs Google VideoFX
                logger.info(f"[LabsGoogle Worker #{worker_id}] Điều hướng tới {LABS_GOOGLE_URL}...")
                page.goto(LABS_GOOGLE_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)

                # Check if redirected to login page
                if "accounts.google.com" in page.url.lower() or "signin" in page.url.lower():
                    logger.error(f"[LabsGoogle Worker #{worker_id}] Chưa đăng nhập tài khoản Google! Vui lòng thực hiện Đăng Nhập Labs Google trước.")
                    self._screenshot(page, f"labs_google_login_required_{worker_id}")
                    context.close()
                    return False

                self._screenshot(page, f"labs_01_landed_{worker_id}")

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
                            logger.info(f"[LabsGoogle Worker #{worker_id}] Bấm nút vào Dự Án Mới / Công Cụ: {l_sel}")
                            btn.click()
                            time.sleep(4)
                            self._screenshot(page, f"labs_01b_workspace_opened_{worker_id}")

                            if "accounts.google.com" in page.url.lower() or "signin" in page.url.lower():
                                logger.error(f"[LabsGoogle Worker #{worker_id}] Yêu cầu đăng nhập tài khoản Google để tiếp tục! Vui lòng mở tab Google Labs Session trong ứng dụng để đăng nhập 1 lần.")
                                self._screenshot(page, f"labs_google_login_required_{worker_id}")
                                context.close()
                                return False
                            break
                    except Exception:
                        pass

                # Step 1.8: Tự động bấm chọn các cài đặt (Aspect Ratio, Duration, Variants, Model) khớp cấu hình Tool
                self._configure_labs_settings(page, aspect_ratio=aspect_ratio, duration=duration, variants=variants, model=model)

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

                # Step 4: Submit prompt by pressing Enter & Click Submit Button if available
                logger.info("[LabsGoogle] Nhấn phím Enter để gửi prompt...")
                page.keyboard.press("Enter")
                time.sleep(1.0)
                page.keyboard.press("Enter")

                # Backup: Tìm và click nút Generate/Tạo/Arrow gửi prompt nếu có
                submit_selectors = [
                    "button[aria-label*='Tạo' i]",
                    "button[aria-label*='Generate' i]",
                    "button[aria-label*='Create' i]",
                    "button[aria-label*='Send' i]",
                    "button:has-text('Tạo')",
                    "button:has-text('Generate')",
                    "button:has-text('Create')",
                    "button[type='submit']"
                ]
                for s_sel in submit_selectors:
                    try:
                        s_btn = page.locator(s_sel).first
                        if s_btn.is_visible(timeout=1000):
                            s_btn.click()
                            logger.info(f"[LabsGoogle] Clicked submit button: '{s_sel}'")
                            break
                    except Exception:
                        pass

                logger.info("[LabsGoogle] Đã gửi yêu cầu sinh video. Đang chờ 50 giây cho Google Labs render hoàn tất...")
                self._screenshot(page, "labs_03_generating")
                time.sleep(50)

                # Step 5: Wait for generated video & download via 3-dots menu -> Tải xuống / Download -> 1080p
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

                    # 0. Tự động phát hiện & đóng Popup/Modal đè màn hình (Overlay / Detail Picker Popup)
                    try:
                        overlay_selectors = [
                            "[role='dialog']",
                            "div:has-text('Thêm vào câu lệnh')",
                            "div:has-text('Tìm kiếm thành phần')",
                            "div:has-text('Tải nội dung nghe nhìn lên')"
                        ]
                        has_overlay = False
                        for o_sel in overlay_selectors:
                            try:
                                if page.locator(o_sel).first.is_visible(timeout=500):
                                    has_overlay = True
                                    break
                            except Exception:
                                pass

                        if has_overlay:
                            logger.info("[LabsGoogle] ⚠️ Phát hiện Popup/Modal đè màn hình, tiến hành bấm Escape & đóng...")
                            # Phím Escape đóng modal
                            page.keyboard.press("Escape")
                            time.sleep(0.3)
                            page.keyboard.press("Escape")

                            # Click nút đóng X nếu có
                            try:
                                close_btns = page.locator("button[aria-label*='Đóng' i], button[aria-label*='Close' i], button[aria-label*='dismiss' i], [role='dialog'] button:has-text('×'), [role='dialog'] button:has-text('✕')")
                                if close_btns.count() > 0 and close_btns.first.is_visible(timeout=500):
                                    close_btns.first.click(force=True)
                            except Exception:
                                pass

                            # Click ra góc màn hình ngoài backdrop
                            try:
                                page.mouse.click(20, 20)
                            except Exception:
                                pass
                            time.sleep(0.8)
                    except Exception as ex_ov:
                        logger.warning(f"[LabsGoogle] Lỗi xử lý overlay popup: {ex_ov}")

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
                                if "khác" in b_aria or "more" in b_aria or "more_vert" in b_text or "..." in b_text or "⋮" in b_text or "download" in b_aria or "download" in b_text or "tải" in b_aria or "tải" in b_text:
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

                                # 3. Tìm DOM element 'Tải xuống' / 'Download' hỗ trợ cả Tiếng Việt & Tiếng Anh
                                dl_menu_item = None
                                try:
                                    dl_selectors = [
                                        "text=/Tải xuống|Download|Export/i",
                                        "[role='menuitem']:has-text('Tải xuống')",
                                        "[role='menuitem']:has-text('Download')",
                                        "[role='menuitem']:has-text('Export')",
                                        "li:has-text('Tải xuống')",
                                        "li:has-text('Download')",
                                        "div:has-text('Tải xuống')",
                                        "div:has-text('Download')",
                                        "span:has-text('Tải xuống')",
                                        "span:has-text('Download')"
                                    ]
                                    for dl_sel in dl_selectors:
                                        cand = page.locator(dl_sel)
                                        if cand.count() > 0 and cand.first.is_visible(timeout=1000):
                                            dl_menu_item = cand.first
                                            break
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
