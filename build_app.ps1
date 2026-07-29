# =========================================================================
# Veo Studio AI PRO - Windows Desktop Application & Installer Build Script
# =========================================================================

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "  VEO STUDIO AI PRO - POWERSHELL AUTOMATED BUILD SCRIPT  " -ForegroundColor Yellow
Write-Host "=========================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# 1. Tắt ứng dụng cũ nếu đang chạy ngầm
Write-Host "`n[1/5] Kiem tra va tat tien trinh cu (neu co)..." -ForegroundColor Green
Get-Process -Name "VeoStudioAI" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 2. Kiểm tra môi trường Python
Write-Host "`n[2/5] Kiem tra moi truong Python..." -ForegroundColor Green

$PythonExe = $null
$candidates = @(
    "$env:LocalAppData\Python\bin\python.exe",
    "python",
    "py"
)

foreach ($cmd in $candidates) {
    try {
        $ver = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -like "*Python*") {
            $PythonExe = $cmd
            $pythonVersion = $ver
            break
        }
    }
    catch {}
}

if (-not $PythonExe) {
    Write-Host "  [LOI] Khong tim thay Python! Vui long cai dat Python 3.10 tro len." -ForegroundColor Red
    Exit 1
}

Write-Host "  -> Python Exe    : $PythonExe" -ForegroundColor Gray
Write-Host "  -> Python Version: $pythonVersion" -ForegroundColor Gray

# 3. Xóa các thư mục tạm cũ
Write-Host "`n[3/5] Don dep bo nho tam build cu..." -ForegroundColor Green
if (Test-Path "$ScriptDir\build") {
    Remove-Item -Path "$ScriptDir\build" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  -> Da xoa thu muc build/" -ForegroundColor Gray
}

# 4. Thực thi script build PyInstaller
Write-Host "`n[4/5] Dang tien hanh dong goi PyInstaller (Standalone Folder)..." -ForegroundColor Green
& $PythonExe "$ScriptDir\build_desktop_exe.py"

$exePath = "$ScriptDir\dist\VeoStudioAI\VeoStudioAI.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "`n[LOI] Khong tim thay file .exe sau khi build PyInstaller." -ForegroundColor Red
    Exit 1
}

# 5. Đóng gói thành File Cài Đặt (Windows Setup Installer .exe)
Write-Host "`n[5/5] Dang tien hanh tao File Cai Dat Windows Setup (.exe Installer)..." -ForegroundColor Green

$IsccPaths = @(
    "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$IsccExe = $null
foreach ($path in $IsccPaths) {
    if (Test-Path $path) {
        $IsccExe = $path
        break
    }
}

if (-not $IsccExe) {
    try {
        $whereIscc = where.exe iscc 2>$null
        if ($whereIscc) { $IsccExe = $whereIscc }
    }
    catch {}
}

if ($IsccExe -and (Test-Path "$ScriptDir\installer.iss")) {
    Write-Host "  -> Tim thay Inno Setup Compiler tại: $IsccExe" -ForegroundColor Gray
    Write-Host "  -> Dang bien dich installer.iss..." -ForegroundColor Gray
    & $IsccExe "$ScriptDir\installer.iss"
}
else {
    Write-Host "  [CANH BAO] Khong tim thay Inno Setup Compiler (ISCC.exe). Se giu nguyen thu muc portable dist\VeoStudioAI" -ForegroundColor Yellow
}

$installerPath = "$ScriptDir\dist\VeoStudioAI_Setup_v2.5.0.exe"

Write-Host "`n=========================================================" -ForegroundColor Green
Write-Host "  [THANH CONG] BANG CAI DA DUOC DONG GOI HOAN CHINH!     " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "Thu muc ung dung (Portable) : $ScriptDir\dist\VeoStudioAI" -ForegroundColor White
Write-Host "File thuc thi portable       : $exePath" -ForegroundColor Yellow

if (Test-Path $installerPath) {
    Write-Host "FILE CAI DAT WINDOWS (.EXE)  : $installerPath" -ForegroundColor Cyan
    Write-Host "  (Ban co the bam double-click vao file nay de cai dat thang len Windows)" -ForegroundColor Gray
}
Write-Host "=========================================================`n" -ForegroundColor Green
$versionLine = Select-String -Path "$ScriptDir\version.py" -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
$appVersion = "unknown"
if ($versionLine) {
    $appVersion = $versionLine.Matches[0].Groups[1].Value
}

$installerPath = "$ScriptDir\dist\VeoStudioAI_Setup_v$appVersion.exe"

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "   BUILD THANH CONG!                                      " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Version    : v$appVersion" -ForegroundColor Cyan
Write-Host "  Portable   : $ScriptDir\dist\VeoStudioAI\" -ForegroundColor White

if (Test-Path $installerPath) {
    $size = [math]::Round((Get-Item $installerPath).Length / 1MB, 1)
    Write-Host "  Installer  : $installerPath ($size MB)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  -> Double-click file Installer .exe de cai dat len Windows!" -ForegroundColor Cyan
} else {
    Write-Host "  [WARN] Khong tim thay file installer output." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host ""
