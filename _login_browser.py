"""
Helper: Mở Chrome hệ thống (hoặc Edge) trực tiếp bằng Python subprocess với cờ buộc hiển thị (STARTUPINFO & SHOWWINDOW)
Kết hợp Win32 user32.dll API để khôi phục cửa sổ nếu bị ẩn (SW_SHOW) hoặc bị nháy ẩn/định vị ngoài rìa màn hình (-32000),
ép nổi lên mặt trên cùng của màn hình máy tính (Foreground Window).

Usage:
    python _login_browser.py <session_dir> <login_url>
"""
import sys
import os
import time
import subprocess
import ctypes
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def is_browser_running(proc: subprocess.Popen, session_dir_str: str) -> bool:
    """Kiểm tra chính xác xem trình duyệt cho session_dir có đang chạy không."""
    # 1. Kiểm tra trực tiếp tiến trình chính (proc) mà Python đã mở
    if proc and proc.poll() is None:
        return True

    # 2. Nếu proc chính thoái ra do ủy quyền sub-process, kiểm tra bằng commandline trong hệ thống
    norm_dir = session_dir_str.lower().replace("/", "\\")
    try:
        res = subprocess.run(
            ["cmd.exe", "/c", 'wmic process where "name=\'chrome.exe\' or name=\'msedge.exe\'" get commandline'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if norm_dir in res.stdout.lower():
            return True
    except Exception as e:
        print(f"[LoginBrowser] WMIC Check Error: {e}", flush=True)

    try:
        # Fallback Powershell check
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | Where-Object {{ $_.CommandLine -like '*{norm_dir}*' }} | Measure-Object | Select-Object -ExpandProperty Count"
        ]
        res_ps = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        count = int(res_ps.stdout.strip())
        if count > 0:
            return True
    except Exception:
        pass

    return False


def kill_orphan_process(session_dir_str: str):
    """Kill bất kỳ tiến trình chrome/edge ngầm nào đang giữ session_dir"""
    norm_dir = session_dir_str.lower().replace("/", "\\")
    try:
        res = subprocess.run(
            ["cmd.exe", "/c", 'wmic process where "name=\'chrome.exe\' or name=\'msedge.exe\'" get commandline,processid'],
            capture_output=True,
            text=True,
            timeout=5
        )
        lines = res.stdout.splitlines()
        for line in lines:
            if norm_dir in line.lower():
                parts = line.strip().split()
                if parts and parts[-1].isdigit():
                    pid = parts[-1]
                    print(f"[LoginBrowser] Kill tiến trình ngầm mồ côi PID={pid}", flush=True)
                    subprocess.run(["taskkill", "/F", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[LoginBrowser] Warning cleanup orphan: {e}", flush=True)


def force_unhide_and_top(target_pid: int = 0):
    """Tìm cửa sổ của Chrome/Edge và BUỘC hiển thị trên màn hình chính, đặt lại tọa độ nếu bị đẩy ra ngoài viền màn hình."""
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

        def callback(hwnd, extra):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            cls_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buff, 256)
            cls_name = cls_buff.value

            # Nếu cửa sổ thuộc PID ta vừa chạy, hoặc có class là Chrome_WidgetWin_1 / Chrome_WidgetWin_0 / Edge
            if cls_name in ['Chrome_WidgetWin_1', 'Chrome_WidgetWin_0', 'Edge_WidgetWin_1'] or (target_pid > 0 and pid.value == target_pid):
                # KHÔNG BỎ QUA NGAY CẢ KHI BỊ ẨN: Gọi SW_SHOW (5) và SW_RESTORE (9) để buộc hiện ra
                user32.ShowWindow(hwnd, 5)  # SW_SHOW (bật hiển thị nếu bị gán cờ SW_HIDE)
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE (khôi phục nếu bị minimize)

                # Kiểm tra tọa độ cửa sổ: nếu bị Playwright gán cờ ẩn (-32000,-32000), lập tức đưa về chính giữa màn hình
                rect = (ctypes.c_int * 4)()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                left, top = rect[0], rect[1]
                if left < -100 or top < -100:
                    print(f"[LoginBrowser] Phát hiện cửa sổ bị giấu off-screen (left={left}, top={top}), đang kéo lại màn hình...", flush=True)
                    user32.SetWindowPos(hwnd, 0, 50, 50, 1280, 800, 0x0040)  # SWP_SHOWWINDOW

                user32.ShowWindow(hwnd, 3)  # SW_SHOWMAXIMIZED (Maximized toàn màn hình)
                user32.SetForegroundWindow(hwnd)  # Ép lên top desktop
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
    except Exception as e:
        print(f"[LoginBrowser] Error force unhide: {e}", flush=True)


def main():
    if len(sys.argv) < 3:
        print("Usage: python _login_browser.py <session_dir> <login_url>")
        sys.exit(1)

    session_dir = str(Path(sys.argv[1]).resolve())
    login_url = sys.argv[2]

    print(f"[LoginBrowser] ABSOLUTE session_dir = {session_dir}", flush=True)
    print(f"[LoginBrowser] login_url            = {login_url}", flush=True)

    # 1. Kill orphan process
    kill_orphan_process(session_dir)

    # 2. Clean lock files
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        lock_path = Path(session_dir) / lock_file
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    # 3. Find Browser EXE
    browser_exe = find_browser()
    if not browser_exe:
        print("[LoginBrowser] ERROR: Chrome/Edge not found!", flush=True)
        sys.exit(1)

    print(f"[LoginBrowser] Browser EXE: {browser_exe}", flush=True)

    # 4. Cấu hình cờ STARTUPINFO để đảm bảo Windows Kernel mở GUI hiển thị Maximized (chống kế thừa cờ ẩn)
    startupinfo = None
    creation_flags = 0
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 3  # SW_SHOWMAXIMIZED (hoặc 1 SW_SHOWNORMAL)
        # Bứt phá khỏi luồng parent ẩn (như background runner hoặc job ẩn)
        creation_flags = 0x00000010 | 0x00000200  # CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP

    # Tham số mở trình duyệt: đè lại mọi tọa độ off-screen (-32000,-32000) từng bị lưu trước đó
    cmd_args = [
        browser_exe,
        f'--user-data-dir={session_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        '--new-window',
        '--window-position=50,50',
        '--window-size=1280,800',
        '--start-maximized',
        login_url
    ]

    print(f"[LoginBrowser] Khởi chạy trình duyệt trực tiếp với subprocess.Popen: {' '.join(cmd_args[:3])} ...", flush=True)
    proc = subprocess.Popen(cmd_args, startupinfo=startupinfo, creationflags=creation_flags)
    print(f"[LoginBrowser] Tiến trình trình duyệt đã mở! PID = {proc.pid}", flush=True)

    # Đợi 1.5s - 3s - 5s để ép cửa sổ hiển thị lên mặt trước màn hình và tháo gỡ cờ ẩn
    for delay in [1.5, 1.5, 2.0]:
        time.sleep(delay)
        force_unhide_and_top(proc.pid)

    # 5. Theo dõi cho đến khi người dùng thực sự đóng cửa sổ trình duyệt
    max_wait = 600
    elapsed = 5
    print("[LoginBrowser] Monitoring browser window... Please log in and close browser when done.", flush=True)
    while elapsed < max_wait:
        time.sleep(3)
        elapsed += 3
        if not is_browser_running(proc, session_dir):
            print("[LoginBrowser] Detected browser window closed by user.", flush=True)
            break

    print("[LoginBrowser] Completed. Session data saved!", flush=True)


if __name__ == "__main__":
    main()
