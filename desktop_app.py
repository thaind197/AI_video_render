"""
Veo Studio AI PRO - Desktop Application Launcher
Khởi chạy hệ thống dạng ứng dụng Native Desktop trên Windows.
Sử dụng Microsoft Edge App Mode + Hidden Console Server.
"""
import sys
import os
import time
import socket
import threading
import urllib.request
import io
import subprocess
import shutil
import webbrowser
import ctypes
from pathlib import Path
from datetime import datetime


# ── [BƯỚC 1] Monkey-patch subprocess để child process không tạo console ──
# Khi chạy ở --windowed mode, mọi subprocess.Popen mặc định sẽ tạo console mới.
# Patch này đảm bảo tất cả child process (FFmpeg, PowerShell, Chrome...) ẩn console.
if sys.platform == "win32":
    _CREATE_NO_WINDOW = 0x08000000
    _original_Popen_init = subprocess.Popen.__init__

    def _patched_Popen_init(self, *args, **kwargs):
        # Chỉ inject flag khi caller CHƯA set creationflags
        if kwargs.get("creationflags", 0) == 0:
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        _original_Popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_Popen_init


# ── Safe stdout/stderr cho mọi Windows Locale ───────────────────────────
class SafeWriter:
    def __init__(self, original_stream):
        self.stream = original_stream

    def write(self, data):
        if not data or not self.stream:
            return
        try:
            self.stream.write(data)
        except Exception:
            try:
                encoding = getattr(self.stream, 'encoding', None) or 'utf-8'
                safe_data = data.encode(encoding, errors='replace').decode(encoding, errors='replace')
                self.stream.write(safe_data)
            except Exception:
                pass

    def flush(self):
        if self.stream and hasattr(self.stream, 'flush'):
            try:
                self.stream.flush()
            except Exception:
                pass

if sys.stdout is None or not hasattr(sys.stdout, 'write'):
    sys.stdout = io.StringIO()
else:
    sys.stdout = SafeWriter(sys.stdout)

if sys.stderr is None or not hasattr(sys.stderr, 'write'):
    sys.stderr = io.StringIO()
else:
    sys.stderr = SafeWriter(sys.stderr)


# ── Crash Log ───────────────────────────────────────────────────────────
def get_log_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "veo_studio_crash.log")
    return os.path.join(os.path.dirname(__file__), "veo_studio_crash.log")

def write_log(msg):
    try:
        with open(get_log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# ── Đường dẫn PyInstaller bundle ────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

write_log(f"App started. frozen={getattr(sys, 'frozen', False)}, BASE_DIR={BASE_DIR}")


# ── Network Utilities ───────────────────────────────────────────────────
def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def find_free_port(start_port: int = 8000) -> int:
    port = start_port
    while is_port_in_use(port):
        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stats", timeout=1)
            if req.status == 200:
                return port
        except Exception:
            pass
        port += 1
    return port

def wait_for_server(url: str, timeout: float = 60.0) -> bool:
    """Chờ server sẵn sàng, timeout mặc định 60 giây."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.urlopen(url, timeout=2)
            if req.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ── FastAPI Server Runner ───────────────────────────────────────────────
def run_fastapi_server(port: int):
    try:
        write_log(f"Importing server modules...")
        import uvicorn
        from server import app
        write_log(f"Server modules imported. Starting uvicorn on port {port}...")
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None)
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        server.run()
    except Exception as e:
        write_log(f"FATAL: FastAPI server failed: {e}")
        import traceback
        write_log(traceback.format_exc())


# ── Browser App Window ──────────────────────────────────────────────────
def find_browser_exe():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


# ── Main ────────────────────────────────────────────────────────────────
def main():
    try:
        port = 8000
        server_already_running = False

        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stats", timeout=1)
            if req.status == 200:
                server_already_running = True
                write_log(f"Server already running on port {port}")
        except Exception:
            server_already_running = False

        if not server_already_running:
            port = find_free_port(8000)
            server_thread = threading.Thread(target=run_fastapi_server, args=(port,), daemon=True)
            server_thread.start()
            write_log(f"Server thread started on port {port}. Waiting up to 60s...")

            target_url = f"http://127.0.0.1:{port}/"
            if not wait_for_server(target_url, timeout=60.0):
                write_log("FATAL: Server did not respond within 60 seconds!")
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "Lỗi: Server không thể khởi động.\n\n"
                    "Vui lòng kiểm tra:\n"
                    "1. Đã giải nén (Extract All) đầy đủ thư mục ứng dụng\n"
                    "2. Thư mục không có ký tự đặc biệt trong đường dẫn\n"
                    "3. Không có phần mềm diệt virus chặn\n\n"
                    "Chi tiết: xem file veo_studio_crash.log",
                    "Lỗi Khởi Động Server",
                    0x10
                )
                os._exit(1)

        write_log(f"Server is ready on port {port}!")

        # Kiểm tra Remote Version (Firebase)
        try:
            from version import FULL_NAME, check_remote_version
            remote_info = check_remote_version()
            if remote_info.get("is_blocked"):
                msg = (
                    f"CHẶN TRUY CẬP PHIÊN BẢN CŨ ({FULL_NAME}):\n\n"
                    f"{remote_info.get('update_message', 'Phiên bản cũ hoặc đang bảo trì.')}\n\n"
                    f"Phiên bản tối thiểu: v{remote_info.get('min_version')}\n"
                    f"Phiên bản mới nhất: v{remote_info.get('latest_version')}\n\n"
                    "Trình duyệt sẽ mở trang tải bản mới nhất."
                )
                download_url = remote_info.get("download_url", "https://veostudio.ai/download")
                try:
                    webbrowser.open(download_url)
                except Exception:
                    pass
                ctypes.windll.user32.MessageBoxW(0, msg, "Cập Nhật Phiên Bản", 0x10)
                os._exit(0)
        except Exception as ve:
            write_log(f"Version check error (non-fatal): {ve}")

        # Mở cửa sổ trình duyệt dạng App Mode
        target_url = f"http://127.0.0.1:{port}/"
        browser_bin = find_browser_exe()

        if browser_bin:
            user_data = os.path.join(
                os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                "VeoStudioAI_AppData"
            )
            cmd = [
                browser_bin,
                f"--app={target_url}",
                f"--user-data-dir={user_data}",
                "--window-size=1420,920",
                "--disable-features=Translate",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            write_log(f"Opening: {os.path.basename(browser_bin)} --app={target_url}")
            subprocess.Popen(cmd)
        else:
            write_log("No Edge/Chrome found. Opening default browser.")
            webbrowser.open(target_url)

        # Giữ server sống vô hạn (daemon thread cần main thread tồn tại)
        write_log("Keep-alive loop started.")
        while True:
            time.sleep(10)

    except Exception as e:
        write_log(f"FATAL CRASH: {e}")
        import traceback
        write_log(traceback.format_exc())
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Lỗi khởi chạy Veo Studio AI PRO:\n\n{e}\n\n"
                "Xem file veo_studio_crash.log để biết chi tiết.",
                "Lỗi Khởi Chạy",
                0x10
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
