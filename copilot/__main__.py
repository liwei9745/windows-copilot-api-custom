"""Command-line entry point.

    python -m copilot login                    # interactive sign-in
    python -m copilot login accounts.txt       # batch login with logging
    python -m copilot ask "hi"                 # one-shot completion
"""

import sys
import os


def main(argv) -> int:
    cmd = argv[0] if argv else "ask"
    if cmd == "login":
        from .browser import BrowserCopilot
        from urllib.parse import parse_qs, urlparse
        proxy = os.environ.get("ALL_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None
        account_file = argv[1] if len(argv) > 1 else None
        if account_file and os.path.exists(account_file):
            from .batch_login import login_from_file
            count = login_from_file(account_file)
            return 0 if count > 0 else 1
        else:
            import json
            import time
            bot = BrowserCopilot(headless=False, proxy=proxy)
            result = bot.login()
            if not result.get("access_token"):
                # Browser is still open and user is signed in.
                # Google logins prevent signed_in() from detecting, so we
                # manually trigger a chat warmup to mint and capture the token.
                print("[login] Detecting token via warmup turn...")
                bot._install_ws_listener()
                if bot._send_warmup():
                    deadline = time.time() + 90
                    while time.time() < deadline:
                        tok = bot.access_token()
                        if tok:
                            token_path = "session/token.json"
                            data = json.load(open(token_path)) if os.path.exists(token_path) else {}
                            data["access_token"] = tok
                            data["identity_type"] = bot._captured_identity_type or "google"
                            json.dump(data, open(token_path, "w"), indent=2)
                            print("[login] Token captured via warmup!")
                            break
                        try:
                            bot._page.wait_for_timeout(1000)
                        except Exception:
                            break
                if not bot.access_token():
                    print("[login] WARNING: Could not capture token. Please manually click inside the Copilot page and send any message, then wait.")
            return 0
    if cmd == "ask":
        prompt = " ".join(argv[1:]) or "Hello!"
        from .client import CopilotClient
        proxy = os.environ.get("ALL_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None

        for chunk in CopilotClient(proxy=proxy).stream(prompt):
            if isinstance(chunk, str):
                print(chunk, end="", flush=True)
        print()
        return 0
    print(f"Unknown command: {cmd!r}. Use 'login' or 'ask <prompt>'.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
