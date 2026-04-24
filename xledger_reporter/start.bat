@echo off
echo ================================
echo  Xledger Reporter - Starting
echo ================================
echo.
echo Your address:
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do (
    set ip=%%a
    setlocal enabledelayedexpansion
    set ip=!ip: =!
    echo   http://!ip!:8001
    endlocal
)
echo.
echo Open the address above in your browser.
echo Keep this window open while using the app.
echo Press Ctrl+C to stop.
echo.
cd /d "%~dp0"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
