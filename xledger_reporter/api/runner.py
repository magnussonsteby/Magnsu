import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
DEBUG_SCREENSHOT = Path(__file__).parent.parent / "debug_screenshot.png"

_running = False

# Manual mode: keep browser alive between login and capture
_manual_browser = None
_manual_page = None
_manual_pw = None
_recorded_steps: list[dict] = []   # steps captured during manual session

# JS injected on every page to record clicks + URL changes
_RECORDER_JS = """
if (!window._xrInited) {
    window._xrInited = true;
    window._xrClicks = [];
    document.addEventListener('click', function(e) {
        const el = e.target.closest(
            'button, a, input[type="submit"], input[type="button"], ' +
            '[role="button"], [role="menuitem"], li, td, span'
        ) || e.target;
        const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
        const shortText = text.replace(/\\s+/g, ' ').substring(0, 80);
        if (shortText.length > 1) {
            window._xrClicks.push({
                url:  window.location.href,
                text: shortText,
                tag:  el.tagName.toLowerCase(),
            });
        }
    }, true);
}
"""


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("config.json not found — please complete setup first")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def browser_is_open() -> bool:
    return _manual_page is not None


def get_playbook() -> list[dict]:
    try:
        cfg = load_config()
        return [s for s in cfg.get("playbook", []) if s.get("text")]
    except Exception:
        return []


def _table_to_html(table_html: str) -> str:
    return (
        '<table border="1" cellpadding="6" cellspacing="0" '
        'style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">'
        + table_html + "</table>"
    )


async def _dismiss_popup(page) -> None:
    close_labels = [
        "OK", "Close", "Lukk", "Confirm", "Bekreft",
        "Yes", "Ja", "Accept", "Continue", "Fortsett", "Got it", "Dismiss",
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
    for sel in ["[role='dialog'] button", ".modal button", ".popup button",
                "button.close", "button[aria-label='Close']", "button[aria-label='Lukk']"]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.click()
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue


async def _dismiss_cookies(page) -> None:
    for label in ["Accept all", "Accept All", "Accept", "Allow all", "Allow All",
                  "Godta alle", "Godta", "Aksepter", "Aksepter alle", "OK", "I agree"]:
        try:
            btn = page.locator(
                f"button:has-text('{label}'), a:has-text('{label}'), [role='button']:has-text('{label}')"
            ).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.8)
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
    try:
        await page.wait_for_selector("input", timeout=20000)
    except PWTimeout:
        return False, "Login page did not load — check the Xledger URL in Settings"

    await asyncio.sleep(2)

    filled_username = False
    for sel in ["input[name='username']", "input[name='email']", "input[name='UserName']",
                "input[name='Email']", "input[type='email']", "input[type='text']"]:
        if await _try_fill(page, sel, username, timeout=5000):
            filled_username = True
            break
    if not filled_username:
        return False, "Could not find the username/email field on the login page"

    await asyncio.sleep(1)

    pw_visible = False
    try:
        pw_visible = await page.locator("input[type='password']").first.is_visible(timeout=3000)
    except Exception:
        pass

    if not pw_visible:
        for next_label in ["Next", "Continue", "Neste", "Fortsett"]:
            if await _try_click(page, f"button:has-text('{next_label}')"):
                await asyncio.sleep(3)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except PWTimeout:
                    pass
                await asyncio.sleep(2)
                break
        else:
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

    if not await _try_fill(page, "input[type='password']", password, timeout=10000):
        return False, "Could not find the password field"

    await asyncio.sleep(1.5)
    await _dismiss_cookies(page)
    await asyncio.sleep(1)

    submit_clicked = False
    for text in ["Sign in", "Sign In", "Log in", "Log In", "Login", "Logg inn", "Innlogging"]:
        for el_type in ["button", "a", "div", "span"]:
            sel = f"input[value='{text}']" if el_type == "input" else f"{el_type}:has-text('{text}')"
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

    await asyncio.sleep(2)
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except PWTimeout:
        pass
    await asyncio.sleep(10)

    try:
        pw_still_visible = await page.locator("input[type='password']").first.is_visible(timeout=3000)
    except Exception:
        pw_still_visible = False
    if pw_still_visible:
        return False, "Login failed — username or password was not accepted"

    return True, ""


async def _capture_page(page) -> tuple[bytes, str]:
    screenshot = await page.screenshot(full_page=True)
    raw_tables = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('table')).map(t => t.outerHTML).join('\\n')
    """)
    if raw_tables.strip():
        parts = []
        for chunk in raw_tables.split("</table>"):
            chunk = chunk.strip()
            if "<tr" in chunk or "<td" in chunk or "<th" in chunk:
                parts.append(_table_to_html(chunk + "</table>"))
        report_body = "<br><br>".join(parts)
    else:
        text = await page.evaluate("""() => {
            const el = document.querySelector('main,[role="main"],#content,.content,body');
            return el ? el.innerText : document.body.innerText;
        }""")
        report_body = f"<pre style='font-family:monospace;font-size:12px'>{text}</pre>"
    return screenshot, report_body


def _send_outlook(subject: str, recipients: list[str], html_body: str, screenshot: bytes | None = None):
    import win32com.client  # type: ignore
    import tempfile, os
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


def _build_playbook(clicks: list[dict]) -> list[dict]:
    """
    Convert raw click log into a clean playbook.
    Keeps unique meaningful click labels in order.
    """
    seen = set()
    steps = []
    for c in clicks:
        text = c.get("text", "").strip().replace("\n", " ")
        tag  = c.get("tag", "")
        # Skip empty, single-char, or pure-noise labels
        if len(text) < 2:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        steps.append({"text": text, "tag": tag})
    return steps


# ---------------------------------------------------------------------------
# Manual mode: login → user navigates → capture
# ---------------------------------------------------------------------------

async def manual_login() -> AsyncGenerator[str, None]:
    global _running, _manual_browser, _manual_page, _manual_pw, _recorded_steps

    if _running:
        yield "data: Already running — please wait\n\n"
        return
    if _manual_page is not None:
        yield "data: READY: Browser already open — navigate to your report and click Capture & Send\n\n"
        return

    _running = True
    _recorded_steps = []
    try:
        yield "data: Loading configuration...\n\n"
        config = load_config()
        login_url = config.get("login_url", "https://www.xledger.net/").rstrip("/") + "/"

        yield "data: Starting browser...\n\n"
        _manual_pw = await async_playwright().start()
        _manual_browser = await _manual_pw.chromium.launch(headless=False)
        context = await _manual_browser.new_context()
        _manual_page = await context.new_page()

        # Inject recorder on every page navigation
        await context.add_init_script(_RECORDER_JS)

        yield f"data: Opening {login_url} ...\n\n"
        await _manual_page.goto(login_url, timeout=30000)
        await _manual_page.wait_for_load_state("domcontentloaded")

        yield "data: Dismissing cookie consent...\n\n"
        await _dismiss_cookies(_manual_page)

        yield "data: Logging in...\n\n"
        ok, err = await _do_login(_manual_page, config["xledger_username"], config["xledger_password"])
        if not ok:
            screenshot = await _manual_page.screenshot()
            DEBUG_SCREENSHOT.write_bytes(screenshot)
            yield f"data: ERROR: {err}\n\n"
            yield "data: Screenshot saved to debug_screenshot.png\n\n"
            await _manual_browser.close()
            await _manual_pw.stop()
            _manual_browser = _manual_page = _manual_pw = None
            return

        yield "data: Dismissing post-login popup...\n\n"
        await asyncio.sleep(2)
        await _dismiss_popup(_manual_page)

        # Reset recorder NOW so only the user's navigation steps are captured
        await _manual_page.evaluate(_RECORDER_JS + "\nwindow._xrClicks = [];")

        yield "data: READY: Logged in! Navigate to your report in the browser window, then click Capture & Send here\n\n"

    except Exception as e:
        yield f"data: ERROR: {e}\n\n"
        if _manual_browser:
            try:
                await _manual_browser.close()
                await _manual_pw.stop()
            except Exception:
                pass
            _manual_browser = _manual_page = _manual_pw = None
    finally:
        _running = False


async def manual_capture() -> AsyncGenerator[str, None]:
    global _manual_browser, _manual_page, _manual_pw

    if _manual_page is None:
        yield "data: ERROR: No browser open — click Login first\n\n"
        return

    try:
        yield "data: Capturing current page...\n\n"
        config = load_config()
        login_url = config.get("login_url", "https://www.xledger.net/").rstrip("/") + "/"

        # Collect recorded clicks from the browser
        try:
            raw_clicks = await _manual_page.evaluate("() => window._xrClicks || []")
            playbook = _build_playbook(raw_clicks)
            if playbook:
                config["playbook"] = playbook
                save_config(config)
                labels = ", ".join(s["text"] for s in playbook[:6])
                yield f"data: Recorded {len(playbook)} step(s): {labels} — will run automatically next time\n\n"
            else:
                yield "data: Note: no steps were recorded (clicks may not have been detected)\n\n"
        except Exception as ex:
            yield f"data: Note: recording failed ({ex})\n\n"

        screenshot, report_body = await _capture_page(_manual_page)

        recipients = config.get("recipient_emails", [])
        subject = config.get("email_subject", "Xledger Time Report")

        yield "data: Composing email...\n\n"
        html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">Please find below the Xledger report.</p>
{report_body}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Xledger Reporter</p>
</body></html>"""

        yield "data: Sending email via Outlook...\n\n"
        _send_outlook(subject, recipients, html_body, screenshot)
        yield f"data: DONE: Email sent to {', '.join(recipients)}\n\n"

    except Exception as e:
        yield f"data: ERROR: {e}\n\n"
    finally:
        try:
            await _manual_browser.close()
            await _manual_pw.stop()
        except Exception:
            pass
        _manual_browser = _manual_page = _manual_pw = None


async def close_browser() -> None:
    global _manual_browser, _manual_page, _manual_pw
    if _manual_browser:
        try:
            await _manual_browser.close()
            await _manual_pw.stop()
        except Exception:
            pass
        _manual_browser = _manual_page = _manual_pw = None


# ---------------------------------------------------------------------------
# Auto mode: replay recorded playbook or fall back to menu_path
# ---------------------------------------------------------------------------

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
        config = load_config()
        login_url = config.get("login_url", "https://www.xledger.net/").rstrip("/") + "/"
        playbook: list[dict] = config.get("playbook", [])
        menu_path: list[str] = config.get("menu_path", [])

        yield "data: Starting browser...\n\n"
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=config.get("headless", False))
            context = await browser.new_context()
            page = await context.new_page()

            yield f"data: Opening {login_url} ...\n\n"
            await page.goto(login_url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")

            yield "data: Dismissing cookie consent...\n\n"
            await _dismiss_cookies(page)

            yield "data: Logging in...\n\n"
            ok, err = await _do_login(page, config["xledger_username"], config["xledger_password"])
            if not ok:
                screenshot = await page.screenshot()
                DEBUG_SCREENSHOT.write_bytes(screenshot)
                yield f"data: ERROR: {err}\n\n"
                yield "data: Screenshot saved to debug_screenshot.png\n\n"
                await browser.close()
                return

            yield "data: Logged in successfully\n\n"
            await asyncio.sleep(2)
            await _dismiss_popup(page)

            # --- Replay playbook if available ---
            if playbook:
                yield f"data: Replaying {len(playbook)} recorded step(s)...\n\n"
                for step in playbook:
                    text = step.get("text", "")
                    tag  = step.get("tag", "")
                    if not text:
                        continue
                    yield f"data: Clicking '{text}'...\n\n"
                    # Try with the recorded tag first, then fall back to any element
                    selectors = []
                    if tag:
                        selectors.append(f"{tag}:has-text('{text}')")
                    selectors += [
                        f"button:has-text('{text}')",
                        f"a:has-text('{text}')",
                        f"[role='menuitem']:has-text('{text}')",
                        f"*:has-text('{text}')",
                    ]
                    clicked = False
                    for sel in selectors:
                        if await _try_click(page, sel, timeout=4000):
                            clicked = True
                            break
                    if clicked:
                        await asyncio.sleep(2)
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=10000)
                        except PWTimeout:
                            pass
                    else:
                        yield f"data: Note: could not find '{text}' — continuing\n\n"

            elif menu_path:
                # Fall back to menu_path navigation
                for item in menu_path:
                    yield f"data: Clicking menu: {item}...\n\n"
                    selectors = [
                        f"nav a:has-text('{item}')", f"nav button:has-text('{item}')",
                        f"[role='menuitem']:has-text('{item}')", f"a:has-text('{item}')",
                        f"button:has-text('{item}')", f"span:has-text('{item}')",
                    ]
                    found = False
                    for sel in selectors:
                        if await _try_click(page, sel, timeout=4000):
                            found = True
                            break
                    if not found:
                        screenshot = await page.screenshot()
                        DEBUG_SCREENSHOT.write_bytes(screenshot)
                        yield f"data: ERROR: Could not find menu item '{item}'\n\n"
                        yield "data: Tip: use Manual Mode once so the steps get recorded automatically\n\n"
                        await browser.close()
                        return
                    await asyncio.sleep(1.5)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except PWTimeout:
                        pass
            else:
                yield "data: No playbook or menu path — capturing current page\n\n"

            yield "data: Waiting for report to load...\n\n"
            await asyncio.sleep(3)

            yield "data: Capturing report data...\n\n"
            screenshot, report_body = await _capture_page(page)
            await browser.close()

        recipients = config.get("recipient_emails", [])
        subject = config.get("email_subject", "Xledger Time Report")
        yield "data: Composing email...\n\n"
        html_body = f"""<html><body>
<p style="font-family:Arial,sans-serif;font-size:14px">Please find below the Xledger report from Xledger.</p>
{report_body}
<p style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:20px">
  Sent automatically by Xledger Reporter</p>
</body></html>"""
        yield "data: Sending email via Outlook...\n\n"
        _send_outlook(subject, recipients, html_body, screenshot)
        yield f"data: DONE: Email sent to {', '.join(recipients)}\n\n"

    except FileNotFoundError as e:
        yield f"data: ERROR: {e}\n\n"
    except Exception as e:
        if page:
            try:
                screenshot = await page.screenshot()
                DEBUG_SCREENSHOT.write_bytes(screenshot)
                yield f"data: ERROR: {e}\n\n"
                yield "data: Screenshot saved to debug_screenshot.png\n\n"
            except Exception:
                yield f"data: ERROR: {e}\n\n"
        else:
            yield f"data: ERROR: {e}\n\n"
    finally:
        _running = False
