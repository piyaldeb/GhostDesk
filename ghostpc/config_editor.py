#!/usr/bin/env python3
"""
ghostdesk-config — open ~/.ghostdesk/.env in the system text editor.
Run: ghostdesk-config
"""

import os
import subprocess
import sys
from pathlib import Path

ENV_PATH = Path.home() / ".ghostdesk" / ".env"


def main():
    # Create .env with defaults if it doesn't exist yet
    if not ENV_PATH.exists():
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        ENV_PATH.write_text(
            "# GhostDesk configuration\n"
            "# Fill in the values below, then restart ghostdesk.\n\n"
            "TELEGRAM_BOT_TOKEN=\n"
            "TELEGRAM_CHAT_ID=\n"
            "TELEGRAM_API_BASE=\n\n"
            "AI_PROVIDER=claude\n"
            "CLAUDE_API_KEY=\n"
            "OPENAI_API_KEY=\n"
            "AI_MODEL=claude-sonnet-4-6\n\n"
            "WHATSAPP_ENABLED=false\n"
            "WHATSAPP_ACCESS_TOKEN=\n"
            "WHATSAPP_PHONE_ID=\n"
            "WHATSAPP_VERIFY_TOKEN=ghostdesk\n\n"
            "EMAIL_ADDRESS=\n"
            "EMAIL_PASSWORD=\n"
            "EMAIL_IMAP=imap.gmail.com\n"
            "EMAIL_SMTP=smtp.gmail.com\n\n"
            "SCREEN_WATCHER_ENABLED=false\n"
            "SCREEN_WATCHER_INTERVAL=30\n\n"
            "AUTO_RESPOND_ENABLED=false\n"
            "AUTO_RESPOND_MODE=suggest\n"
            "AUTO_RESPOND_WHATSAPP=false\n"
            "AUTO_RESPOND_EMAIL=false\n"
            "AUTO_RESPOND_TELEGRAM=false\n\n"
            "VOICE_TRANSCRIPTION_ENABLED=true\n"
            "VOICE_REPLY_ENABLED=false\n\n"
            "PERSONALITY_CLONE_ENABLED=true\n"
            "AUTONOMOUS_MODE_ENABLED=true\n",
            encoding="utf-8",
        )
        print(f"Created new .env at {ENV_PATH}")

    print(f"Opening {ENV_PATH} ...")

    try:
        if sys.platform == "win32":
            os.startfile(str(ENV_PATH))          # opens in default .env / text editor
        elif sys.platform == "darwin":
            subprocess.run(["open", "-t", str(ENV_PATH)])
        else:
            editor = os.environ.get("EDITOR", "nano")
            subprocess.run([editor, str(ENV_PATH)])
    except Exception as e:
        print(f"Could not open editor automatically: {e}")
        print(f"Manually open: {ENV_PATH}")


if __name__ == "__main__":
    main()
