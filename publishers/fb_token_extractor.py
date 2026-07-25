"""
Facebook Token Extractor & Page Scanner
========================================
Dùng Playwright với browser session đã đăng nhập để:
1. Intercept request URL/body (sync, an toàn) → bắt EAA token
2. JS evaluate scan HTML/localStorage sau khi page load
3. Gọi GET /me/accounts → danh sách Pages

FIXES:
- import time (fix NameError)
- Không dùng response.text() trong event callback (gây CancelledError async)
- wait_until="domcontentloaded" thay vì "networkidle" (FB không bao giờ đạt networkidle)
"""

import re
import time
import logging
import requests
from config.settings import FACEBOOK_SESSION_DIR

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"

# JS scan toàn bộ page để tìm EAA token
_JS_SCAN = r"""(() => {
    const scripts = document.querySelectorAll('script');
    for (const s of scripts) {
        const m = s.textContent.match(/EAA[A-Za-z0-9\-_]{80,}/);
        if (m) return m[0];
    }
    const hm = document.documentElement.innerHTML.match(/EAA[A-Za-z0-9\-_]{80,}/);
    if (hm) return hm[0];
    try {
        for (const k of Object.keys(localStorage)) {
            const v = localStorage.getItem(k) || '';
            const lm = v.match(/EAA[A-Za-z0-9\-_]{50,}/);
            if (lm) return lm[0];
        }
    } catch(e) {}
    return null;
})()"""

_JS_SDK = "typeof window.FB !== 'undefined' && window.FB.getAccessToken ? window.FB.getAccessToken() : null"


def _parse_token(text: str):
    m = re.search(r'EAA[A-Za-z0-9\-_]{50,}', text)
    return m.group(0) if m else None


def get_user_token_from_session() -> str | None:
    """Mở browser với session FB đã lưu, bắt token từ requests + JS."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright chưa cài. Chạy: pip install playwright && playwright install chromium")
        return None

    tokens_found: list[str] = []

    def on_request(request):
        """Chỉ đọc URL và post_data (đều là string sync) — KHÔNG gọi response.text()."""
        try:
            token = _parse_token(request.url)
            if token:
                tokens_found.append(token)
                return
            body = request.post_data or ""
            if body:
                token = _parse_token(body)
                if token:
                    tokens_found.append(token)
        except Exception:
            pass

    logger.info("[FB Token] Đang mở browser với session Facebook...")
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(FACEBOOK_SESSION_DIR),
                headless=False,
                no_viewport=True,
                args=['--start-maximized', '--disable-blink-features=AutomationControlled', '--no-sandbox'],
            )
            page = context.new_page()
            page.on("request", on_request)

            logger.info("[FB Token] Tải facebook.com (domcontentloaded)...")
            try:
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"[FB Token] goto warning (bình thường): {type(e).__name__}")

            time.sleep(6)  # Chờ background XHR/GraphQL requests

            # JS extraction
            for name, js in [("FB SDK", _JS_SDK), ("Scan HTML", _JS_SCAN)]:
                if tokens_found:
                    break
                try:
                    result = page.evaluate(js)
                    if result and isinstance(result, str) and result.startswith("EAA"):
                        tokens_found.append(result)
                        logger.info(f"[FB Token] ✅ {name}: {result[:25]}...")
                except Exception:
                    pass

            # Navigate thêm để trigger API calls
            extra = [
                "https://www.facebook.com/settings/",
                "https://www.facebook.com/pages/",
                "https://business.facebook.com/",
            ]
            for url in extra:
                if tokens_found:
                    break
                logger.info(f"[FB Token] Thử: {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                time.sleep(4)
                try:
                    result = page.evaluate(_JS_SCAN)
                    if result and result.startswith("EAA"):
                        tokens_found.append(result)
                        logger.info(f"[FB Token] ✅ Từ {url}: {result[:25]}...")
                except Exception:
                    pass

            context.close()

    except Exception as e:
        logger.exception(f"[FB Token] Lỗi: {e}")
        return None

    if tokens_found:
        best = max(set(tokens_found), key=len)
        logger.info(f"[FB Token] ✅ {len(tokens_found)} token(s) tìm thấy. Dùng: {best[:30]}...")
        return best

    logger.warning("[FB Token] ❌ Không bắt được token EAA từ session.")
    return None


def get_managed_pages(user_token: str) -> list[dict]:
    """Gọi Graph API GET /me/accounts → list Pages."""
    try:
        resp = requests.get(
            f"{GRAPH_API_BASE}/me/accounts",
            params={"access_token": user_token, "fields": "id,name,category,access_token,fan_count"},
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get("data", [])
        logger.info(f"[FB Pages] ✅ {len(pages)} Pages: {[p['name'] for p in pages]}")
        return pages
    except requests.HTTPError as e:
        try:
            logger.error(f"[FB Pages] API Error: {e.response.json()}")
        except Exception:
            logger.error(f"[FB Pages] HTTP Error: {e}")
        return []
    except Exception as e:
        logger.exception(f"[FB Pages] Lỗi: {e}")
        return []


def scan_facebook_pages() -> dict:
    """Main: extract token + list pages. Returns {success, token, pages, error}."""
    logger.info("[FB Scanner] Bắt đầu quét Pages Facebook...")
    token = get_user_token_from_session()
    if not token:
        return {
            "success": False,
            "error": (
                "Không lấy được Access Token. "
                "Facebook không nhúng token EAA trong HTML thông thường. "
                "Hãy thử nhập token thủ công từ Facebook Developer Tools."
            ),
            "pages": [],
        }
    pages = get_managed_pages(token)
    if not pages:
        return {
            "success": False,
            "token": token,
            "error": "Không tìm thấy Pages nào. Bạn cần có ít nhất 1 Facebook Page với quyền admin.",
            "pages": [],
        }
    return {"success": True, "token": token, "pages": pages, "error": None}
