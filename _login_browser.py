"""
Helper: Mo Chrome de user dang nhap Facebook.
Tao file .bat tam thoi va dung explorer.exe de mo — dam bao Chrome
chay tren INTERACTIVE DESKTOP cua user (khong bi anh huong boi
desktop station cua parent process).

Usage:
    python _login_browser.py <session_dir> <login_url>
"""
import sys
import os
import subprocess
import time
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def find_chrome():
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


def main():
    if len(sys.argv) < 3:
        print("Usage: python _login_browser.py <session_dir> <login_url>")
        sys.exit(1)

    session_dir = sys.argv[1]
    login_url = sys.argv[2]

    print(f"[LoginBrowser] session_dir = {session_dir}", flush=True)
    print(f"[LoginBrowser] login_url   = {login_url}", flush=True)

    # Xoa lock files
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = Path(session_dir) / lock_file
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    chrome_exe = find_chrome()
    if not chrome_exe:
        print("[LoginBrowser] ERROR: Chrome/Edge not found!", flush=True)
        sys.exit(1)

    print(f"[LoginBrowser] Chrome: {chrome_exe}", flush=True)

    # === CACH 1: Dung WMI Win32_Process.Create ===
    # WMI luon tao process tren interactive desktop
    try:
        import wmi
        has_wmi = True
    except ImportError:
        has_wmi = False

    chrome_args = f'--user-data-dir="{session_dir}" --profile-directory=Default --no-first-run --no-default-browser-check --disable-sync --start-maximized "{login_url}"'

    chrome_pid = None

    if has_wmi:
        print("[LoginBrowser] Using WMI Win32_Process.Create...", flush=True)
        try:
            c = wmi.WMI()
            process_startup = c.Win32_ProcessStartup.new()
            process_startup.ShowWindow = 1  # SW_SHOWNORMAL
            pid, result = c.Win32_Process.Create(
                CommandLine=f'"{chrome_exe}" {chrome_args}',
                ProcessStartupInformation=process_startup
            )
            if result == 0:
                chrome_pid = pid
                print(f"[LoginBrowser] WMI launched Chrome PID={pid}", flush=True)
            else:
                print(f"[LoginBrowser] WMI failed result={result}", flush=True)
        except Exception as e:
            print(f"[LoginBrowser] WMI error: {e}", flush=True)

    # === CACH 2: Tao .bat file va dung explorer.exe mo ===
    if not chrome_pid:
        print("[LoginBrowser] Using explorer.exe + .bat file...", flush=True)

        # Tao bat file tam thoi
        bat_dir = Path(session_dir)
        bat_dir.mkdir(parents=True, exist_ok=True)
        bat_path = bat_dir / "_open_login.bat"

        bat_content = f'@echo off\nstart "" "{chrome_exe}" {chrome_args}\n'
        bat_path.write_text(bat_content, encoding='utf-8')

        print(f"[LoginBrowser] Created: {bat_path}", flush=True)

        # Dung explorer.exe de chay bat file — luon tren interactive desktop
        subprocess.Popen(
            ["explorer.exe", str(bat_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("[LoginBrowser] explorer.exe launched .bat file", flush=True)

        # Cho Chrome khoi dong
        time.sleep(5)

        # Tim Chrome PID
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowTitle -ne '' }} | Select-Object -First 1 -ExpandProperty Id"],
                capture_output=True, text=True, timeout=5
            )
            chrome_pid = result.stdout.strip() or None
            print(f"[LoginBrowser] Found Chrome PID={chrome_pid}", flush=True)
        except Exception:
            pass

    if not chrome_pid:
        print("[LoginBrowser] WARNING: Could not find Chrome PID, but browser may still be open", flush=True)
        # Just wait a fixed time
        print("[LoginBrowser] Waiting 5 minutes for user to login...", flush=True)
        time.sleep(300)
    else:
        # Poll cho den khi Chrome ket thuc
        max_wait = 600
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(3)
            elapsed += 3
            try:
                check = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Get-Process -Id {chrome_pid} -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
                    capture_output=True, text=True, timeout=5
                )
                if check.stdout.strip() == "0":
                    print("[LoginBrowser] Chrome da dong.", flush=True)
                    break
            except Exception:
                break

    print("[LoginBrowser] Done. Session da luu.", flush=True)


if __name__ == "__main__":
    main()
