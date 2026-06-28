"""Batch multi-account login with real-time logging and verification code support.

Usage:
    python -m copilot login accounts.txt
    
This opens a browser for each account, auto-fills credentials, handles
verification codes, and saves session data to session/account_X/.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .auth import DEFAULT_AUTH_FILE, DEFAULT_PROFILE_DIR, SESSION_DIR
from .browser import BrowserCopilot


def _ts(msg: str) -> str:
    return f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"


def _log(msg: str, log_fh=None):
    line = _ts(msg)
    print(line, flush=True)
    if log_fh:
        log_fh.write(line + "\n")
        log_fh.flush()


def _handle_verification_if_needed(bot, log_fh=None) -> bool:
    """Check if a verification code input is showing, and if so prompt user.

    Returns True if verification was handled successfully, False if not needed.
    """
    page = bot._page
    if page is None:
        return False

    # Microsoft verification code selectors
    code_selectors = [
        'input[name="otc"]',
        'input[name="otp"]',
        'input[autocomplete="one-time-code"]',
        'input#iOttText',
    ]

    for sel in code_selectors:
        try:
            el = page.wait_for_selector(sel, timeout=3000)
            if el and el.is_visible():
                _log("Verification code required. Please check your email (or authenticator app).", log_fh)
                _log("Enter the code (or type 'skip' to skip this account):", log_fh)
                code = input()

                if code.strip().lower() == "skip":
                    _log("Skipping this account as requested.", log_fh)
                    return False
                if code.strip():
                    el.fill(code.strip())
                    page.wait_for_timeout(500)
                    # Click Verify / Next button
                    submit_sel = 'input[type="submit"], button:has-text("Verify"), button:has-text("Next")'
                    try:
                        page.click(submit_sel, timeout=5000)
                    except Exception:
                        page.keyboard.press("Enter")
                    _log("Verification code submitted.", log_fh)
                    return True
        except Exception:
            continue
    return False


def login_one(
    username: str,
    password: str,
    account_index: int,
    timeout: int = 300,
    log_fh=None,
) -> bool:
    """Login one account, save credentials to session/account_{index}/.

    Returns True if login succeeded, False otherwise.
    """
    session_dir = f"{SESSION_DIR}/account_{account_index}"
    os.makedirs(session_dir, exist_ok=True)
    profile_dir = f"{session_dir}/profile"
    token_path = f"{session_dir}/token.json"

    _log(f"[{account_index}] === Starting login for: {username} ===", log_fh)

    bot = BrowserCopilot(profile_dir=profile_dir, headless=False)

    try:
        bot.start(headless=False)
        bot._install_ws_listener()
    except Exception as e:
        _log(f"[{account_index}] Failed to start browser: {e}", log_fh)
        return False

    log = bot._open_login_log(Path(token_path).resolve().parent / "batch_login.log")
    log(f"batch login started for {username}")

    _log(f"[{account_index}] Browser opened. Auto-filling credentials...", log_fh)

    # ====== Auto-fill username ======
    try:
        bot._page.wait_for_selector('input[name="loginfmt"]', timeout=30000)
        bot._page.fill('input[name="loginfmt"]', username)
        bot._page.wait_for_timeout(500)
        bot._page.click('input[type="submit"], #idSIButton9')
        log(f"username filled for {username}")
        _log(f"[{account_index}] Username filled.", log_fh)
    except Exception as e:
        log(f"username field not found or fill failed: {e}")
        _log(f"[{account_index}] Could not find username field. Might already be signed in.", log_fh)

    # ====== Auto-fill password ======
    try:
        bot._page.wait_for_selector('input[name="passwd"]', timeout=15000)
        bot._page.wait_for_timeout(500)
        bot._page.fill('input[name="passwd"]', password)
        bot._page.wait_for_timeout(500)
        bot._page.click('input[type="submit"], #idSIButton9')
        log(f"password filled for {username}")
        _log(f"[{account_index}] Password filled and submitted.", log_fh)
    except Exception as e:
        log(f"password field not found or fill failed: {e}")
        _log(f"[{account_index}] Could not find password field.", log_fh)

    # ====== Handle "Stay signed in?" prompt ======
    try:
        bot._page.wait_for_selector('input[name="DontShowAgain"]', timeout=8000)
        bot._page.wait_for_timeout(300)
        bot._page.click('input[type="submit"], #idSIButton9')
        log("'Stay signed in' prompt handled")
        _log(f"[{account_index}] 'Stay signed in' prompt accepted.", log_fh)
    except Exception:
        pass

    # ====== Handle verification code if needed ======
    _handle_verification_if_needed(bot, log_fh)

    # ====== Wait for sign-in detection ======
    _log(f"[{account_index}] Waiting for sign-in detection (up to {timeout}s)...", log_fh)
    deadline = time.time() + timeout
    detected = False

    while time.time() < deadline:
        if bot._window_closed():
            log("browser window closed before sign-in was detected")
            _log(f"[{account_index}] Browser window closed unexpectedly.", log_fh)
            break
        if bot.signed_in():
            log("sign-in detected")
            _log(f"[{account_index}] Sign-in detected!", log_fh)
            detected = True
            break
        # Check if verification code prompt appeared (in case it showed up later)
        if _handle_verification_if_needed(bot, log_fh):
            continue
        try:
            bot._page.wait_for_timeout(2000)
        except Exception:
            break

    if not detected:
        _log(f"[{account_index}] Sign-in NOT detected within {timeout}s.", log_fh)
        bot.close()
        return False

    # ====== Warm-up and capture token ======
    _log(f"[{account_index}] Sign-in complete. Warming up to capture token...", log_fh)
    token = None
    try:
        token = bot.access_token()
        # If sign-in detected but no token yet, try warmup
        if not token:
            _log(f"[{account_index}] No cached token found. Sending warm-up message...", log_fh)
            bot._warmup_replied = False
            if bot._send_warmup():
                # Wait for warm-up to complete
                for _ in range(30):
                    token = bot.access_token()
                    if token or bot._warmup_replied:
                        break
                    bot._page.wait_for_timeout(2000)
    except Exception as e:
        log(f"warm-up error: {e}")
        _log(f"[{account_index}] Warm-up failed: {e}", log_fh)

    if not token:
        _log(f"[{account_index}] Could not capture access token.", log_fh)
        bot.close()
        return False

    # ====== Export auth snapshot ======
    try:
        auth = bot.export_auth(path=token_path, stamp=time.time())
        if auth.get("access_token"):
            _log(f"[{account_index}] Credentials saved to {session_dir}/token.json", log_fh)
            bot.close()
            return True
        else:
            _log(f"[{account_index}] Auth snapshot saved but no access_token found.", log_fh)
            bot.close()
            return False
    except Exception as e:
        _log(f"[{account_index}] Failed to save credentials: {e}", log_fh)
        bot.close()
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
            parts = line.split("----", 1)
            if len(parts) >= 2:
                username = parts[0].strip()
                password = parts[1].strip()
                accounts.append((username, password))

        if not accounts:
            _log("No valid accounts found in the file.", log_fh)
            _log("Expected format: email----password (one per line)", log_fh)
            return 0

        _log(f"Found {len(accounts)} accounts to process.", log_fh)
        _log("NOTE: A browser window will open for EACH account.", log_fh)
        _log("      If a verification code is required, check your email.", log_fh)
        _log("      Press Ctrl+C at any time to abort.", log_fh)

        success_count = 0
        fail_count = 0

        for idx, (username, password) in enumerate(accounts, 1):
            _log(f"\n{'='*60}", log_fh)
            _log(f"Account {idx}/{len(accounts)}", log_fh)
            _log(f"Email: {username}", log_fh)

            try:
                ok = login_one(username, password, idx, log_fh=log_fh)
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

        # ====== Summary ======
        _log(f"\n{'='*60}", log_fh)
        _log(f"=== BATCH LOGIN COMPLETE ===", log_fh)
        _log(f"Total accounts processed: {success_count + fail_count}", log_fh)
        _log(f"Successful: {success_count}", log_fh)
        _log(f"Failed: {fail_count}", log_fh)
        _log(f"Credentials saved under: {SESSION_DIR}/account_*/", log_fh)
        _log(f"Full log: {log_path}", log_fh)

    return success_count
