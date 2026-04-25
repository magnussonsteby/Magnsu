@echo off
cd /d "%~dp0"
echo Installing Pipedrive Reporter dependencies...
python -m pip install -r requirements.txt
echo.
echo Setup complete. Run start.bat to launch the app.
pause
