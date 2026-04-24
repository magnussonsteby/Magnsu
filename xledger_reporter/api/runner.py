import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

_running = False


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("config.json not found — please complete setup first")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _table_to_html(table_html: str) -> str:
    return f"""
<table border="1" cellpadding="6" cellspacing="0"
       style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">
  {table_html}
</table>"""


async def run_report() -> AsyncGenerator[str, None]:
    global _running
    if _running:
        yield "data: Already running — please wait\n\n"
        return

    _running = True
    try:
        yield "data: Loading configuration...\n\n"
        await asyncio.sleep(0.1)
        config = load_config()

        yield "data: Starting browser...\n\n"
        await asyncio.sleep(0.1)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=config.get("headless", False))
            context = await browser.new_context()
            page = await context.new_page()

            # ---- Login ----
            yield "data: Opening Xledger login page...\n\n"
            await page.goto("https://www.xledger.net/", timeout=30000)
            await page.wait_for_load_state("domcontentloaded")

            yield "data: Entering credentials...\n\n"
            # Try common username/email field selectors
            username_sel = (
                "input[name='username'], input[name='email'], "
                "input[type='email'], input[id*='user'], input[id*='login']"
            )
            password_sel = "input[type='password']"
            submit_sel = (
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Log in'), button:has-text('Sign in'), button:has-text('Login')"
            )

            try:
                await page.wait_for_selector(username_sel, timeout=10000)
                await page.fill(username_sel, config["xledger_username"])
                await page.fill(password_sel, config["xledger_password"])

                yield "data: Submitting login...\n\n"
                await page.click(submit_sel)
                await page.wait_for_load_state("networkidle", timeout=20000)
            except PWTimeout:
                yield "data: ERROR: Could not find login form — check the Xledger URL\n\n"
                await browser.close()
                return

            # Check for login failure
            current_url = page.url
            if "login" in current_url.lower() or "signin" in current_url.lower():
                yield "data: ERROR: Login may have failed — check username and password in Settings\n\n"
                await browser.close()
                return

            yield "data: Logged in successfully!\n\n"

            # ---- Navigate to report ----
            report_url = config.get("report_url", "").strip()
            if not report_url or report_url == "https://www.xledger.net/":
                yield "data: WARNING: No report URL configured — showing current page\n\n"
            else:
                yield f"data: Opening report...\n\n"
                await page.goto(report_url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=30000)

            # ---- Wait for any loading spinners to disappear ----
            yield "data: Waiting for report to fully load...\n\n"
            try:
                await page.wait_for_function(
                    "() => !document.querySelector('.loading, .spinner, [class*=\"load\"]')",
                    timeout=15000,
                )
            except PWTimeout:
                pass  # Continue even if spinner check times out

            await asyncio.sleep(2)  # Extra buffer for dynamic content

            # ---- Extract report data ----
            yield "data: Capturing report data...\n\n"

            # Take screenshot
            screenshot = await page.screenshot(full_page=True)

            # Extract all tables from the page
            tables_html = await page.evaluate("""() => {
                const tables = Array.from(document.querySelectorAll('table'));
                return tables.map(t => t.outerHTML).join('\\n');
            }""")

            # If no tables, fall back to capturing main content text
            if not tables_html.strip():
                yield "data: No tables found — capturing visible text...\n\n"
                tables_html = await page.evaluate("""() => {
                    const main = document.querySelector('main, #content, .content, body');
                    return main ? main.innerText : document.body.innerText;
                }""")
                report_body = f"<pre style='font-family:monospace;font-size:12px'>{tables_html}</pre>"
            else:
                styled_tables = []
                for t in tables_html.split("</table>"):
                    t = t.strip()
                    if t:
                        styled_tables.append(_table_to_html(t + "</table>"))
                report_body = "<br>".join(styled_tables)

            await browser.close()

        # ---- Send via Outlook ----
        yield "data: Composing email...\n\n"
        recipients = config.get("recipient_emails", [])
        subject = config.get("email_subject", "Xledger Report")

        html_body = f"""
<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">
  Please find below the Xledger report.
</p>
{report_body}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Xledger Reporter
</p>
</body></html>"""

        yield "data: Opening Outlook and sending email...\n\n"
        _send_outlook(subject, recipients, html_body, screenshot)

        recipient_list = ", ".join(recipients)
        yield f"data: DONE: Email sent to {recipient_list}\n\n"

    except FileNotFoundError as e:
        yield f"data: ERROR: {e}\n\n"
    except Exception as e:
        yield f"data: ERROR: {e}\n\n"
    finally:
        _running = False


def _send_outlook(subject: str, recipients: list[str], html_body: str, screenshot: bytes | None = None):
    import win32com.client  # type: ignore
    import tempfile, os

    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # olMailItem = 0
    mail.Subject = subject
    mail.To = "; ".join(recipients)
    mail.HTMLBody = html_body

    if screenshot:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(screenshot)
            tmp_path = tmp.name
        try:
            mail.Attachments.Add(tmp_path, 1, 0, "report_screenshot.png")  # olByValue=1
        finally:
            os.unlink(tmp_path)

    mail.Send()
