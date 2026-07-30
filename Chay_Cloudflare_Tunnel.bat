@echo off
chcp 65001 >nul
title Veo Studio AI PRO - Cloudflare Tunnel Launcher

echo ====================================================================
echo 🚀 Đang khởi tạo Cloudflare Tunnel cho Web Admin & App Remote...
echo ====================================================================
echo.
echo Đang gửi yêu cầu tạo HTTPS Public Tunnel tới Cloudflare...
echo.

cloudflared tunnel --url http://localhost:8080
