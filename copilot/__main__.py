"""Command-line entry point.

    python -m copilot login        # interactive sign-in, persists the session
    python -m copilot ask "hi"     # one-shot completion via the pure-HTTP driver
"""

import sys


def main(argv) -> int:
    cmd = argv[0] if argv else "ask"
    if cmd == "login":
        # The browser is used only for interactive sign-in / token capture.
        from .browser import BrowserCopilot
        import os

        # Check if an account list file is provided for batch pool login
        account_file = argv[1] if len(argv) > 1 else None
        if account_file and os.path.exists(account_file):
            print(f"[pool] Found account file: {account_file}. Starting batch login...")
            with open(account_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            count = 0
            for line in lines:
                line = line.strip()
                if not line or "----" not in line:
                    continue
                parts = line.split("----")
                if len(parts) >= 2:
                    username = parts[0].strip()
                    password = parts[1].strip()
                    count += 1
                    print(f"\n[pool] [{count}] Logging in for: {username} ...")
                    session_dir = f"session/account_{count}"
                    token_path = f"{session_dir}/token.json"
                    try:
                        bot = BrowserCopilot(profile_dir=f"{session_dir}/profile", headless=False)
                        bot.login(path=token_path, username=username, password=password)
                        print(f"[pool] [{count}] Successfully logged in and saved credentials.")
                    except Exception as e:
                        print(f"[pool] [{count}] Failed to login for {username}: {e}")
            print(f"\n[pool] Batch login complete. Loaded {count} accounts in total.")
            return 0
        else:
            BrowserCopilot(headless=False).login()
            return 0
    if cmd == "ask":
        prompt = " ".join(argv[1:]) or "Hello!"
        from .client import CopilotClient

        for chunk in CopilotClient().stream(prompt):
            if isinstance(chunk, str):
                print(chunk, end="", flush=True)
        print()
        return 0
    print(f"Unknown command: {cmd!r}. Use 'login' or 'ask <prompt>'.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
