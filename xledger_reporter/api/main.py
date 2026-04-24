import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from api.runner import CONFIG_PATH, load_config, run_report, save_config

app = FastAPI(title="Xledger Reporter", version="1.0.0")

STATIC = Path(__file__).parent.parent / "static"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_ui():
    with open(STATIC / "index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/config-exists")
def config_exists():
    return {"exists": CONFIG_PATH.exists()}


@app.get("/api/config")
def get_config():
    if not CONFIG_PATH.exists():
        return {}
    cfg = load_config()
    cfg.pop("xledger_password", None)  # Never return password to UI
    return cfg


@app.post("/api/config")
def set_config(payload: dict):
    existing = load_config() if CONFIG_PATH.exists() else {}
    # Keep existing password if not provided
    if not payload.get("xledger_password"):
        payload["xledger_password"] = existing.get("xledger_password", "")
    save_config(payload)
    return {"ok": True}


@app.get("/api/run")
async def run(request=None):
    async def event_stream():
        async for chunk in run_report():
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")
