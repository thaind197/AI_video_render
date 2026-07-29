"""
Build Script: Đóng gói Veo Studio AI PRO thành ứng dụng Desktop Windows (.exe)
Tự động tăng patch version (vd: 2.5.0 → 2.5.1) mỗi lần build.
"""
import sys
import subprocess
import os
import re
from pathlib import Path

# Đảm bảo UTF-8 Encoding cho Windows Terminal
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent


def auto_bump_version() -> str:
    """Tự động tăng patch version trong version.py mỗi lần build.
    Ví dụ: 2.5.0 → 2.5.1 → 2.5.2 → ...
    """
    version_file = BASE_DIR / "version.py"
    content = version_file.read_text(encoding="utf-8")

    match = re.search(r'__version__\s*=\s*["\']([\d.]+)["\']', content)
    if not match:
        print("[Build] WARN: Khong tim thay __version__ trong version.py")
        return "0.0.0"

    old_version = match.group(1)
    parts = old_version.split(".")

    # Tăng patch (số cuối) lên 1
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = ".".join(parts)

    # Ghi lại version.py
    new_content = content.replace(f'__version__ = "{old_version}"', f'__version__ = "{new_version}"')
    version_file.write_text(new_content, encoding="utf-8")

    print(f"[Build] Version bumped: {old_version} -> {new_version}")
    return new_version

def run_build():
    # Auto-increment patch version
    new_version = auto_bump_version()

    # Reload version module sau khi bump
    import importlib
    import version as ver_mod
    importlib.reload(ver_mod)
    from version import __version__, FULL_NAME

    print("=========================================================")
    print(f"[BUILD] BAT DAU DONG GOI {FULL_NAME} DESKTOP EXECUTABLE")
    print("=========================================================")


    # 1. Cài đặt pyinstaller nếu chưa có
    try:
        import PyInstaller
    except ImportError:
        print("[Build] Đang cài đặt pyinstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # 2. Tạo Windows Version Info file để embed version vào EXE
    ver_parts = __version__.split(".")
    v_major = int(ver_parts[0]) if len(ver_parts) > 0 else 0
    v_minor = int(ver_parts[1]) if len(ver_parts) > 1 else 0
    v_patch = int(ver_parts[2]) if len(ver_parts) > 2 else 0

    version_info_content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v_major}, {v_minor}, {v_patch}, 0),
    prodvers=({v_major}, {v_minor}, {v_patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Veo Studio AI'),
        StringStruct('FileDescription', 'Veo Studio AI PRO'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', 'VeoStudioAI'),
        StringStruct('OriginalFilename', 'VeoStudioAI.exe'),
        StringStruct('ProductName', 'Veo Studio AI PRO'),
        StringStruct('ProductVersion', '{__version__}'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    version_info_path = BASE_DIR / "win_version_info.txt"
    version_info_path.write_text(version_info_content, encoding="utf-8")
    print(f"[Build] Version info file: {version_info_path}")

    # 3. Xây dựng lệnh PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=VeoStudioAI",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        f"--version-file={version_info_path}",
        f"--add-data={BASE_DIR / 'ui'};ui",
        f"--add-data={BASE_DIR / 'config'};config",
        f"--add-data={BASE_DIR / 'publishers'};publishers",
        f"--add-data={BASE_DIR / 'core'};core",
        f"--add-data={BASE_DIR / 'version.py'};.",
        f"--add-data={BASE_DIR / 'remote_config.py'};.",
        # Loại bỏ .NET CLR dependencies
        "--exclude-module=pythonnet",
        "--exclude-module=clr",
        "--exclude-module=clr_loader",
        "--exclude-module=webview",
        # Uvicorn/FastAPI
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
        # Firebase/Google Auth
        "--hidden-import=google.auth",
        "--hidden-import=google.auth.transport.requests",
        "--hidden-import=google.oauth2.service_account",
        "--hidden-import=firebase_admin",
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
