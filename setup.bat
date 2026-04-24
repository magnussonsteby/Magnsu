@echo off
echo ================================
echo  Magnsu - First Time Setup
echo ================================
echo.

echo Installing requirements...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip failed. Make sure Python is installed and "Add to PATH" was checked.
    pause
    exit /b 1
)

echo.
echo Setting up database...
python -m alembic upgrade head
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Database setup failed.
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
