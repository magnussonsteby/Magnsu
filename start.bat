@echo off
echo ================================
echo  Magnsu - Starting App
echo ================================
echo.
echo Your iPhone address:
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do (
    set ip=%%a
    setlocal enabledelayedexpansion
    set ip=!ip: =!
    echo   http://!ip!:8000
    endlocal
)
echo.
echo Open the address above in your iPhone browser.
echo Keep this window open while using the app.
echo Press Ctrl+C to stop.
echo.
uvicorn api.main:app --host 0.0.0.0 --port 8000
