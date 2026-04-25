import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from api.pipedrive_api import PipedriveClient, build_html_table, build_excel_bytes

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


@app.get("/api/debug")
async def api_debug():
    client = _client()
    return await client.raw_deals_sample()


@app.get("/api/test")
async def api_test():
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


@app.get("/api/owners")
async def api_owners():
    """Return list of active Pipedrive users for the owner dropdown."""
    client = _client()
    try:
        return await client.fetch_owners()
    except Exception as e:
        raise HTTPException(400, f"Could not load owners: {e}")


def _build_preview_html(
    deals: list[dict],
    status: str,
    owner_name: str,
    period: str,
    pdf: bool,
) -> str:
    html_table = build_html_table(deals)
    auto_print = "window.addEventListener('load', () => window.print());" if pdf else ""
    owner_part = f" &bull; Owner: {owner_name}" if owner_name else ""
    count = len(deals)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pipedrive Deals &mdash; {status}</title>
<style>
  body {{ font-family: Arial, sans-serif; padding: 28px; color: #1C1C1E; }}
  h1 {{ font-size: 22px; font-weight: 800; margin-bottom: 4px; }}
  .meta {{ font-size: 13px; color: #6C6C70; margin-bottom: 20px; }}
  table {{ border-collapse: collapse; font-size: 13px; width: 100%; }}
  th {{ background: #f0f0f5; padding: 8px 10px; text-align: left; border: 1px solid #ddd; }}
  td {{ padding: 7px 10px; border: 1px solid #e0e0e0; }}
  tr:nth-child(even) td {{ background: #fafafa; }}
  .print-btn {{
    display: inline-block; margin-bottom: 18px; padding: 9px 20px;
    background: #007AFF; color: #fff; border: none; border-radius: 10px;
    font-size: 15px; font-weight: 600; cursor: pointer;
  }}
  @media print {{ .print-btn {{ display: none; }} }}
</style>
</head>
<body>
<h1>Pipedrive Deals &mdash; {status}</h1>
<div class="meta">Period: {period}{owner_part} &nbsp;&bull;&nbsp; {count} deal{'s' if count != 1 else ''}</div>
<button class="print-btn" onclick="window.print()">&#x1F4E5; Save as PDF / Print</button>
{html_table}
<script>{auto_print}</script>
</body>
</html>"""


@app.get("/api/excel")
async def api_excel(
    status: str = "open",
    owner_id: int = None,
    from_date: str = None,
    to_date: str = None,
):
    """Download deals as an Excel (.xlsx) file."""
    client = _client()
    deals = await client.fetch_all_deals(
        status=status, owner_id=owner_id, from_date=from_date, to_date=to_date
    )
    xlsx = build_excel_bytes(deals)
    filename = f"pipedrive_deals_{status}.xlsx"
    return StreamingResponse(
        iter([xlsx]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/preview", response_class=HTMLResponse)
async def api_preview(
    status: str = "open",
    owner_id: int = None,
    from_date: str = None,
    to_date: str = None,
    pdf: bool = False,
):
    client = _client()
    deals = await client.fetch_all_deals(
        status=status, owner_id=owner_id, from_date=from_date, to_date=to_date
    )
    period = f"{from_date or 'all'} to {to_date or 'today'}"
    owner_name = ""
    if owner_id and deals:
        owner_name = deals[0].get("Owner", "")
    return HTMLResponse(_build_preview_html(deals, status, owner_name, period, pdf))


@app.get("/api/fetch")
async def api_fetch(
    status: str = "open",
    owner_id: int = None,
    from_date: str = None,
    to_date: str = None,
):
    client = _client()
    cfg = load_config() if CONFIG_PATH.exists() else {}

    deals = await client.fetch_all_deals(
        status=status, owner_id=owner_id, from_date=from_date, to_date=to_date
    )

    owner_name = ""
    if owner_id and deals:
        owner_name = deals[0].get("Owner", "")

    period = f"{from_date or 'all'} to {to_date or 'today'}"
    html_table = build_html_table(deals)
    recipients = cfg.get("recipient_emails", [])
    subject    = cfg.get("email_subject", "Pipedrive Deals Report")
    owner_part = f" — {owner_name}" if owner_name else ""

    html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">
  Pipedrive deals ({status}){owner_part} &mdash; {period}
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
        "owner":         owner_name or "all",
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
