"""Batch multi-account login using OAuth URL with default browser.

Opens the OAuth URL in the user's DEFAULT browser (not Playwright).
User logs into Microsoft there, then pastes the redirect URL back.

Usage:
    python -m copilot login accounts.txt
"""

import json
import os
import re
import sys
import time
import urllib.parse
import webbrowser
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
        "prompt": "login",  # Forces the login screen to appear (ignores SSO)
    }
    return "https://login.live.com/oauth20_authorize.srf?" + urllib.parse.urlencode(params)


def extract_token_from_url(url: str) -> str:
    m = re.search(r"access_token=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.search(r"[?&]code=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    return ""


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


def login_one(username: str, account_index: int, log_fh=None) -> bool:
    """Login one account via OAuth using a clean, visible Playwright browser.
    Auto-captures the redirect URL."""
    session_dir = f"{SESSION_DIR}/account_{account_index}"
    token_path = f"{session_dir}/token.json"
    os.makedirs(session_dir, exist_ok=True)

    _log(f"\n{'='*60}", log_fh)
    _log(f"[{account_index}] Account: {username}", log_fh)
    _log("", log_fh)

    oauth_url = build_oauth_url()

    _log("#" * 60, log_fh)
    _log("  Step 1: A CLEAN browser window will open.", log_fh)
    _log("  Step 2: Please manually copy/paste the account and password.", log_fh)
    _log("  Step 3: Solve any CAPTCHAs.", log_fh)
    _log("  Step 4: The window will auto-close when successful!", log_fh)
    _log("#" * 60, log_fh)
    _log("", log_fh)

    access_token = ""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            
            _log(f"[{account_index}] Opening login page...", log_fh)
            page.goto(oauth_url)
            
            _log(f"[{account_index}] Waiting for you to log in. Window will auto-close upon success.", log_fh)
            
            # Poll for the redirect URL
            deadline = time.time() + 300
            while time.time() < deadline:
                try:
                    current_url = page.url
                    if "oauth20_desktop.srf" in current_url:
                        _log(f"[{account_index}] Redirect detected!", log_fh)
                        access_token = extract_token_from_url(current_url)
                        break
                    
                    if page.is_closed():
                        _log(f"[{account_index}] Browser closed manually.", log_fh)
                        break
                        
                    page.wait_for_timeout(1000)
                except Exception:
                    break
            
            browser.close()
    except Exception as e:
        _log(f"[{account_index}] Playwright error: {e}", log_fh)
        
    if not access_token:
        # Fallback to manual paste if auto-capture failed
        _log(f"[{account_index}] Could not auto-capture. If you see the warning page, paste the URL here:", log_fh)
        try:
            user_input = input("  Paste redirect URL (or 'skip')> ").strip()
            if user_input.lower() == "skip":
                return False
            access_token = extract_token_from_url(user_input)
        except Exception:
            return False

    if not access_token:
        _log(f"[{account_index}] No token obtained.", log_fh)
        return False

    _log(f"[{account_index}] Token extracted! ({access_token[:30]}...)", log_fh)

    # Capture cookies headlessly
    _log(f"[{account_index}] Capturing cookies via headless browser...", log_fh)
    cookies = _capture_cookies()
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
        _log("", log_fh)
        _log("=" * 60, log_fh)
        _log("  LOGIN INSTRUCTIONS", log_fh)
        _log("=" * 60, log_fh)
        _log("  For each account:", log_fh)
        _log("    1. A browser tab opens to Microsoft login", log_fh)
        _log("    2. Log into that Microsoft account", log_fh)
        _log("    3. After redirect, copy the address bar URL", log_fh)
        _log("    4. Paste it here and press Enter", log_fh)
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
