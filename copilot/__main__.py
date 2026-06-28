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
        account_file = argv[1] if len(argv) > 1 else None
        if account_file and os.path.exists(account_file):
            from .batch_login import login_from_file
            count = login_from_file(account_file)
            return 0 if count > 0 else 1
        else:
            from .browser import BrowserCopilot
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
