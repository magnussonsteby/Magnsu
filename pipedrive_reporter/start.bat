@echo off
cd /d "%~dp0"
echo Starting Pipedrive Reporter on http://localhost:8002
echo.

:: Open browser after 4 seconds (gives uvicorn time to start)
start /min cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8002"

uvicorn api.main:app --host 0.0.0.0 --port 8002 --reload
