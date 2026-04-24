@echo off
echo ================================
echo  Xledger Reporter - First Time Setup
echo ================================
echo.

echo Installing Python requirements...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip failed. Make sure Python is installed.
    pause
    exit /b 1
)

echo.
echo Installing Playwright browser (Chromium)...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Playwright browser install failed.
    pause
    exit /b 1
)

echo.
echo ================================
echo  Setup complete!
echo ================================
echo.
echo Run start.bat to launch the app.
echo.
pause
