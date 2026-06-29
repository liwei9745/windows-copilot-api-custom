"""Batch multi-account login using OAuth URL flow.

Usage:
    python -m copilot login accounts.txt
    python -m copilot login accounts.txt --oauth

For each account, prints an OAuth URL. Open it in your own browser
(where you're already signed into Microsoft), complete auth, then
paste the redirect URL back into this terminal.
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
    """Build the OAuth authorize URL for implicit grant flow."""
    params = {
        "client_id": CLIENT_ID,
        "response_type": "token",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    }
    return "https://login.live.com/oauth20_authorize.srf?" + urllib.parse.urlencode(params)


def extract_token_from_url(url: str) -> str:
    """Extract access_token from a redirect URL fragment (#access_token=...)."""
    # Try fragment first (implicit grant)
    m = re.search(r"access_token=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    # Try query param (auth code flow)
    m = re.search(r"[?&]code=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    # Maybe the whole thing is a token
    if url.startswith("Ew") or url.startswith("eyJ"):
        return url
    return ""


def _capture_cookies_via_playwright() -> dict:
    """Visit copilot.microsoft.com headlessly to get basic cookies."""
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


def login_one_oauth(username: str, account_index: int, log_fh=None) -> bool:
    """Login one account via OAuth URL.

    1. Prints OAuth URL
    2. User opens URL in browser, completes auth
    3. User pastes resulting URL back here
    4. Extracts token, captures cookies, saves
    """
    session_dir = f"{SESSION_DIR}/account_{account_index}"
    token_path = f"{session_dir}/token.json"
    os.makedirs(session_dir, exist_ok=True)

    _log(f"\n{'='*60}", log_fh)
    _log(f"[{account_index}] Account: {username}", log_fh)
    _log("", log_fh)

    url = build_oauth_url()
    _log("#" * 60, log_fh)
    _log("  Step 1: Open this URL in your browser (where you're already", log_fh)
    _log("          signed into Microsoft):", log_fh)
    _log("", log_fh)
    _log(f"  {url}", log_fh)
    _log("", log_fh)
    _log("  Step 2: Complete authentication in the browser", log_fh)
    _log("  Step 3: After redirect, copy the ENTIRE address bar URL", log_fh)
    _log("  Step 4: Paste it here and press Enter", log_fh)
    _log("", log_fh)
    _log("  (Type 'skip' to skip this account, or 'abort' to stop)", log_fh)
    _log("#" * 60, log_fh)
    _log("", log_fh)

    print("  Paste redirect URL> ", end="", flush=True)
    user_input = sys.stdin.readline().strip()

    if user_input.lower() == "skip":
        _log(f"[{account_index}] Skipped.", log_fh)
        return False
    if user_input.lower() == "abort":
        _log(f"[{account_index}] Aborted by user.", log_fh)
        raise KeyboardInterrupt()

    access_token = extract_token_from_url(user_input)
    if not access_token:
        _log(f"[{account_index}] Could not extract access_token from input.", log_fh)
        _log(f"  Received: {user_input[:100]}...", log_fh)
        return False

    _log(f"[{account_index}] Token extracted! (starts with: {access_token[:30]}...)", log_fh)
    _log(f"[{account_index}] Capturing cookies via headless browser...", log_fh)

    cookies = _capture_cookies_via_playwright()
    _log(f"[{account_index}] Got {len(cookies)} cookies.", log_fh)

    auth = {
        "cookies": cookies,
        "access_token": access_token,
        "identity_type": "microsoft",
        "saved_at": time.time(),
    }
    Path(token_path).write_text(json.dumps(auth, indent=2), encoding="utf-8")
    _log(f"[{account_index}] SUCCESS: Credentials saved to {token_path}", log_fh)
    return True


total = 0


def login_from_file(file_path: str) -> int:
    """Read account file and login each account sequentially via OAuth."""
    global total

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
        _log("", log_fh)
        _log("=" * 60, log_fh)
        _log("  Using OAuth URL login flow.", log_fh)
        _log("  For EACH account:", log_fh)
        _log("    1. Open the URL in your browser", log_fh)
        _log("    2. Complete Microsoft authentication", log_fh)
        _log("    3. Paste the redirect URL back here", log_fh)
        _log("=" * 60, log_fh)
        _log("", log_fh)

        success_count = 0
        fail_count = 0

        for idx, username in enumerate(accounts, 1):
            try:
                ok = login_one_oauth(username, idx, log_fh=log_fh)
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
