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
            import time
            from playwright.sync_api import Error as PlaywrightError

            bot = BrowserCopilot(headless=False, proxy=proxy)
            
            # Manually control the login flow so we can warmup before closing browser.
            try:
                bot.close()
                bot.start(headless=False)
                bot._install_ws_listener()
                print("\nA browser window is open at copilot.microsoft.com.\n"
                      "Sign in, then WAIT — the token will be captured automatically.\n"
                      "Press Enter once you're signed in (or if already signed in).\n")
                input()
                
                print("[login] Sending warmup to mint chat token...")
                if bot._send_warmup("Hi"):
                    deadline = time.time() + 90
                    while time.time() < deadline:
                        tok = bot.access_token()
                        if tok:
                            print("[login] Token captured! Exporting full auth...")
                            token_path = "session/token.json"
                            bot.export_auth(path=token_path, stamp=time.time())
                            print("[login] Full auth (cookies + token) saved.")
                            break
                        try:
                            bot._page.wait_for_timeout(1000)
                        except PlaywrightError:
                            break
                
                if not bot.access_token():
                    print("[login] WARNING: Token not captured. Trying export anyway...")
                    token_path = "session/token.json"
                    bot.export_auth(path=token_path, stamp=time.time())
                    print("[login] Session saved. Try restarting the API service.")
            finally:
                bot.close()
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
