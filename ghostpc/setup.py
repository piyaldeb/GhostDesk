#!/usr/bin/env python3
"""
GhostPC First-Time Setup Wizard
Run: python setup.py
"""

import os
import sys
import json
import requests
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.py"
ENV_PATH = Path(__file__).parent / ".env"


def print_banner():
    print("""
╔═══════════════════════════════════════════════════╗
║           👻  GhostPC Setup Wizard               ║
║     Your AI-powered Windows remote agent         ║
╚═══════════════════════════════════════════════════╝
""")


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "

    if secret:
        import getpass
        value = getpass.getpass(display)
    else:
        value = input(display).strip()

    return value if value else default


def verify_telegram(token: str) -> tuple[bool, str]:
    """Verify Telegram bot token via API."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10
        )
        data = resp.json()
        if data.get("ok"):
            bot_name = data["result"]["first_name"]
            username = data["result"]["username"]
            return True, f"{bot_name} (@{username})"
        return False, data.get("description", "Unknown error")
    except Exception as e:
        return False, str(e)


def get_telegram_chat_id(token: str) -> str:
    """Get chat ID by asking user to send a message to the bot."""
    print("\n  📱 To get your Chat ID:")
    print("     1. Open Telegram")
    print("     2. Search for your bot and send it: /start")
    print("     3. Then come back here and press Enter")
    input("\n  Press Enter after sending /start to your bot...")

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=10
        )
        data = resp.json()
        if data.get("ok") and data["result"]:
            chat_id = str(data["result"][-1]["message"]["chat"]["id"])
            return chat_id
        print("  ⚠️  No messages found. Make sure you sent /start to the bot.")
        return ask("  Enter your Chat ID manually")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return ask("  Enter your Chat ID manually")


def verify_claude(api_key: str) -> tuple[bool, str]:
    """Verify Claude API key with a minimal test call."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        return True, "Claude API key verified"
    except Exception as e:
        return False, str(e)


def verify_openai(api_key: str) -> tuple[bool, str]:
    """Verify OpenAI API key."""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        client.models.list()
        return True, "OpenAI API key verified"
    except Exception as e:
        return False, str(e)


def setup_telegram(config: dict) -> dict:
    print("\n─── Step 1: Telegram Bot ───────────────────────────────")
    print("  Create a bot via @BotFather on Telegram if you haven't.")

    while True:
        token = ask("  Bot Token", secret=True)
        if not token:
            print("  ❌ Token cannot be empty.")
            continue

        print("  🔍 Verifying token...")
        ok, msg = verify_telegram(token)
        if ok:
            print(f"  ✅ Connected: {msg}")
            config["TELEGRAM_BOT_TOKEN"] = token
            break
        else:
            print(f"  ❌ Invalid token: {msg}")
            retry = ask("  Try again? (y/n)", default="y")
            if retry.lower() != "y":
                sys.exit(1)

    chat_id = get_telegram_chat_id(token)
    if chat_id:
        print(f"  ✅ Chat ID: {chat_id}")
        config["TELEGRAM_CHAT_ID"] = chat_id
    else:
        print("  ⚠️  Could not auto-detect Chat ID. You can set it manually in config.py")

    return config


def setup_ai(config: dict) -> dict:
    print("\n─── Step 2: AI Provider ────────────────────────────────")
    print("  Choose your AI provider:")
    print("  1. Claude (Anthropic) — Recommended")
    print("  2. OpenAI (GPT-4)")

    choice = ask("  Choice [1/2]", default="1")

    if choice == "2":
        config["AI_PROVIDER"] = "openai"
        config["AI_MODEL"] = "gpt-4o"
        while True:
            key = ask("  OpenAI API Key", secret=True)
            print("  🔍 Verifying...")
            ok, msg = verify_openai(key)
            if ok:
                print(f"  ✅ {msg}")
                config["OPENAI_API_KEY"] = key
                break
            else:
                print(f"  ❌ {msg}")
                retry = ask("  Try again? (y/n)", default="y")
                if retry.lower() != "y":
                    break
    else:
        config["AI_PROVIDER"] = "claude"
        config["AI_MODEL"] = "claude-opus-4-5"
        while True:
            key = ask("  Anthropic API Key", secret=True)
            print("  🔍 Verifying...")
            ok, msg = verify_claude(key)
            if ok:
                print(f"  ✅ {msg}")
                config["CLAUDE_API_KEY"] = key
                break
            else:
                print(f"  ❌ {msg}")
                retry = ask("  Try again? (y/n)", default="y")
                if retry.lower() != "y":
                    break

    return config


def setup_whatsapp(config: dict) -> dict:
    print("\n─── Step 3: WhatsApp Mirroring (Optional) ──────────────")
    print("  Requires Node.js and whatsapp-web.js")
    enable = ask("  Enable WhatsApp mirroring? (y/n)", default="n")
    config["WHATSAPP_ENABLED"] = enable.lower() == "y"
    return config


def setup_email(config: dict) -> dict:
    print("\n─── Step 4: Email Integration (Optional) ───────────────")
    enable = ask("  Enable email integration? (y/n)", default="n")

    if enable.lower() == "y":
        config["EMAIL_ADDRESS"] = ask("  Email address")
        config["EMAIL_PASSWORD"] = ask("  Email password / App password", secret=True)
        config["EMAIL_IMAP"] = ask("  IMAP server (e.g. imap.gmail.com)", default="imap.gmail.com")
        config["EMAIL_SMTP"] = ask("  SMTP server (e.g. smtp.gmail.com)", default="smtp.gmail.com")

    return config


def write_env_file(config: dict):
    """Write config to .env file."""
    lines = [
        "# GhostPC Environment Variables",
        "# Generated by setup.py — keep this file private!\n",
    ]

    key_map = {
        "TELEGRAM_BOT_TOKEN": config.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": config.get("TELEGRAM_CHAT_ID", ""),
        "AI_PROVIDER": config.get("AI_PROVIDER", "claude"),
        "CLAUDE_API_KEY": config.get("CLAUDE_API_KEY", ""),
        "OPENAI_API_KEY": config.get("OPENAI_API_KEY", ""),
        "AI_MODEL": config.get("AI_MODEL", "claude-opus-4-5"),
        "WHATSAPP_ENABLED": "true" if config.get("WHATSAPP_ENABLED") else "false",
        "EMAIL_IMAP": config.get("EMAIL_IMAP", ""),
        "EMAIL_SMTP": config.get("EMAIL_SMTP", ""),
        "EMAIL_ADDRESS": config.get("EMAIL_ADDRESS", ""),
        "EMAIL_PASSWORD": config.get("EMAIL_PASSWORD", ""),
        "AGENT_NAME": "GhostPC",
        "MEMORY_ENABLED": "true",
        "MAX_FILE_SEND_MB": "50",
        "SCREENSHOT_INTERVAL": "0",
    }

    for k, v in key_map.items():
        lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(lines))
    print(f"\n  ✅ Config saved to {ENV_PATH}")


def main():
    print_banner()
    print("This wizard will configure GhostPC. Press Ctrl+C to abort at any time.\n")

    config = {}

    try:
        config = setup_telegram(config)
        config = setup_ai(config)
        config = setup_whatsapp(config)
        config = setup_email(config)

        print("\n─── Saving Configuration ───────────────────────────────")
        write_env_file(config)

        print("""
╔═══════════════════════════════════════════════════╗
║              ✅ Setup Complete!                   ║
║                                                   ║
║   Run: python main.py                             ║
║   Your ghost is ready to haunt the PC.            ║
╚═══════════════════════════════════════════════════╝
""")

    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
