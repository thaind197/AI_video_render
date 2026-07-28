# =========================================================================
# Veo Studio AI PRO - Windows Desktop Application Build Script (PowerShell)
# =========================================================================

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "  VEO STUDIO AI PRO - POWERSHELL AUTOMATED BUILD SCRIPT  " -ForegroundColor Yellow
Write-Host "=========================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# 1. Tắt ứng dụng cũ nếu đang chạy ngầm
Write-Host "`n[1/4] Kiem tra va tat tiến trinh cu (neu co)..." -ForegroundColor Green
Get-Process -Name "VeoStudioAI" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 2. Kiểm tra môi trường Python
Write-Host "`n[2/4] Kiem tra moi truong Python..." -ForegroundColor Green
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "  -> Python Version: $pythonVersion" -ForegroundColor Gray
} catch {
    Write-Host "  [LOI] Khong tim thay Python! Vui long cai dat Python 3.10 tro len." -ForegroundColor Red
    Exit 1
}

# 3. Xóa các thư mục tạm cũ
Write-Host "`n[3/4] Don dep bo nho tam build cu..." -ForegroundColor Green
if (Test-Path "$ScriptDir\build") {
    Remove-Item -Path "$ScriptDir\build" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  -> Da xoa thu muc build/" -ForegroundColor Gray
}

# 4. Thực thi script build PyInstaller
Write-Host "`n[4/4] Dang tien hanh dong goi PyInstaller..." -ForegroundColor Green
& python "$ScriptDir\build_desktop_exe.py"

$exePath = "$ScriptDir\dist\VeoStudioAI\VeoStudioAI.exe"
if (Test-Path $exePath) {
    Write-Host "`n=========================================================" -ForegroundColor Green
    Write-Host "  [THANH CONG] BAN CAI DA DUOC DONG GOI HOAN CHINH!      " -ForegroundColor Green
    Write-Host "=========================================================" -ForegroundColor Green
    Write-Host "Thu muc ung dung : $ScriptDir\dist\VeoStudioAI" -ForegroundColor White
    Write-Host "File thuc thi    : $exePath" -ForegroundColor Yellow
    Write-Host "=========================================================`n" -ForegroundColor Green
} else {
    Write-Host "`n[LOI] Khong tim thay file .exe sau khi build." -ForegroundColor Red
}
