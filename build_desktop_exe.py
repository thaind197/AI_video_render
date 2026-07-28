"""
Build Script: Đóng gói Veo Studio AI PRO thành ứng dụng Desktop Windows (.exe)
"""
import sys
import subprocess
import os
from pathlib import Path

# Đảm bảo UTF-8 Encoding cho Windows Terminal
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from version import __version__, FULL_NAME

BASE_DIR = Path(__file__).resolve().parent

def run_build():
    print("=========================================================")
    print(f"[BUILD] BAT DAU DONG GOI {FULL_NAME} DESKTOP EXECUTABLE")
    print("=========================================================")


    # 1. Cài đặt pyinstaller nếu chưa có
    try:
        import PyInstaller
    except ImportError:
        print("[Build] Đang cài đặt pyinstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # 2. Xây dựng lệnh PyInstaller
    # LƯU Ý: Không dùng pywebview/pythonnet/clr_loader (gây crash .NET CLR trên Win 11)
    # Sử dụng Microsoft Edge App Mode làm engine GUI - ổn định 100% mọi máy Windows.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=VeoStudioAI",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",           # Không tạo console window - triệt để không có console nào
        f"--add-data={BASE_DIR / 'ui'};ui",
        f"--add-data={BASE_DIR / 'config'};config",
        f"--add-data={BASE_DIR / 'publishers'};publishers",
        f"--add-data={BASE_DIR / 'core'};core",
        f"--add-data={BASE_DIR / 'version.py'};.",
        # Loại bỏ hoàn toàn .NET CLR dependencies (gây crash trên Win 11)
        "--exclude-module=pythonnet",
        "--exclude-module=clr",
        "--exclude-module=clr_loader",
        "--exclude-module=webview",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=fastapi",
        str(BASE_DIR / "desktop_app.py")
    ]


    print(f"[Build] Thực thi lệnh PyInstaller: {' '.join(cmd[:5])}...")
    res = subprocess.run(cmd)

    if res.returncode == 0:
        dist_dir = BASE_DIR / "dist" / "VeoStudioAI"
        print("\n=========================================================")
        print(f"[SUCCESS] DONG GOI THANH CONG {FULL_NAME}!")
        print(f"Thu muc ung dung hoan chinh: {dist_dir}")
        print(f"File khoi chay: {dist_dir / 'VeoStudioAI.exe'}")
        print("=========================================================\n")
    else:
        print("\n[ERROR] Dong goi that bai, vui long kiem tra thong bao loi tren.")



if __name__ == "__main__":
    run_build()
