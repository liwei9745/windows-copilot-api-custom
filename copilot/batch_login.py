"""Batch multi-account login for Microsoft Copilot.

Uses headless Playwright to navigate through Microsoft login flow,
auto-fills credentials, and captures proper auth tokens.

Usage:
    python -m copilot login accounts.txt
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from .auth import SESSION_DIR


def _ts(msg: str) -> str:
    return f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"


def _log(msg: str, log_fh=None):
    line = _ts(msg)
    print(line, flush=True)
    if log_fh:
        log_fh.write(line + "\n")
        log_fh.flush()


def _run_browser_login(profile_dir: str, username: str, password: str, log_fh=None) -> dict:
    """Use headless Playwright to navigate through Microsoft login,
    auto-fill username and password, and capture the auth result.

    Returns the auth dict from export_auth(), or empty dict on failure.
    """
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    from .useragent import CHROME_UA

    auth = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=CHROME_UA,
                storage_state=None,
            )
            page = context.new_page()

            # Navigate to Microsoft live login page directly
            _log("[browser] Navigating to Microsoft login for Copilot...", log_fh)
            import urllib.parse
            oauth_params = {
                'client_id': '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
                'response_type': 'code',
                'redirect_uri': 'https://copilot.microsoft.com/',
                'scope': 'openid profile email ChatAI.ReadWrite',
                'response_mode': 'query',
            }
            oauth_url = 'https://login.live.com/oauth20_authorize.srf?' + urllib.parse.urlencode(oauth_params)
            page.goto(oauth_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Auto-fill username
            _log("[browser] Filling username...", log_fh)
            try:
                username_input = page.wait_for_selector('input[name="loginfmt"]', timeout=10000)
                username_input.fill(username)
                page.wait_for_timeout(500)
                page.click('input[type="submit"], #idSIButton9')
                _log("[browser] Username submitted.", log_fh)
            except Exception as e:
                _log(f"[browser] Username field not found: {e}", log_fh)
                browser.close()
                return {}

            # Auto-fill password
            _log("[browser] Filling password...", log_fh)
            try:
                password_input = page.wait_for_selector('input[name="passwd"]', timeout=10000)
                page.wait_for_timeout(500)
                password_input.fill(password)
                page.wait_for_timeout(500)
                page.click('input[type="submit"], #idSIButton9')
                _log("[browser] Password submitted.", log_fh)
            except Exception as e:
                _log(f"[browser] Password field not found: {e}", log_fh)
                browser.close()
                return {}

            # Handle "Stay signed in" prompt
            try:
                page.wait_for_selector('input[name="DontShowAgain"]', timeout=5000)
                page.wait_for_timeout(300)
                page.click('input[type="submit"], #idSIButton9')
                _log("[browser] Stay signed in accepted.", log_fh)
            except Exception:
                pass

            # Handle verification code if prompted
            try:
                otc_input = page.wait_for_selector('input[name="otc"]', timeout=3000)
                if otc_input and otc_input.is_visible():
                    _log("[browser] Verification code required. Check your email/authenticator.", log_fh)
                    code = input("  Enter verification code (or 'skip'): ").strip()
                    if code.lower() == "skip":
                        _log("[browser] Skipping verification.", log_fh)
                        browser.close()
                        return {}
                    otc_input.fill(code)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(2000)
            except Exception:
                pass

            # Wait for redirect back to copilot.microsoft.com
            _log("[browser] Waiting for redirect to Copilot...", log_fh)
            try:
                page.wait_for_url("**/copilot.microsoft.com/**", timeout=15000)
            except Exception:
                _log("[browser] Redirect to Copilot not detected within 15s. Continuing anyway...", log_fh)

            page.wait_for_timeout(3000)

            # Export auth (cookies + access_token)
            _log("[browser] Exporting auth...", log_fh)
            cookies = {}
            for c in context.cookies():
                cookies[c["name"]] = c["value"]

            # Try to get access_token from localStorage
            access_token = ""
            try:
                access_token = page.evaluate("""() => {
                    for (const key of Object.keys(localStorage)) {
                        try {
                            const val = JSON.parse(localStorage[key]);
                            if (val && val.secret && val.secret.startsWith('eyJ')) return val.secret;
                            if (val && val.accessToken) return val.accessToken;
                            if (val && val.credential) return val.credential;
                        } catch(e) {}
                    }
                    return '';
                }""")
            except Exception:
                pass

            browser.close()

            auth = {
                "cookies": cookies,
                "access_token": access_token or None,
                "identity_type": "microsoft",
                "saved_at": time.time(),
            }
            _log(f"[browser] Got {len(cookies)} cookies, access_token={'yes' if access_token else 'no'}", log_fh)
            return auth

    except Exception as e:
        _log(f"[browser] Browser error: {e}", log_fh)
        return {}


def login_one(
    username: str,
    password: str,
    account_index: int,
    refresh_token: str = "",
    log_fh=None,
) -> bool:
    """Login one account.

    Uses headless browser to go through Microsoft login flow and capture
    the proper Copilot auth (cookies + access_token with ChatAI.ReadWrite scope).

    Returns True if login succeeded, False otherwise.
    """
    session_dir = f"{SESSION_DIR}/account_{account_index}"
    os.makedirs(session_dir, exist_ok=True)
    token_path = f"{session_dir}/token.json"

    _log(f"[{account_index}] === Logging in: {username} ===", log_fh)
    _log(f"[{account_index}] Using headless browser to complete Microsoft login flow...", log_fh)

    profile_dir = f"{session_dir}/profile"
    auth = _run_browser_login(profile_dir, username, password, log_fh)

    if auth.get("access_token") and auth.get("cookies"):
        Path(token_path).write_text(json.dumps(auth, indent=2), encoding="utf-8")
        _log(f"[{account_index}] SUCCESS: Credentials saved to {token_path}", log_fh)
        return True
    else:
        _log(f"[{account_index}] FAILED: Could not obtain auth (token={'yes' if auth.get('access_token') else 'no'}, cookies={len(auth.get('cookies', {}))})", log_fh)
        return False


def login_from_file(file_path: str) -> int:
    """Read account file and login each account sequentially.

    Returns: number of successfully logged in accounts.
    """
    log_path = Path(SESSION_DIR) / "batch_login.log"
    os.makedirs(SESSION_DIR, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as log_fh:
        _log(f"=== Batch login started: {file_path} ===", log_fh)
        _log(f"Log file: {log_path}", log_fh)

        if not os.path.exists(file_path):
            _log(f"ERROR: File not found: {file_path}", log_fh)
            return 0

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        accounts = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or "----" not in line:
                continue
            parts = line.split("----")
            username = parts[0].strip()
            password = parts[1].strip()
            refresh_token = parts[3].strip() if len(parts) >= 4 else ""
            accounts.append((username, password, refresh_token))

        if not accounts:
            _log("No valid accounts found in the file.", log_fh)
            _log("Expected format: email----password----uuid----MSAL_refresh_token", log_fh)
            return 0

        _log(f"Found {len(accounts)} accounts to process.", log_fh)
        _log("Using MSAL refresh tokens (no browser needed for most accounts).", log_fh)

        success_count = 0
        fail_count = 0

        for idx, (username, password, refresh_token) in enumerate(accounts, 1):
            _log(f"\n{'='*60}", log_fh)
            _log(f"Account {idx}/{len(accounts)}", log_fh)
            _log(f"Email: {username}", log_fh)

            try:
                ok = login_one(username, password, idx, refresh_token, log_fh=log_fh)
                if ok:
                    success_count += 1
                    _log(f"[OK] Account {idx} login SUCCEEDED.", log_fh)
                else:
                    fail_count += 1
                    _log(f"[FAIL] Account {idx} login FAILED.", log_fh)
            except KeyboardInterrupt:
                _log("\n\nBatch login interrupted by user.", log_fh)
                break
            except Exception as e:
                fail_count += 1
                _log(f"[ERROR] Account {idx} exception: {e}", log_fh)

        _log(f"\n{'='*60}", log_fh)
        _log(f"=== BATCH LOGIN COMPLETE ===", log_fh)
        _log(f"Total accounts processed: {success_count + fail_count}", log_fh)
        _log(f"Successful: {success_count}", log_fh)
        _log(f"Failed: {fail_count}", log_fh)
        _log(f"Credentials saved under: {SESSION_DIR}/account_*/", log_fh)

    return success_count
