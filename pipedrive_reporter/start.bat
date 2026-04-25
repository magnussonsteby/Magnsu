@echo off
cd /d "%~dp0"
echo ============================================
echo  Pipedrive Reporter
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)

:: Check uvicorn is installed
uvicorn --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: uvicorn not found. Run setup.bat first.
    pause
    exit /b 1
)

echo Starting server on http://localhost:8002
echo Press Ctrl+C to stop.
echo.

:: Open browser after 5 seconds
start /min cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8002"

uvicorn api.main:app --host 0.0.0.0 --port 8002 --reload

echo.
echo Server stopped.
pause
