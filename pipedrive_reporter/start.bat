@echo off
cd /d "%~dp0"
echo Starting Pipedrive Reporter on http://localhost:8002
start http://localhost:8002
uvicorn api.main:app --host 0.0.0.0 --port 8002 --reload
