from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from api.runner import (
    CONFIG_PATH, load_config, save_config,
    run_report, manual_login, manual_capture, close_browser,
    browser_is_open, get_playbook,
)
from api.xledger_api import XledgerClient, build_html_table
from api.pipedrive_api import PipedriveClient, build_html_table as build_pd_html_table

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


# ---------------------------------------------------------------------------
# Xledger GraphQL API endpoints
# ---------------------------------------------------------------------------

def _get_api_client() -> XledgerClient:
    cfg = load_config() if CONFIG_PATH.exists() else {}
    token = cfg.get("api_token", "").strip()
    if not token:
        raise HTTPException(400, "No API token configured — add it in Settings")
    url = cfg.get("graphql_url", "https://www.xledger.net/graphql").strip()
    return XledgerClient(token=token, url=url)


@app.get("/api/api-test")
async def api_test():
    """Test the GraphQL connection and discover time-related query types."""
    client = _get_api_client()
    try:
        await client.ping()
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")

    time_fields = await client.discover_time_queries()
    return {
        "connected": True,
        "time_fields": [
            {"name": f["name"], "description": f.get("description") or ""}
            for f in time_fields
        ],
    }


@app.get("/api/api-fetch")
async def api_fetch(from_date: str = None, to_date: str = None):
    """
    Fetch timesheet data via GraphQL, email it, and return a summary.
    Probes candidate query names to find the right one automatically.
    """
    client = _get_api_client()
    cfg = load_config()

    # Use stored query name or probe for it
    query_name = cfg.get("timesheet_query_name", "").strip()
    if not query_name:
        query_name = await client.probe_timesheet_query()
        if not query_name:
            raise HTTPException(
                404,
                "Could not find a timesheet query in the Xledger schema. "
                "Use /api/api-test to see available time-related queries, "
                "then set timesheet_query_name in config.json."
            )
        cfg["timesheet_query_name"] = query_name
        save_config(cfg)

    rows = await client.fetch_all_timesheets(query_name, from_date, to_date)
    html_table = build_html_table(rows)

    recipients = cfg.get("recipient_emails", [])
    subject = cfg.get("email_subject", "Xledger Time Report")
    period = f"{from_date or 'all'} to {to_date or 'today'}"

    html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">
  Xledger time report — {period}
</p>
{html_table}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Xledger Reporter (API mode)
</p>
</body></html>"""

    if recipients:
        from api.runner import _send_outlook
        _send_outlook(subject, recipients, html_body)

    return {
        "rows": len(rows),
        "query_used": query_name,
        "period": period,
        "emailed_to": recipients,
    }


# ---------------------------------------------------------------------------
# Pipedrive REST API v2 endpoints
# ---------------------------------------------------------------------------

def _get_pipedrive_client() -> PipedriveClient:
    cfg = load_config() if CONFIG_PATH.exists() else {}
    token = cfg.get("pipedrive_token", "").strip()
    if not token:
        raise HTTPException(400, "No Pipedrive token configured — add it in Settings")
    domain = cfg.get("pipedrive_domain", "akselera").strip() or "akselera"
    return PipedriveClient(token=token, company_domain=domain)


@app.get("/api/pipedrive-test")
async def pipedrive_test():
    """Test the Pipedrive API connection and return current user info."""
    client = _get_pipedrive_client()
    try:
        user = await client.ping()
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")
    return {
        "connected": True,
        "user": user.get("name", ""),
        "email": user.get("email", ""),
        "company": user.get("company_name", ""),
    }


@app.get("/api/pipedrive-fetch")
async def pipedrive_fetch(
    status: str = "open",
    from_date: str = None,
    to_date: str = None,
):
    """Fetch deals from Pipedrive, email them, and return a summary."""
    client = _get_pipedrive_client()
    cfg = load_config()

    deals = await client.fetch_all_deals(
        status=status, from_date=from_date, to_date=to_date
    )
    html_table = build_pd_html_table(deals)

    recipients = cfg.get("recipient_emails", [])
    subject = cfg.get("email_subject", "Pipedrive Deals Report")
    period = f"{from_date or 'all'} to {to_date or 'today'}"

    html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">
  Pipedrive deals ({status}) — {period}
</p>
{html_table}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Reporter
</p>
</body></html>"""

    if recipients:
        from api.runner import _send_outlook
        _send_outlook(subject, recipients, html_body)

    return {
        "rows": len(deals),
        "status_filter": status,
        "period": period,
        "emailed_to": recipients,
    }
