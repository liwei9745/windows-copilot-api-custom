"""Batch multi-account login for Microsoft Copilot.

Opens a visible browser for each account to the OAuth authorize page.
User manually logs in. Script auto-captures the redirect URL.

Usage:
    python -m copilot login accounts.txt
"""

import json
import os
import re
import sys
import time
import urllib.parse
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


CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
SCOPE = "openid profile email ChatAI.ReadWrite"


def build_oauth_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "token",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    }
    return "https://login.live.com/oauth20_authorize.srf?" + urllib.parse.urlencode(params)


def extract_token_from_url(url: str) -> str:
    """Extract access_token from URL fragment or query."""
    m = re.search(r"access_token=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.search(r"[?&]code=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    return ""


def login_one(username: str, account_index: int, log_fh=None) -> bool:
    """Login one account via OAuth in a visible browser.

    1. Opens visible browser → navigates to OAuth authorize page
    2. User manually logs in the browser
    3. After redirect, script extracts access_token from URL
    4. Captures cookies and saves credentials
    5. Closes browser, moves to next account
    """
    session_dir = f"{SESSION_DIR}/account_{account_index}"
    token_path = f"{session_dir}/token.json"
    os.makedirs(session_dir, exist_ok=True)

    _log(f"\n{'='*60}", log_fh)
    _log(f"[{account_index}] Account: {username}", log_fh)
    _log(f"[{account_index}] Opening browser to OAuth login page...", log_fh)
    _log("", log_fh)
    _log("  >> A browser window should appear on your screen <<", log_fh)
    _log("  >> Log into your Microsoft account in that window <<", log_fh)
    _log("  >> After login, the page will redirect <<", log_fh)
    _log("  >> Copy the FINAL address bar URL and paste it here <<", log_fh)
    _log("", log_fh)
    _log("  (Type 'skip' to skip, 'abort' to stop all)", log_fh)
    _log("", log_fh)

    # Try to open the browser via Playwright first
    oauth_url = build_oauth_url()
    browser_opened = False

    try:
        from playwright.sync_api import sync_playwright, Error as PwError
        from .useragent import CHROME_UA

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=CHROME_UA)
            page = context.new_page()
            page.goto(oauth_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            browser_opened = True
            _log(f"[{account_index}] Browser is open. Waiting for you to complete login...", log_fh)

            # Wait for redirect from login.live.com to oauth20_desktop.srf
            redirect_detected = False
            redirect_url = ""

            # Poll for redirect (max 5 min)
            deadline = time.time() + 300
            while time.time() < deadline:
                try:
                    current_url = page.url
                    if "oauth20_desktop.srf" in current_url:
                        redirect_detected = True
                        redirect_url = current_url
                        _log(f"[{account_index}] Redirect detected!", log_fh)
                        break
                    if "_c_Auth" in current_url or "copilot.microsoft.com" in current_url and "access_token" in current_url:
                        redirect_detected = True
                        redirect_url = current_url
                        break
                except Exception:
                    pass

                # Also check if page content contains the token
                try:
                    body = page.content()
                    for m in re.finditer(r'access_token=([^&\s"<>]+)', body):
                        redirect_detected = True
                        redirect_url = current_url
                        break
                except Exception:
                    pass

                if redirect_detected:
                    break

                try:
                    page.wait_for_timeout(1000)
                except Exception:
                    break

            browser.close()

            if redirect_detected and redirect_url:
                _log(f"[{account_index}] Redirect URL captured.", log_fh)
                access_token = extract_token_from_url(redirect_url)
                if access_token:
                    _log(f"[{account_index}] Token extracted! ({access_token[:30]}...)", log_fh)
                    # Capture cookies via headless Playwright
                    _log(f"[{account_index}] Capturing cookies...", log_fh)
                    cookies = _capture_cookies()
                    auth = {
                        "cookies": cookies,
                        "access_token": access_token,
                        "identity_type": "microsoft",
                        "saved_at": time.time(),
                    }
                    Path(token_path).write_text(json.dumps(auth, indent=2), encoding="utf-8")
                    _log(f"[{account_index}] SUCCESS: Credentials saved to {token_path}", log_fh)
                    return True
                else:
                    _log(f"[{account_index}] Token not found in URL: {redirect_url[:100]}", log_fh)
            else:
                _log(f"[{account_index}] No redirect detected within timeout.", log_fh)

    except Exception as e:
        _log(f"[{account_index}] Browser error: {e}", log_fh)

    # Fallback: manual URL paste
    if not browser_opened:
        _log(f"[{account_index}] Could not open browser. Please open this URL manually:", log_fh)
        _log(f"  {oauth_url}", log_fh)
        _log("", log_fh)

    _log(f"[{account_index}] Paste the redirect URL (or 'skip'/'abort'):", log_fh)
    print("  > ", end="", flush=True)
    user_input = sys.stdin.readline().strip()

    if user_input.lower() in ("skip", "abort"):
        if user_input.lower() == "abort":
            raise KeyboardInterrupt()
        return False

    access_token = extract_token_from_url(user_input)
    if not access_token:
        _log(f"[{account_index}] Could not extract token from input.", log_fh)
        return False

    _log(f"[{account_index}] Token extracted! ({access_token[:30]}...)", log_fh)
    cookies = _capture_cookies()
    auth = {
        "cookies": cookies,
        "access_token": access_token,
        "identity_type": "microsoft",
        "saved_at": time.time(),
    }
    Path(token_path).write_text(json.dumps(auth, indent=2), encoding="utf-8")
    _log(f"[{account_index}] SUCCESS: Credentials saved to {token_path}", log_fh)
    return True


def _capture_cookies() -> dict:
    """Headlessly visit copilot.microsoft.com to get basic cookies."""
    try:
        from playwright.sync_api import sync_playwright
        from .useragent import CHROME_UA
        cookies = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=CHROME_UA)
            page = context.new_page()
            page.goto("https://copilot.microsoft.com", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            for c in context.cookies():
                cookies[c["name"]] = c["value"]
            browser.close()
        return cookies
    except Exception:
        return {}


total = 0


def login_from_file(file_path: str) -> int:
    """Read account file and login each account sequentially."""
    global total

    log_path = Path(SESSION_DIR) / "batch_login.log"
    os.makedirs(SESSION_DIR, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as log_fh:
        _log(f"=== Batch login started: {file_path} ===", log_fh)

        if not os.path.exists(file_path):
            _log(f"ERROR: File not found: {file_path}", log_fh)
            return 0

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        accounts = []
        for line in lines:
            line = line.strip()
            if not line or "----" not in line:
                continue
            username = line.split("----")[0].strip()
            accounts.append(username)

        if not accounts:
            _log("No valid accounts found.", log_fh)
            return 0

        total = len(accounts)
        _log(f"Found {total} accounts.", log_fh)
        _log("For each account:", log_fh)
        _log("  1. Browser opens to Microsoft login page", log_fh)
        _log("  2. Log into your account in that browser", log_fh)
        _log("  3. After redirect, paste the address bar URL back here", log_fh)
        _log("", log_fh)

        success_count = 0
        fail_count = 0

        for idx, username in enumerate(accounts, 1):
            try:
                ok = login_one(username, idx, log_fh=log_fh)
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
            except KeyboardInterrupt:
                _log("\n\nBatch login interrupted.", log_fh)
                break

        _log(f"\n{'='*60}", log_fh)
        _log(f"=== BATCH LOGIN COMPLETE ===", log_fh)
        _log(f"Total: {success_count + fail_count}  |  Success: {success_count}  |  Failed: {fail_count}", log_fh)
        _log(f"Credentials: {SESSION_DIR}/account_*/", log_fh)

    return success_count
