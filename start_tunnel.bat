@echo off
title Cloudflare Tunnel - Public URL
echo ===================================================
echo   Dang khoi chay Cloudflare Tunnel cho Port 8000
echo ===================================================
echo.
cloudflared tunnel --url http://localhost:8000
pause
