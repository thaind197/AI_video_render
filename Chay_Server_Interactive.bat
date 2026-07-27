@echo off
title Video Render & Social Auto Post Server
cd /d "%~dp0"
echo [Info] Dang khoi chay Server de hien thi trinh duyet...

:: Thu chay voi python mac dinh
python server.py
if %ERRORLEVEL% NEQ 0 (
    echo [Warning] Khong tim thay lenh python mac dinh, dang thu voi cac duong dan khac...
    "C:\Users\Duy Thai\AppData\Local\Python\bin\python.exe" server.py
)
if %ERRORLEVEL% NEQ 0 (
    "C:\Users\Duy Thai\AppData\Local\Python\pythoncore-3.14-64\python.exe" server.py
)

pause
