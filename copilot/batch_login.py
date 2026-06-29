"""Batch multi-account login for Microsoft Copilot (semi-automated).

Opens a visible browser for each account. User manually signs in.
Script detects success, saves credentials, moves to next account.

Usage:
    python -m copilot login accounts.txt
"""

import json
import os
import sys
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


def login_one(username: str, password: str, account_index: int, log_fh=None) -> bool:
    """Login one account using a visible browser.

    Opens browser → user manually signs in → detects success → saves credentials.
    Returns True if login succeeded.
    """
    session_dir = f"{SESSION_DIR}/account_{account_index}"
    profile_dir = f"{session_dir}/profile"
    token_path = f"{session_dir}/token.json"
    os.makedirs(session_dir, exist_ok=True)

    _log(f"\n{'='*60}", log_fh)
    _log(f"[{account_index}/{total}] Account: {username}", log_fh)
    _log(f"[{account_index}] Opening browser...", log_fh)

    try:
        from .browser import BrowserCopilot

        bot = BrowserCopilot(profile_dir=profile_dir, headless=False)
        result = bot.login(path=token_path, timeout=300)

        if result.get("access_token"):
            _log(f"[{account_index}] SUCCESS: Credentials saved to {token_path}", log_fh)
            return True
        else:
            _log(f"[{account_index}] FAILED: No access_token captured. Sign-in may not have completed.", log_fh)
            return False
    except KeyboardInterrupt:
        raise
    except Exception as e:
        _log(f"[{account_index}] ERROR: {e}", log_fh)
        return False


# Make account_index aware of total (module-level hack for clean logging)
total = 0


def login_from_file(file_path: str) -> int:
    """Read account file and login each account sequentially.

    Returns: number of successfully logged in accounts.
    """
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
            parts = line.split("----")
            username = parts[0].strip()
            password = parts[1].strip()
            accounts.append(username)

        if not accounts:
            _log("No valid accounts found.", log_fh)
            _log("Expected format: email----password----...", log_fh)
            return 0

        total = len(accounts)
        _log(f"Found {total} accounts to process.", log_fh)
        _log("", log_fh)
        _log("=" * 60, log_fh)
        _log("  IMPORTANT: A visible browser will open for EACH account.", log_fh)
        _log("  1. Browser opens to copilot.microsoft.com", log_fh)
        _log("  2. Click 'Sign in' in the browser and log into Microsoft", log_fh)
        _log("  3. Pass any CAPTCHA or 2FA if prompted", log_fh)
        _log("  4. The browser will close itself once sign-in is detected", log_fh)
        _log("  5. Next account browser will open automatically", log_fh)
        _log("=" * 60, log_fh)
        _log("", log_fh)
        _log("Press Ctrl+C at any time to abort batch.", log_fh)
        _log("", log_fh)

        success_count = 0
        fail_count = 0

        for idx, username in enumerate(accounts, 1):
            try:
                ok = login_one(username, "", idx, log_fh=log_fh)
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
            except KeyboardInterrupt:
                _log("\n\nBatch login interrupted by user.", log_fh)
                break
            except Exception as e:
                fail_count += 1
                _log(f"[ERROR] Account {idx} exception: {e}", log_fh)

        _log(f"\n{'='*60}", log_fh)
        _log(f"=== BATCH LOGIN COMPLETE ===", log_fh)
        _log(f"Total: {success_count + fail_count}  |  Success: {success_count}  |  Failed: {fail_count}", log_fh)
        _log(f"Credentials saved under: {SESSION_DIR}/account_*/", log_fh)
        _log(f"Full log: {log_path}", log_fh)

    return success_count
