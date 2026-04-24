from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from api.runner import (
    CONFIG_PATH, load_config, save_config,
    run_report, manual_login, manual_capture, close_browser,
    browser_is_open, get_playbook,
)

app = FastAPI(title="Xledger Reporter", version="2.0.0")
STATIC = Path(__file__).parent.parent / "static"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_ui():
    with open(STATIC / "index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/status")
def status():
    return {
        "config_exists": CONFIG_PATH.exists(),
        "browser_open": browser_is_open(),
        "has_playbook": len(get_playbook()) > 0,
    }


@app.get("/api/config")
def get_config():
    if not CONFIG_PATH.exists():
        return {}
    cfg = load_config()
    cfg.pop("xledger_password", None)
    return cfg


@app.post("/api/config")
def set_config(payload: dict):
    existing = load_config() if CONFIG_PATH.exists() else {}
    if not payload.get("xledger_password"):
        payload["xledger_password"] = existing.get("xledger_password", "")
    # Preserve playbook if not in payload
    if "playbook" not in payload:
        payload["playbook"] = existing.get("playbook", [])
    save_config(payload)
    return {"ok": True}


@app.post("/api/clear-playbook")
def clear_playbook():
    if CONFIG_PATH.exists():
        cfg = load_config()
        cfg.pop("playbook", None)
        save_config(cfg)
    return {"ok": True}


@app.get("/api/run")
async def run():
    async def stream():
        async for chunk in run_report():
            yield chunk
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/login")
async def login():
    async def stream():
        async for chunk in manual_login():
            yield chunk
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/capture")
async def capture():
    async def stream():
        async for chunk in manual_capture():
            yield chunk
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/close")
async def close():
    await close_browser()
    return {"ok": True}
