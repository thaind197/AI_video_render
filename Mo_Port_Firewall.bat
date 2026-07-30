@echo off
chcp 65001 >nul
title Veo Studio AI PRO - Open Ports 5432 & 8080 in Windows Firewall

echo ====================================================================
echo 🔓 Đang cấu hình Mở Port Windows Firewall cho PostgreSQL (5432) & WebAdmin (8080)...
echo ====================================================================
echo.

powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"New-NetFirewallRule -DisplayName ''VeoStudio_PostgreSQL_5432'' -Direction Inbound -LocalPort 5432 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue; New-NetFirewallRule -DisplayName ''VeoStudio_WebAdmin_8080'' -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue; Write-Host ''[OK] Da mo thanh cong Port 5432 va Port 8080 trong Windows Firewall!'' -ForegroundColor Green; Start-Sleep -Seconds 3\"'"

echo.
echo ✅ Đã gửi lệnh mở port đến Windows Firewall. Vui lòng chọn Yes khi UAC hỏi quyền Admin.
echo.
pause
