import asyncio
import json
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
    return (
        '<table border="1" cellpadding="6" cellspacing="0" '
        'style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">'
        + table_html
        + "</table>"
    )


async def _click_menu_item(page, label: str) -> bool:
    """Try to click a nav/menu element whose visible text matches label."""
    selectors = [
        f"nav a:has-text('{label}')",
        f"nav button:has-text('{label}')",
        f"[role='menuitem']:has-text('{label}')",
        f"[role='menu'] a:has-text('{label}')",
        f"li a:has-text('{label}')",
        f"li:has-text('{label}') > a",
        f"a:has-text('{label}')",
        f"button:has-text('{label}')",
        f"span:has-text('{label}')",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                return True
        except Exception:
            continue
    return False


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

        menu_path: list[str] = config.get("menu_path", [])
        run_button: str = config.get("run_button", "").strip()

        yield "data: Starting browser...\n\n"
        await asyncio.sleep(0.1)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=config.get("headless", False))
            context = await browser.new_context()
            page = await context.new_page()

            # ---- Login ----
            yield "data: Opening Xledger...\n\n"
            await page.goto("https://www.xledger.net/", timeout=30000)
            await page.wait_for_load_state("domcontentloaded")

            yield "data: Entering credentials...\n\n"
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
                yield "data: Logging in...\n\n"
                await page.click(submit_sel)
                await page.wait_for_load_state("networkidle", timeout=25000)
            except PWTimeout:
                yield "data: ERROR: Could not find login form — is xledger.net reachable?\n\n"
                await browser.close()
                return

            if "login" in page.url.lower() or "signin" in page.url.lower():
                yield "data: ERROR: Login failed — check your username and password in Settings\n\n"
                await browser.close()
                return

            yield "data: Logged in successfully\n\n"

            # ---- Navigate via menu ----
            if not menu_path:
                yield "data: WARNING: No menu path configured — capturing current page\n\n"
            else:
                for i, item in enumerate(menu_path):
                    yield f"data: Clicking menu: {item}...\n\n"
                    found = await _click_menu_item(page, item)
                    if not found:
                        yield f"data: ERROR: Could not find menu item '{item}' — check the menu path in Settings\n\n"
                        await browser.close()
                        return
                    await asyncio.sleep(1.5)
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)

            # ---- Click Run/Search button if configured ----
            if run_button:
                yield f"data: Clicking '{run_button}' button...\n\n"
                try:
                    await page.click(
                        f"button:has-text('{run_button}'), input[value='{run_button}'], "
                        f"a:has-text('{run_button}')",
                        timeout=8000,
                    )
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except PWTimeout:
                    yield f"data: Note: '{run_button}' button not found — capturing page as-is\n\n"

            # ---- Wait for report content ----
            yield "data: Waiting for report to load...\n\n"
            await asyncio.sleep(3)

            # ---- Capture ----
            yield "data: Capturing report data...\n\n"
            screenshot = await page.screenshot(full_page=True)

            raw_tables = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('table'))
                    .map(t => t.outerHTML).join('\\n');
            }""")

            if raw_tables.strip():
                parts = []
                for chunk in raw_tables.split("</table>"):
                    chunk = chunk.strip()
                    if "<tr" in chunk or "<td" in chunk or "<th" in chunk:
                        parts.append(_table_to_html(chunk + "</table>"))
                report_body = "<br><br>".join(parts)
            else:
                yield "data: No tables found — capturing visible text instead\n\n"
                text = await page.evaluate("""() => {
                    const el = document.querySelector('main, [role=\"main\"], #content, .content, body');
                    return el ? el.innerText : document.body.innerText;
                }""")
                report_body = f"<pre style='font-family:monospace;font-size:12px'>{text}</pre>"

            await browser.close()

        # ---- Send via Outlook ----
        recipients = config.get("recipient_emails", [])
        subject = config.get("email_subject", "Xledger Time Report")
        menu_label = " > ".join(menu_path) if menu_path else "Xledger"

        yield "data: Composing email...\n\n"
        html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">
  Please find below the <b>{menu_label}</b> report from Xledger.
</p>
{report_body}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Xledger Reporter
</p>
</body></html>"""

        yield "data: Sending email via Outlook...\n\n"
        _send_outlook(subject, recipients, html_body, screenshot)

        yield f"data: DONE: Email sent to {', '.join(recipients)}\n\n"

    except FileNotFoundError as e:
        yield f"data: ERROR: {e}\n\n"
    except Exception as e:
        yield f"data: ERROR: {e}\n\n"
    finally:
        _running = False


def _send_outlook(subject: str, recipients: list[str], html_body: str, screenshot: bytes | None = None):
    import win32com.client  # type: ignore
    import tempfile
    import os

    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.To = "; ".join(recipients)
    mail.HTMLBody = html_body

    if screenshot:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(screenshot)
            tmp_path = tmp.name
        try:
            mail.Attachments.Add(tmp_path, 1, 0, "report_screenshot.png")
        finally:
            os.unlink(tmp_path)

    mail.Send()
