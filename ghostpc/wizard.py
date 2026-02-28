#!/usr/bin/env python3
"""
GhostPC First-Time Setup Wizard
Run: ghostdesk-setup
"""

import os
import sys
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Save .env to ~/.ghostdesk/ so it works whether installed via pip or cloned
USER_DATA_DIR = Path.home() / ".ghostdesk"
USER_DATA_DIR.mkdir(exist_ok=True)
ENV_PATH = USER_DATA_DIR / ".env"


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


def setup_auto_response(config: dict) -> dict:
    print("\n─── Step 5: Auto-Response (Optional) ──────────────────")
    print("  When someone messages you, GhostDesk reads recent history,")
    print("  drafts a reply using AI, and sends it to you for approval.")
    enable = ask("  Enable auto-response? (y/n)", default="n")

    if enable.lower() != "y":
        config["AUTO_RESPOND_ENABLED"] = False
        return config

    config["AUTO_RESPOND_ENABLED"] = True

    # Mode
    print("\n  Mode:")
    print("  1. Suggest (default) — sends draft to Telegram, you approve/edit/skip")
    print("  2. Auto — sends reply automatically without approval")
    mode = ask("  Mode [1/2]", default="1")
    config["AUTO_RESPOND_MODE"] = "auto" if mode == "2" else "suggest"

    # Platforms
    if config.get("WHATSAPP_ENABLED"):
        wa = ask("  Auto-respond to WhatsApp messages? (y/n)", default="y")
        config["AUTO_RESPOND_WHATSAPP"] = wa.lower() == "y"

    if config.get("EMAIL_ADDRESS"):
        em = ask("  Auto-respond to emails? (y/n)", default="y")
        config["AUTO_RESPOND_EMAIL"] = em.lower() == "y"
        if em.lower() == "y":
            interval = ask("  Email check interval in seconds", default="300")
            config["EMAIL_POLL_INTERVAL"] = interval

    tg = ask("  Auto-respond to personal Telegram DMs? (y/n)", default="n")
    if tg.lower() == "y":
        config["AUTO_RESPOND_TELEGRAM"] = True
        print("\n  For Telegram DMs you need API credentials from https://my.telegram.org")
        config["TELEGRAM_API_ID"]   = ask("  API ID")
        config["TELEGRAM_API_HASH"] = ask("  API Hash", secret=True)
    else:
        config["AUTO_RESPOND_TELEGRAM"] = False

    # Context days
    days = ask("  Days of history to read per contact", default="2")
    config["AUTO_RESPOND_CONTEXT_DAYS"] = days

    # Whitelist
    whitelist = ask("  Only respond to these contacts (comma-separated, leave blank = all)", default="")
    config["AUTO_RESPOND_WHITELIST"] = whitelist

    return config


def setup_voice(config: dict) -> dict:
    print("\n─── Step 6: Voice Module (Optional) ────────────────────")
    print("  Send voice notes to GhostDesk — they're transcribed via OpenAI Whisper")
    print("  and executed as commands. Requires OPENAI_API_KEY (even if using Claude).")
    enable = ask("  Enable voice transcription? (y/n)", default="y")
    config["VOICE_TRANSCRIPTION_ENABLED"] = enable.lower() == "y"
    if enable.lower() == "y":
        reply = ask("  Also reply back as voice notes? (y/n)", default="n")
        config["VOICE_REPLY_ENABLED"] = reply.lower() == "y"
    else:
        config["VOICE_REPLY_ENABLED"] = False
    return config


def setup_screen_watcher(config: dict) -> dict:
    print("\n─── Step 7: Screen Watcher (Optional) ──────────────────")
    print("  GhostDesk watches your screen every N seconds for errors, crashes,")
    print("  security alerts, and unusual activity. Alerts arrive instantly on Telegram.")
    enable = ask("  Enable screen watcher? (y/n)", default="n")
    config["SCREEN_WATCHER_ENABLED"] = enable.lower() == "y"
    if enable.lower() == "y":
        interval = ask("  Screenshot interval in seconds (30 = every 30s)", default="30")
        config["SCREEN_WATCHER_INTERVAL"] = interval
    else:
        config["SCREEN_WATCHER_INTERVAL"] = "30"
    return config


def setup_advanced(config: dict) -> dict:
    print("\n─── Step 8: Advanced AI Features ───────────────────────")
    print("\n  Personality Clone + Ghost Mode:")
    print("  GhostDesk analyzes your message history and can reply to contacts")
    print("  sounding exactly like you. Ghost Mode auto-replies for a set duration.")
    pc = ask("  Enable personality clone / ghost mode? (y/n)", default="y")
    config["PERSONALITY_CLONE_ENABLED"] = pc.lower() == "y"

    print("\n  Autonomous Mode:")
    print("  Say 'autonomously: [complex goal]' and GhostDesk plans and executes")
    print("  multi-step tasks on its own, reporting progress step by step.")
    am = ask("  Enable autonomous mode? (y/n)", default="y")
    config["AUTONOMOUS_MODE_ENABLED"] = am.lower() == "y"
    return config


def write_env_file(config: dict):
    """Write config to .env file."""
    lines = [
        "# GhostDesk Environment Variables",
        "# Generated by ghostdesk-setup — keep this file private!\n",
    ]

    def b(val):
        return "true" if val else "false"

    key_map = {
        "TELEGRAM_BOT_TOKEN":       config.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID":         config.get("TELEGRAM_CHAT_ID", ""),
        "AI_PROVIDER":              config.get("AI_PROVIDER", "claude"),
        "CLAUDE_API_KEY":           config.get("CLAUDE_API_KEY", ""),
        "OPENAI_API_KEY":           config.get("OPENAI_API_KEY", ""),
        "AI_MODEL":                 config.get("AI_MODEL", "claude-opus-4-5"),
        "WHATSAPP_ENABLED":         b(config.get("WHATSAPP_ENABLED")),
        "EMAIL_IMAP":               config.get("EMAIL_IMAP", ""),
        "EMAIL_SMTP":               config.get("EMAIL_SMTP", ""),
        "EMAIL_ADDRESS":            config.get("EMAIL_ADDRESS", ""),
        "EMAIL_PASSWORD":           config.get("EMAIL_PASSWORD", ""),
        "AGENT_NAME":               "GhostPC",
        "MEMORY_ENABLED":           "true",
        "MAX_FILE_SEND_MB":         "50",
        "SCREENSHOT_INTERVAL":      "0",
        # Auto-response
        "AUTO_RESPOND_ENABLED":     b(config.get("AUTO_RESPOND_ENABLED")),
        "AUTO_RESPOND_MODE":        config.get("AUTO_RESPOND_MODE", "suggest"),
        "AUTO_RESPOND_WHATSAPP":    b(config.get("AUTO_RESPOND_WHATSAPP")),
        "AUTO_RESPOND_EMAIL":       b(config.get("AUTO_RESPOND_EMAIL")),
        "AUTO_RESPOND_TELEGRAM":    b(config.get("AUTO_RESPOND_TELEGRAM")),
        "AUTO_RESPOND_CONTEXT_DAYS": str(config.get("AUTO_RESPOND_CONTEXT_DAYS", "2")),
        "AUTO_RESPOND_WHITELIST":   config.get("AUTO_RESPOND_WHITELIST", ""),
        "EMAIL_POLL_INTERVAL":      str(config.get("EMAIL_POLL_INTERVAL", "300")),
        "TELEGRAM_API_ID":          str(config.get("TELEGRAM_API_ID", "")),
        "TELEGRAM_API_HASH":        config.get("TELEGRAM_API_HASH", ""),
        # Voice
        "VOICE_TRANSCRIPTION_ENABLED": b(config.get("VOICE_TRANSCRIPTION_ENABLED", True)),
        "VOICE_REPLY_ENABLED":         b(config.get("VOICE_REPLY_ENABLED", False)),
        # Screen Watcher
        "SCREEN_WATCHER_ENABLED":      b(config.get("SCREEN_WATCHER_ENABLED", False)),
        "SCREEN_WATCHER_INTERVAL":     str(config.get("SCREEN_WATCHER_INTERVAL", "30")),
        # Advanced
        "PERSONALITY_CLONE_ENABLED":   b(config.get("PERSONALITY_CLONE_ENABLED", True)),
        "AUTONOMOUS_MODE_ENABLED":     b(config.get("AUTONOMOUS_MODE_ENABLED", True)),
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
        config = setup_auto_response(config)
        config = setup_voice(config)
        config = setup_screen_watcher(config)
        config = setup_advanced(config)

        print("\n─── Saving Configuration ───────────────────────────────")
        write_env_file(config)

        print("""
╔═══════════════════════════════════════════════════╗
║              ✅ Setup Complete!                   ║
║                                                   ║
║   Run: ghostdesk                                  ║
║   Your ghost is ready to haunt the PC.            ║
╚═══════════════════════════════════════════════════╝
""")

    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
