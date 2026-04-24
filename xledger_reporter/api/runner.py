import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
DEBUG_SCREENSHOT = Path(__file__).parent.parent / "debug_screenshot.png"

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


async def _dismiss_cookies(page) -> None:
    """Click any cookie consent / GDPR accept button if present."""
    cookie_labels = [
        "Accept all", "Accept All", "Accept", "Allow all", "Allow All",
        "Godta alle", "Godta", "Aksepter", "Aksepter alle",
        "OK", "I agree", "Agree", "Consent",
    ]
    for label in cookie_labels:
        try:
            btn = page.locator(
                f"button:has-text('{label}'), "
                f"a:has-text('{label}'), "
                f"[role='button']:has-text('{label}')"
            ).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.8)
                return
        except Exception:
            continue


async def _dismiss_popup(page) -> None:
    """Close any in-page modal dialog or confirmation message."""
    close_labels = [
        "OK", "Close", "Lukk", "Confirm", "Bekreft",
        "Yes", "Ja", "Accept", "Continue", "Fortsett",
        "Got it", "Dismiss",
    ]
    # Also try generic modal close buttons (×, X)
    close_selectors = [
        "[role='dialog'] button",
        ".modal button",
        ".popup button",
        ".dialog button",
        "button.close",
        "button[aria-label='Close']",
        "button[aria-label='Lukk']",
    ]
    for label in close_labels:
        for el_type in ["button", "a", "div", "span"]:
            try:
                el = page.locator(f"{el_type}:has-text('{label}')").first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                continue
    for sel in close_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.click()
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue


async def _try_fill(page, selector: str, value: str, timeout: int = 5000) -> bool:
    try:
        el = page.locator(selector).first
        if await el.is_visible(timeout=timeout):
            await el.fill(value)
            return True
    except Exception:
        pass
    return False


async def _try_click(page, selector: str, timeout: int = 5000) -> bool:
    try:
        el = page.locator(selector).first
        if await el.is_visible(timeout=timeout):
            await el.click()
            return True
    except Exception:
        pass
    return False


async def _do_login(page, username: str, password: str) -> tuple[bool, str]:
    """
    Attempt login. Returns (success, error_message).
    Handles both single-page and two-step (email then password) forms.
    """
    # Wait generously for the login form to fully render
    try:
        await page.wait_for_selector("input", timeout=20000)
    except PWTimeout:
        return False, "Login page did not load — check the Xledger URL in Settings"

    await asyncio.sleep(2)  # Let JS finish rendering the form

    # Broad selectors ordered from most to least specific
    username_selectors = [
        "input[name='username']",
        "input[name='email']",
        "input[name='UserName']",
        "input[name='Email']",
        "input[type='email']",
        "input[type='text']",
    ]

    filled_username = False
    for sel in username_selectors:
        if await _try_fill(page, sel, username, timeout=5000):
            filled_username = True
            break

    if not filled_username:
        return False, "Could not find the username/email field on the login page"

    await asyncio.sleep(1)  # Pause between fields

    # Check if password field is visible now, or if this is a two-step form
    pw_visible = False
    try:
        pw_el = page.locator("input[type='password']").first
        pw_visible = await pw_el.is_visible(timeout=3000)
    except Exception:
        pass

    if not pw_visible:
        # Two-step form: click Next/Continue after entering username
        for next_label in ["Next", "Continue", "Neste", "Fortsett"]:
            if await _try_click(page, f"button:has-text('{next_label}')"):
                await asyncio.sleep(3)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                break
        else:
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

    # Fill password
    if not await _try_fill(page, "input[type='password']", password, timeout=10000):
        return False, "Could not find the password field — the login form may have changed"

    await asyncio.sleep(1.5)  # Pause before submitting

    # Dismiss cookies again — they sometimes reappear over the submit button
    await _dismiss_cookies(page)
    await asyncio.sleep(1)

    # Submit — try every reasonable selector for a "Sign in / Log in" button
    submit_clicked = False
    sign_in_texts = ["Sign in", "Sign In", "Log in", "Log In", "Login", "Logg inn", "Innlogging"]
    element_types = ["button", "a", "div", "span", "input"]

    for text in sign_in_texts:
        for el_type in element_types:
            sel = f"{el_type}:has-text('{text}')" if el_type != "input" else f"input[value='{text}']"
            if await _try_click(page, sel, timeout=3000):
                submit_clicked = True
                break
        if submit_clicked:
            break

    if not submit_clicked:
        for sel in ["button[type='submit']", "input[type='submit']"]:
            if await _try_click(page, sel, timeout=3000):
                submit_clicked = True
                break

    if not submit_clicked:
        await page.locator("input[type='password']").first.press("Enter")

    # Wait generously for the page to navigate after login
    await asyncio.sleep(2)
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except PWTimeout:
        pass

    await asyncio.sleep(10)  # Extra buffer for SPA routing after login

    # Detect login failure: password field still visible means we didn't get past the form
    pw_still_visible = False
    try:
        pw_el = page.locator("input[type='password']").first
        pw_still_visible = await pw_el.is_visible(timeout=3000)
    except Exception:
        pass

    if pw_still_visible:
        return False, "Login failed — username or password was not accepted"

    return True, ""


async def _click_menu_item(page, label: str) -> bool:
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
        if await _try_click(page, sel, timeout=4000):
            return True
    return False


async def run_report() -> AsyncGenerator[str, None]:
    global _running
    if _running:
        yield "data: Already running — please wait\n\n"
        return

    _running = True
    page = None
    browser = None
    try:
        yield "data: Loading configuration...\n\n"
        await asyncio.sleep(0.1)
        config = load_config()

        menu_path: list[str] = config.get("menu_path", [])
        run_button: str = config.get("run_button", "").strip()
        login_url: str = config.get("login_url", "https://www.xledger.net/").rstrip("/") + "/"

        yield "data: Starting browser...\n\n"
        await asyncio.sleep(0.1)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=config.get("headless", False))
            context = await browser.new_context()
            page = await context.new_page()

            # ---- Login ----
            yield f"data: Opening {login_url} ...\n\n"
            await page.goto(login_url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")

            yield "data: Checking for cookie consent dialog...\n\n"
            await _dismiss_cookies(page)

            yield "data: Filling in login details...\n\n"
            ok, err = await _do_login(page, config["xledger_username"], config["xledger_password"])

            if not ok:
                screenshot = await page.screenshot(full_page=False)
                DEBUG_SCREENSHOT.write_bytes(screenshot)
                yield f"data: ERROR: {err}\n\n"
                yield f"data: A screenshot was saved to debug_screenshot.png in the app folder — open it to see what the browser shows\n\n"
                await browser.close()
                return

            yield "data: Logged in successfully\n\n"

            # ---- Navigate via menu ----
            if not menu_path:
                yield "data: WARNING: No menu path configured — capturing current page\n\n"
            else:
                for item in menu_path:
                    yield f"data: Clicking menu: {item}...\n\n"
                    found = await _click_menu_item(page, item)
                    if not found:
                        screenshot = await page.screenshot(full_page=False)
                        DEBUG_SCREENSHOT.write_bytes(screenshot)
                        yield f"data: ERROR: Could not find menu item '{item}'\n\n"
                        yield f"data: A screenshot was saved to debug_screenshot.png — open it to see the current screen\n\n"
                        await browser.close()
                        return
                    await asyncio.sleep(1.5)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except PWTimeout:
                        pass

            # ---- Click Run/Search/Find button to execute the report ----
            # Try the configured button name first, then fall back to common labels
            run_button_candidates = []
            if run_button:
                run_button_candidates.append(run_button)
            run_button_candidates += [
                "Find", "Finn",        # Xledger standard
                "Search", "Søk",
                "Run", "Kjør",
                "Execute", "Utfør",
                "Generate",
                "Show", "Vis",
                "Refresh", "Oppdater",
                "OK",
            ]

            yield "data: Waiting for report interface to load...\n\n"
            await asyncio.sleep(3)

            yield "data: Looking for Find/Run button...\n\n"
            report_triggered = False
            for label in run_button_candidates:
                for el_type in ["button", "input", "a", "div", "span"]:
                    sel = (
                        f"input[value='{label}']"
                        if el_type == "input"
                        else f"{el_type}:has-text('{label}')"
                    )
                    if await _try_click(page, sel, timeout=3000):
                        yield f"data: Clicked '{label}' button\n\n"
                        report_triggered = True
                        break
                if report_triggered:
                    break

            if not report_triggered:
                yield "data: Note: no Find/Run button found — capturing page as-is\n\n"
            else:
                # Accept any native browser dialog that appears (alert/confirm/prompt)
                page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except PWTimeout:
                    pass

            # Dismiss any in-page modal/popup that appeared (confirmation, info message, etc.)
            yield "data: Checking for any popup messages...\n\n"
            await asyncio.sleep(2)
            await _dismiss_popup(page)

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
        if page:
            try:
                screenshot = await page.screenshot(full_page=False)
                DEBUG_SCREENSHOT.write_bytes(screenshot)
                yield f"data: ERROR: {e}\n\n"
                yield "data: A screenshot was saved to debug_screenshot.png in the app folder\n\n"
            except Exception:
                yield f"data: ERROR: {e}\n\n"
        else:
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
