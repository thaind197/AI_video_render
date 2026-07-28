"""
Helper: Mở Chrome / Edge cho người dùng đăng nhập thủ công
Chạy như 1 tiến trình Python riêng biệt.
Mở đúng 1 cửa sổ trình duyệt Chrome/Edge duy nhất với session_dir chỉ định.
Theo dõi chính xác tiến trình Chrome thông qua commandline session_dir.

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


def kill_orphan_process(session_dir_str: str):
    """Kill bất kỳ tiến trình chrome/edge ngầm nào đang giữ session_dir"""
    norm_dir = session_dir_str.lower().replace("/", "\\")
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | Where-Object {{ $_.CommandLine -like '*{norm_dir}*' }} | Stop-Process -Force"
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, creationflags=flags)
    except Exception as e:
        print(f"[LoginBrowser] Warning cleanup orphan: {e}", flush=True)


def is_browser_running(session_dir_str: str) -> bool:
    """Kiểm tra chính xác xem còn tiến trình Chrome/Edge nào đang giữ session_dir này hay không."""
    norm_dir = session_dir_str.lower().replace("/", "\\")
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | Where-Object {{ $_.CommandLine -like '*{norm_dir}*' }} | Measure-Object | Select-Object -ExpandProperty Count"
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags)
        count_str = res.stdout.strip()
        if count_str.isdigit() and int(count_str) > 0:
            return True
    except Exception:
        pass
    return False


def bring_to_front_once(target_pid: int):
    """Gọi nhẹ 1 lần duy nhất để đưa cửa sổ Chrome mới mở lên trên cùng màn hình."""
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

        def callback(hwnd, extra):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
    except Exception:
        pass


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

    # 4. Mở trình duyệt Chrome/Edge trực tiếp
    cmd_args = [
        browser_exe,
        f'--user-data-dir={session_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-blink-features=AutomationControlled',
        '--start-maximized',
        login_url
    ]

    print(f"[LoginBrowser] Khởi chạy trình duyệt: {' '.join(cmd_args[:3])} ...", flush=True)
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = subprocess.Popen(cmd_args, creationflags=creation_flags)
    print(f"[LoginBrowser] Tiến trình khởi tạo PID = {proc.pid}", flush=True)

    # Đợi 3 giây cho Chrome khởi tạo đầy đủ các tiến trình con
    time.sleep(3.0)
    bring_to_front_once(proc.pid)

    # 5. Theo dõi cho đến khi người dùng đóng tất cả cửa sổ trình duyệt của session này
    print("[LoginBrowser] Đang theo dõi cửa sổ trình duyệt... Vui lòng đăng nhập và đóng trình duyệt khi hoàn tất.", flush=True)
    max_wait = 600
    elapsed = 3.0
    while elapsed < max_wait:
        time.sleep(2)
        elapsed += 2
        if not is_browser_running(session_dir):
            print("[LoginBrowser] Đã phát hiện người dùng đóng trình duyệt.", flush=True)
            break

    print("[LoginBrowser] Hoàn tất. Phiên đăng nhập đã được lưu!", flush=True)


if __name__ == "__main__":
    main()
