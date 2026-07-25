import os
import time
import math
import logging
import requests
from pathlib import Path
from publishers.base_publisher import BasePublisher
from config.settings import FACEBOOK_SESSION_DIR

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB


class FacebookPublisher(BasePublisher):
    """Facebook Reels Auto Publisher.
    Priority 1: Meta Graph API (if FB_PAGE_ACCESS_TOKEN + FB_PAGE_ID configured).
    Priority 2: Playwright browser automation (browser session — hidden off-screen).

    Supports multi-account: pass profile_id to use a specific FB profile session.
    """

    def __init__(self, profile_id: str = None):
        if profile_id:
            # Dùng session dir của profile cụ thể
            from publishers.fb_profile_manager import FBProfileManager
            mgr = FBProfileManager()
            session_dir = mgr.get_session_dir(profile_id)
            profile = mgr.get_profile(profile_id)
            name = profile["name"] if profile else profile_id
            super().__init__(f"Facebook [{name}]", session_dir)
            self._profile_id = profile_id
        else:
            # Backward compat: dùng session mặc định
            super().__init__("Facebook", FACEBOOK_SESSION_DIR)
            self._profile_id = "default"

        self.page_access_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
        self.page_id = os.getenv("FB_PAGE_ID", "").strip()

    def login_manual(self):
        self.interactive_login("https://www.facebook.com/")

    # ─────────────────────────────────────────────────────────
    # PUBLIC: post_video
    # ─────────────────────────────────────────────────────────
    def post_video(self, video_path: Path, caption: str, tags: list = None) -> bool:
        if not video_path.exists():
            logger.error(f"File video không tồn tại: {video_path}")
            return False

        full_caption = caption.strip()
        if tags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags[:20])
            full_caption += f"\n\n{tag_str}"

        if self.page_access_token and self.page_id:
            logger.info("Dùng Meta Graph API để đăng Facebook Reels...")
            return self._post_via_graph_api(video_path, full_caption)
        else:
            logger.info("Dùng Playwright browser automation (hidden mode)...")
            return self._post_via_playwright(video_path, full_caption)

    # ─────────────────────────────────────────────────────────
    # METHOD 1: Meta Graph API
    # ─────────────────────────────────────────────────────────
    def _post_via_graph_api(self, video_path: Path, caption: str) -> bool:
        token = self.page_access_token
        page_id = self.page_id
        file_size = video_path.stat().st_size

        try:
            # Phase 1: Start upload session
            start_r = requests.post(
                f"{GRAPH_API_BASE}/{page_id}/videos",
                data={
                    "upload_phase": "start",
                    "access_token": token,
                    "file_size": file_size,
                },
                timeout=30,
            )
            start_r.raise_for_status()
            start_data = start_r.json()
            session_id = start_data["upload_session_id"]
            start_offset = int(start_data["start_offset"])
            end_offset = int(start_data["end_offset"])
            logger.info(f"[FB API] Upload session: {session_id}")

            # Phase 2: Transfer chunks
            with open(video_path, "rb") as f:
                chunk_n = 0
                while start_offset < file_size:
                    chunk_size = end_offset - start_offset
                    f.seek(start_offset)
                    chunk_data = f.read(chunk_size)
                    transfer_r = requests.post(
                        f"{GRAPH_API_BASE}/{page_id}/videos",
                        data={
                            "upload_phase": "transfer",
                            "upload_session_id": session_id,
                            "start_offset": start_offset,
                            "access_token": token,
                        },
                        files={"video_file_chunk": (video_path.name, chunk_data, "application/octet-stream")},
                        timeout=120,
                    )
                    transfer_r.raise_for_status()
                    transfer_data = transfer_r.json()
                    start_offset = int(transfer_data["start_offset"])
                    end_offset = int(transfer_data["end_offset"])
                    chunk_n += 1
                    logger.info(f"[FB API] Chunk {chunk_n}: offset {start_offset}/{file_size}")

            # Phase 3: Publish
            publish_r = requests.post(
                f"{GRAPH_API_BASE}/{page_id}/videos",
                data={
                    "upload_phase": "finish",
                    "upload_session_id": session_id,
                    "access_token": token,
                    "video_state": "PUBLISHED",
                    "description": caption,
                    "title": caption[:100],
                },
                timeout=60,
            )
            publish_r.raise_for_status()
            logger.info(f"[FB API] ✅ Đăng Reels thành công! {publish_r.json()}")
            return True

        except requests.HTTPError as e:
            try:
                logger.error(f"[FB API] HTTP {e.response.status_code} — {e.response.json()}")
            except Exception:
                logger.error(f"[FB API] HTTP Error: {e}")
            return False
        except Exception as e:
            logger.exception(f"[FB API] Lỗi: {e}")
            return False

    # ─────────────────────────────────────────────────────────
    # METHOD 2: Playwright Browser Automation (Hidden Mode)
    # Browser chạy ẩn ngoài màn hình (headless=False nhưng off-screen)
    # → FB không phát hiện automation, file input vẫn render bình thường
    # ─────────────────────────────────────────────────────────
    def _post_via_playwright(self, video_path: Path, full_caption: str) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright chưa cài. Chạy: pip install playwright && playwright install chromium")
            return False

        logger.info(f"[FB Playwright] Bắt đầu đăng Reels (hidden mode): {video_path.name}")

        try:
            with sync_playwright() as p:
                # hidden=True: cửa sổ ẩn ngoài màn hình, FB không detect automation
                context = self.get_browser_context(p, headless=False, hidden=True)
                page = context.new_page()
                page.set_default_timeout(60000)

                try:
                    # ── Step 1: Navigate ──
                    logger.info("[FB Playwright] Điều hướng đến Facebook Reels...")
                    page.goto("https://www.facebook.com/reels/create", wait_until="domcontentloaded", timeout=45000)
                    time.sleep(4)

                    # ── Step 2: Check login ──
                    if "login" in page.url.lower() or "checkpoint" in page.url.lower():
                        logger.error("[FB Playwright] Phiên hết hạn! Vui lòng đăng nhập lại.")
                        self._screenshot(page, "fb_login_expired")
                        return False

                    logger.info(f"[FB Playwright] URL: {page.url} | File inputs: {page.locator('input[type=file]').count()}")
                    self._screenshot(page, "fb_01_landed")

                    # ── Step 3: Click upload area ──
                    for sel in [
                        "div[role='button']:has-text('Tải lên')",
                        "div[role='button']:has-text('Upload')",
                        "div[role='button']:has-text('Thêm video')",
                        "div[role='button']:has-text('Add video')",
                        "div[role='button']:has-text('Chọn video')",
                        "[aria-label*='Tải lên']",
                        "[aria-label*='Upload']",
                    ]:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=3000):
                                btn.click()
                                time.sleep(2)
                                logger.info(f"[FB Playwright] Click upload: {sel}")
                                break
                        except Exception:
                            pass

                    # ── Step 4: Set file ──
                    file_inputs = page.locator("input[type='file']")
                    count = file_inputs.count()
                    logger.info(f"[FB Playwright] File inputs: {count}")

                    if count == 0:
                        logger.error("[FB Playwright] Không tìm thấy file input")
                        self._screenshot(page, f"fb_no_input_{video_path.stem}")
                        return False

                    uploaded = False
                    for i in range(count):
                        try:
                            file_inputs.nth(i).set_input_files(str(video_path))
                            logger.info(f"[FB Playwright] Set file → input #{i}: {video_path.name}")
                            uploaded = True
                            break
                        except Exception as ex:
                            logger.warning(f"[FB Playwright] Input #{i} lỗi: {ex}")

                    if not uploaded:
                        logger.error("[FB Playwright] Không set được file vào input nào")
                        self._screenshot(page, f"fb_upload_fail_{video_path.stem}")
                        return False

                    # ── Step 5: Poll upload completion (max 20 phút) ──
                    logger.info("[FB Playwright] Chờ upload xong (poll 5s/lần, tối đa 20 phút)...")
                    NEXT_SELS = [
                        "button:has-text('Tiếp')", "button:has-text('Tiếp theo')",
                        "button:has-text('Next')", "div[role='button']:has-text('Tiếp')",
                        "div[role='button']:has-text('Chia sẻ')", "div[role='button']:has-text('Đăng')",
                        "[aria-label='Tiếp']", "[aria-label='Tiếp theo']",
                    ]
                    upload_done = False
                    for poll in range(240):  # 240 × 5s = 20 phút
                        for sel in NEXT_SELS:
                            try:
                                if page.locator(sel).first.is_visible(timeout=1000):
                                    logger.info(f"[FB Playwright] ✅ Upload xong sau {poll*5}s — thấy: {sel}")
                                    upload_done = True
                                    break
                            except Exception:
                                pass
                        if upload_done:
                            break
                        if poll > 0 and poll % 6 == 0:
                            logger.info(f"[FB Playwright] ⏳ Uploading... {poll*5}s | URL: {page.url[:70]}")
                        time.sleep(5)

                    if not upload_done:
                        logger.warning("[FB Playwright] Timeout 20 phút. Thử tiếp tục các bước sau...")

                    self._screenshot(page, "fb_02_after_upload")
                    time.sleep(2)

                    # ── Step 6: Click "Tiếp" qua màn hình edit ──
                    for step_n in range(4):
                        if page.locator("div[contenteditable='true'], div[role='textbox']").count() > 0:
                            logger.info(f"[FB Playwright] Thấy caption box (bước {step_n})")
                            break
                        clicked = False
                        for sel in [
                            "button:has-text('Tiếp')", "button:has-text('Tiếp theo')",
                            "button:has-text('Next')", "div[role='button']:has-text('Tiếp')",
                            "div[role='button']:has-text('Tiếp theo')",
                            "[aria-label='Tiếp']", "[aria-label='Tiếp theo']", "[aria-label='Next']",
                        ]:
                            try:
                                btn = page.locator(sel).first
                                if btn.is_visible(timeout=3000):
                                    btn.click()
                                    logger.info(f"[FB Playwright] Click Tiếp #{step_n+1}: {sel}")
                                    time.sleep(3)
                                    clicked = True
                                    break
                            except Exception:
                                pass
                        if not clicked:
                            logger.info(f"[FB Playwright] Không còn nút Tiếp ở bước {step_n}")
                            break

                    self._screenshot(page, "fb_03_caption_screen")

                    # ── Step 7: Điền caption ──
                    caption_filled = False
                    for sel in [
                        "div[contenteditable='true']", "div[role='textbox']", "textarea",
                        "[placeholder*='mô tả']", "[placeholder*='Thêm mô tả']",
                        "[placeholder*='description']", "[placeholder*='Add a description']",
                    ]:
                        try:
                            area = page.locator(sel).first
                            if area.is_visible(timeout=4000):
                                area.click()
                                time.sleep(1)
                                area.fill(full_caption)
                                time.sleep(2)
                                caption_filled = True
                                logger.info(f"[FB Playwright] ✅ Caption: {len(full_caption)} ký tự ({sel})")
                                break
                        except Exception:
                            pass
                    if not caption_filled:
                        logger.warning("[FB Playwright] Không điền được caption, đăng không mô tả...")

                    # ── Step 8: Click Đăng ──
                    posted = False
                    for sel in [
                        "div[role='button']:has-text('Chia sẻ')",
                        "div[role='button']:has-text('Đăng')",
                        "div[role='button']:has-text('Publish')",
                        "div[role='button']:has-text('Post')",
                        "button:has-text('Chia sẻ')",
                        "button:has-text('Đăng')",
                        "button:has-text('Publish')",
                        "[aria-label='Chia sẻ']",
                        "[aria-label='Đăng']",
                        "[aria-label='Publish']",
                    ]:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=5000):
                                btn.click()
                                logger.info(f"[FB Playwright] ✅ Đã nhấn Đăng: {sel}")
                                time.sleep(15)  # Chờ FB xử lý
                                self._screenshot(page, f"fb_04_published_{video_path.stem}")
                                posted = True
                                break
                        except Exception:
                            pass

                    if not posted:
                        logger.error("[FB Playwright] Không tìm thấy nút Đăng/Chia sẻ")
                        self._screenshot(page, f"fb_05_no_publish_btn_{video_path.stem}")

                    return posted

                finally:
                    # ★ LUÔN đóng browser dù thành công hay thất bại ★
                    logger.info("[FB Playwright] Đóng browser...")
                    try:
                        context.close()
                    except Exception:
                        pass

        except Exception as e:
            err_msg = str(e)
            if "TargetClosedError" in err_msg or "Target page, context or browser has been closed" in err_msg:
                logger.error("[FB Playwright] Browser bị đóng sớm. Vui lòng thử lại.")
            else:
                logger.exception(f"[FB Playwright] Lỗi: {e}")
            return False

    # ─────────────────────────────────────────────────────────
    # HELPER: Debug screenshot
    # ─────────────────────────────────────────────────────────
    def _screenshot(self, page, name: str):
        try:
            from config.settings import BASE_DIR
            log_dir = BASE_DIR / "storage" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{name}.png"
            page.screenshot(path=str(path))
            logger.info(f"[FB] Screenshot: {path}")
        except Exception as ex:
            logger.warning(f"[FB] Không lưu được screenshot: {ex}")
