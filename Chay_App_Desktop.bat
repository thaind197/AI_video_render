@echo off
chcp 65001 >nul
title Veo Studio AI PRO - Desktop Launcher
echo ===================================================
echo 🚀 Đang khởi chạy Veo Studio AI Desktop Application...
echo ===================================================
echo.

python desktop_app.py
if errorlevel 1 (
    echo.
    echo ⚠️ Có lỗi khi khởi chạy! Đang kiểm tra dependencies...
    pip install -r requirements.txt
    python desktop_app.py
)
pause
