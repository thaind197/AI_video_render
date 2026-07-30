@echo off
title Veo Studio AI PRO - Cloudflare Tunnel URL Checker

echo ====================================================================
echo Dang kiem tra URL Public Cloudflare Tunnel...
echo ====================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0get_tunnel.ps1"

echo.
pause
