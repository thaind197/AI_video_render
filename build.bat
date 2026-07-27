@echo off
echo ============================================
echo   Veo Studio AI PRO - Build Server
echo ============================================
echo.

:: Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
    echo.
)

echo [BUILD] Building VeoStudioServer.exe ...
echo.
pyinstaller build.spec --clean --noconfirm

echo.
if exist "dist\VeoStudioServer\VeoStudioServer.exe" (
    echo ============================================
    echo   BUILD SUCCESS!
    echo ============================================
    echo.
    echo Output:  dist\VeoStudioServer\
    echo EXE:     dist\VeoStudioServer\VeoStudioServer.exe
    echo.
    echo To deploy on another server:
    echo   1. Copy the entire "dist\VeoStudioServer\" folder
    echo   2. Create a .env file with your GEMINI_API_KEY
    echo   3. Run VeoStudioServer.exe
    echo   4. Open http://localhost:8000
    echo.

    :: Create run script in dist
    echo @echo off > "dist\VeoStudioServer\start_server.bat"
    echo echo Starting Veo Studio AI PRO Server... >> "dist\VeoStudioServer\start_server.bat"
    echo VeoStudioServer.exe >> "dist\VeoStudioServer\start_server.bat"
    echo pause >> "dist\VeoStudioServer\start_server.bat"

    :: Copy .env.example
    if exist ".env.example" copy ".env.example" "dist\VeoStudioServer\.env.example" >nul
    
    :: Ensure storage directories exist
    mkdir "dist\VeoStudioServer\storage\downloads" 2>nul
    mkdir "dist\VeoStudioServer\storage\generated" 2>nul
    mkdir "dist\VeoStudioServer\storage\final" 2>nul
    mkdir "dist\VeoStudioServer\storage\browser_sessions\facebook" 2>nul
    mkdir "dist\VeoStudioServer\storage\browser_sessions\tiktok" 2>nul
    mkdir "dist\VeoStudioServer\storage\browser_sessions\x" 2>nul

) else (
    echo ============================================
    echo   BUILD FAILED!
    echo ============================================
    echo Check the error messages above.
)

echo.
pause
