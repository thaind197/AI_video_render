@echo off
chcp 65001 >nul
title Veo Studio AI PRO - Docker WebAdmin Launcher
echo ===================================================
echo 🚀 Đang Build & Khởi chạy Docker WebAdmin & Postgres Database...
echo ===================================================
echo.

docker-compose -f docker-compose.admin.yml up --build -d

if errorlevel 1 (
    echo.
    echo ❌ Lỗi khi khởi chạy Docker Compose! Đảm bảo Docker Desktop đang bật.
) else (
    echo.
    echo ✅ Đã khởi chạy thành công các container Docker:
    echo    - Postgres Database: localhost:5432
    echo    - Web Admin Panel:   http://localhost:8080/admin
    echo.
)
pause
