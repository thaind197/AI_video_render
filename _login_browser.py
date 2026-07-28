"""
Helper: Mở Chrome / Edge cho người dùng đăng nhập thủ công.
Không sử dụng PowerShell subprocess → không flash console window.

Usage:
    python _login_browser.py <session_dir> <login_url>
"""
import sys
import os
import time
import subprocess
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Cờ ẩn console cho mọi child process trên Windows
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def launch_login_browser(session_dir_input: str, login_url: str):
    session_dir = str(Path(session_dir_input).resolve())

    print(f"[LoginBrowser] session_dir = {session_dir}", flush=True)
    print(f"[LoginBrowser] login_url   = {login_url}", flush=True)

    # 1. Clean lock files (không dùng PowerShell)
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        lock_path = Path(session_dir) / lock_file
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    # 2. Find Browser EXE
    browser_exe = find_browser()
    if not browser_exe:
        print("[LoginBrowser] ERROR: Chrome/Edge not found!", flush=True)
        return False

    print(f"[LoginBrowser] Browser: {browser_exe}", flush=True)

    # 3. Mở trình duyệt - KHÔNG dùng CREATE_NO_WINDOW cho GUI app (Chrome/Edge)
    cmd_args = [
        browser_exe,
        f'--user-data-dir={session_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-blink-features=AutomationControlled',
        '--start-maximized',
        login_url
    ]

    # Dùng DETACHED_PROCESS để Chrome chạy hoàn toàn độc lập, không kế thừa console
    detached_flags = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS

    proc = subprocess.Popen(
        cmd_args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=detached_flags,
    )
    print(f"[LoginBrowser] Chrome PID = {proc.pid}", flush=True)

    # 4. Theo dõi bằng proc.poll() - KHÔNG dùng PowerShell
    # Chrome với --user-data-dir riêng sẽ giữ main process sống cho đến khi đóng hết cửa sổ
    print("[LoginBrowser] Waiting for user to close browser...", flush=True)
    max_wait = 600  # 10 phút
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(2)
        elapsed += 2
        ret = proc.poll()
        if ret is not None:
            print(f"[LoginBrowser] Chrome exited (code={ret})", flush=True)
            break

    print("[LoginBrowser] Done. Session saved!", flush=True)
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: python _login_browser.py <session_dir> <login_url>")
        sys.exit(1)

    launch_login_browser(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
