import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from api.pipedrive_api import PipedriveClient, build_html_table

app = FastAPI(title="Pipedrive Reporter", version="1.0.0")
STATIC = Path(__file__).parent.parent / "static"
CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_ui():
    with open(STATIC / "index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/config")
def get_config():
    if not CONFIG_PATH.exists():
        return {}
    return load_config()


@app.post("/api/config")
def set_config(payload: dict):
    existing = load_config() if CONFIG_PATH.exists() else {}
    existing.update(payload)
    save_config(existing)
    return {"ok": True}


def _client() -> PipedriveClient:
    cfg = load_config() if CONFIG_PATH.exists() else {}
    token = cfg.get("pipedrive_token", "").strip()
    if not token:
        raise HTTPException(400, "No API token configured — add it in Settings")
    domain = (cfg.get("pipedrive_domain") or "akselera").strip()
    return PipedriveClient(token=token, company_domain=domain)


@app.get("/api/test")
async def api_test():
    """Verify the API token and return the current user's name and company."""
    client = _client()
    try:
        user = await client.ping()
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")
    return {
        "connected": True,
        "user":    user.get("name", ""),
        "email":   user.get("email", ""),
        "company": user.get("company_name", ""),
    }


@app.get("/api/fetch")
async def api_fetch(
    status: str = "open",
    from_date: str = None,
    to_date: str = None,
):
    """Fetch deals and optionally email them via Outlook."""
    client = _client()
    cfg = load_config() if CONFIG_PATH.exists() else {}

    deals = await client.fetch_all_deals(
        status=status, from_date=from_date, to_date=to_date
    )
    html_table = build_html_table(deals)

    recipients = cfg.get("recipient_emails", [])
    subject    = cfg.get("email_subject", "Pipedrive Deals Report")
    period     = f"{from_date or 'all'} to {to_date or 'today'}"

    html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">
  Pipedrive deals ({status}) &mdash; {period}
</p>
{html_table}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Pipedrive Reporter
</p>
</body></html>"""

    if recipients:
        _send_outlook(subject, recipients, html_body)

    return {
        "rows":          len(deals),
        "status_filter": status,
        "period":        period,
        "emailed_to":    recipients,
    }


def _send_outlook(subject: str, recipients: list[str], html_body: str) -> None:
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.HTMLBody = html_body
    mail.To = "; ".join(recipients)
    mail.Send()
