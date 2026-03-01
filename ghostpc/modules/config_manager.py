"""
GhostDesk Config Manager
Read and write .env configuration values through Telegram chat.
Provides setup guides and suggestions for unconfigured features.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Sensitive keys (masked in display) ──────────────────────────────────────

_SENSITIVE = {
    "TELEGRAM_BOT_TOKEN",
    "CLAUDE_API_KEY",
    "OPENAI_API_KEY",
    "EMAIL_PASSWORD",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_VERIFY_TOKEN",
    "TELEGRAM_API_HASH",
    "TELEGRAM_API_ID",
}

# ─── Config groups (display order + grouping) ────────────────────────────────

_CONFIG_GROUPS = {
    "Core (Required)": [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ],
    "AI Provider": [
        "AI_PROVIDER",
        "CLAUDE_API_KEY",
        "OPENAI_API_KEY",
        "AI_MODEL",
    ],
    "Email": [
        "EMAIL_ADDRESS",
        "EMAIL_PASSWORD",
        "EMAIL_IMAP",
        "EMAIL_SMTP",
        "EMAIL_POLL_INTERVAL",
    ],
    "WhatsApp": [
        "WHATSAPP_ENABLED",
        "WHATSAPP_PHONE_ID",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_VERIFY_TOKEN",
    ],
    "Auto-Response": [
        "AUTO_RESPOND_ENABLED",
        "AUTO_RESPOND_MODE",
        "AUTO_RESPOND_WHATSAPP",
        "AUTO_RESPOND_EMAIL",
        "AUTO_RESPOND_TELEGRAM",
    ],
    "Screen Watcher": [
        "SCREEN_WATCHER_ENABLED",
        "SCREEN_WATCHER_INTERVAL",
    ],
    "Features": [
        "VOICE_TRANSCRIPTION_ENABLED",
        "VOICE_REPLY_ENABLED",
        "PERSONALITY_CLONE_ENABLED",
        "AUTONOMOUS_MODE_ENABLED",
    ],
    "Google Services": [
        "GOOGLE_SHEETS_CREDS_PATH",
    ],
    "Advanced": [
        "TELEGRAM_API_BASE",
        "HTTPS_PROXY",
        "MAX_FILE_SEND_MB",
        "SCREEN_IDLE_SECONDS",
        "PRIORITY_CONTACTS",
    ],
}

# ─── Setup guides ─────────────────────────────────────────────────────────────

_SETUP_GUIDES = {
    "email": (
        "📧 *Email Setup*\n\n"
        "*Step 1 — Gmail (most common):*\n"
        "  Go to: Google Account → Security → 2-Step Verification → App passwords\n"
        "  Create an app password for 'Mail' — copy the 16-char code.\n\n"
        "*Step 2 — Set your values:*\n"
        "  `set EMAIL_ADDRESS to yourmail@gmail.com`\n"
        "  `set EMAIL_PASSWORD to xxxx-xxxx-xxxx-xxxx` _(app password)_\n"
        "  `set EMAIL_IMAP to imap.gmail.com`\n"
        "  `set EMAIL_SMTP to smtp.gmail.com`\n\n"
        "*Other providers:*\n"
        "  Outlook: imap.outlook.com / smtp.office365.com\n"
        "  Yahoo: imap.mail.yahoo.com / smtp.mail.yahoo.com\n\n"
        "*Step 3 — Restart:* say `restart ghostdesk`"
    ),
    "whatsapp": (
        "📱 *WhatsApp Setup (Cloud API)*\n\n"
        "*Step 1 — Create a Meta App:*\n"
        "  Go to: developers.facebook.com → My Apps → Create App\n"
        "  Choose: Business → WhatsApp\n\n"
        "*Step 2 — Copy credentials from API Setup:*\n"
        "  • Phone Number ID\n"
        "  • Permanent Access Token\n\n"
        "*Step 3 — Set values:*\n"
        "  `set WHATSAPP_ENABLED to true`\n"
        "  `set WHATSAPP_PHONE_ID to your-phone-id`\n"
        "  `set WHATSAPP_ACCESS_TOKEN to EAAxx...`\n\n"
        "*Step 4 — Restart:* say `restart ghostdesk`"
    ),
    "claude": (
        "🤖 *Claude (Anthropic) AI Setup*\n\n"
        "*Step 1:* Go to console.anthropic.com\n"
        "*Step 2:* Create account → add payment method\n"
        "*Step 3:* API Keys → Create new key\n\n"
        "*Step 4 — Set values:*\n"
        "  `set AI_PROVIDER to claude`\n"
        "  `set CLAUDE_API_KEY to sk-ant-xxxx`\n"
        "  `set AI_MODEL to claude-sonnet-4-6` _(or claude-opus-4-6)_\n\n"
        "*Step 5 — Restart:* say `restart ghostdesk`"
    ),
    "openai": (
        "🤖 *OpenAI Setup*\n\n"
        "*Step 1:* Go to platform.openai.com\n"
        "*Step 2:* Create account → add credits\n"
        "*Step 3:* API Keys → Create new secret key\n\n"
        "*Step 4 — Set values:*\n"
        "  `set AI_PROVIDER to openai`\n"
        "  `set OPENAI_API_KEY to sk-xxxx`\n"
        "  `set AI_MODEL to gpt-4o`\n\n"
        "*Step 5 — Restart:* say `restart ghostdesk`"
    ),
    "screen_watcher": (
        "👁️ *Screen Watcher Setup*\n\n"
        "Watches your screen every N seconds and sends Telegram alerts for:\n"
        "  errors/crashes, downloads, calls, low battery, media paused\n\n"
        "*Enable it:*\n"
        "  `set SCREEN_WATCHER_ENABLED to true`\n"
        "  `set SCREEN_WATCHER_INTERVAL to 30` _(seconds between checks)_\n\n"
        "*Then restart:* say `restart ghostdesk`"
    ),
    "auto_respond": (
        "🤖 *Auto-Response Setup*\n\n"
        "GhostDesk auto-replies to emails/WhatsApp in your writing style.\n\n"
        "*Step 1 — Enable:*\n"
        "  `set AUTO_RESPOND_ENABLED to true`\n\n"
        "*Step 2 — Choose mode:*\n"
        "  `set AUTO_RESPOND_MODE to suggest` _(asks you before sending)_\n"
        "  `set AUTO_RESPOND_MODE to auto` _(sends automatically)_\n\n"
        "*Step 3 — Enable channels:*\n"
        "  `set AUTO_RESPOND_EMAIL to true`\n"
        "  `set AUTO_RESPOND_WHATSAPP to true`\n"
        "  `set AUTO_RESPOND_TELEGRAM to true`\n\n"
        "*Step 4 — Restart:* say `restart ghostdesk`"
    ),
    "telegram_bot": (
        "🤖 *Telegram Bot Setup*\n\n"
        "*Step 1 — Create a bot:*\n"
        "  Open Telegram → search @BotFather → /newbot\n"
        "  Follow prompts → copy the bot token.\n\n"
        "*Step 2 — Get your chat ID:*\n"
        "  Message @userinfobot → /start → copy the numeric ID.\n\n"
        "*Step 3 — Set values:*\n"
        "  `set TELEGRAM_BOT_TOKEN to 123456:ABCdef...`\n"
        "  `set TELEGRAM_CHAT_ID to 987654321`\n\n"
        "*Step 4 — Restart:* say `restart ghostdesk`"
    ),
    "google_sheets": (
        "📊 *Google Sheets Setup (API — no browser)*\n\n"
        "*Option A — Service Account (recommended for automation):*\n"
        "1️⃣ Go to: console.cloud.google.com\n"
        "2️⃣ Create a project → Enable 'Google Sheets API'\n"
        "3️⃣ IAM & Admin → Service Accounts → Create → Download JSON key\n"
        "4️⃣ Save the JSON file to: `C:\\Users\\YourName\\.ghostdesk\\google_service_account.json`\n"
        "5️⃣ Share your Google Sheet with the service account email\n\n"
        "*Option B — OAuth2 (easier, opens browser once):*\n"
        "1️⃣ Same console → OAuth 2.0 Client IDs → Desktop App → Download JSON\n"
        "2️⃣ Save as: `C:\\Users\\YourName\\.ghostdesk\\google_oauth_secret.json`\n"
        "3️⃣ First use opens a browser to authorize — then cached forever\n\n"
        "*Then use in chat:*\n"
        "  `read my google sheet docs.google.com/spreadsheets/d/ID`\n"
        "  `write to google sheet ID: [data]`\n"
        "  `update cell B3 in sheet ID to 500`"
    ),
    "personality_clone": (
        "🧠 *Personality Clone Setup*\n\n"
        "Teach GhostDesk to write exactly like you — for auto-replies and ghost mode.\n\n"
        "*Data sources you can add:*\n\n"
        "📧 *Email sent history (IMAP):*\n"
        "  Requires EMAIL_ADDRESS + EMAIL_PASSWORD configured.\n"
        "  Then say: `learn my writing style from email`\n\n"
        "📱 *WhatsApp chat export:*\n"
        "  1️⃣ Open any WhatsApp chat (1-on-1 or group)\n"
        "  2️⃣ Tap ⋮ → More → Export Chat → *Without media*\n"
        "  3️⃣ WhatsApp saves a .txt file (or .zip — extract it)\n"
        "  4️⃣ Send that .txt file directly to this bot\n"
        "  GhostDesk auto-detects it and learns from your messages.\n\n"
        "👁️ *Screen Watcher (passive):*\n"
        "  Set SCREEN_WATCHER_ENABLED=true — GhostDesk learns from your typing over time.\n\n"
        "*Check your current data:* say `personality status`\n"
        "*See analysis:* say `build my style profile`"
    ),
    "voice": (
        "🎤 *Voice Setup*\n\n"
        "Voice transcription uses OpenAI Whisper — needs OPENAI_API_KEY even if you use Claude.\n\n"
        "*Enable transcription:*\n"
        "  `set VOICE_TRANSCRIPTION_ENABLED to true`\n"
        "  `set OPENAI_API_KEY to sk-xxxx`\n\n"
        "*Enable voice replies (bot speaks back):*\n"
        "  `set VOICE_REPLY_ENABLED to true`\n\n"
        "*Restart:* say `restart ghostdesk`"
    ),
    "google_services": (
        "🗂️ *Google Services Setup (Drive, Calendar, Docs, Gmail, Contacts)*\n\n"
        "All Google services use the same credentials — set up once, use everywhere.\n"
        "No browser is opened for normal use — all API calls run in the background.\n\n"
        "*Option A — Service Account (best for automation):*\n"
        "1️⃣ Go to: console.cloud.google.com\n"
        "2️⃣ Create a project (or reuse existing)\n"
        "3️⃣ Enable APIs: Drive, Calendar, Docs, Gmail, Sheets, People\n"
        "4️⃣ IAM & Admin → Service Accounts → Create → Download JSON key\n"
        "5️⃣ Save as: `~/.ghostdesk/google_service_account.json`\n"
        "   Or set: `set GOOGLE_SHEETS_CREDS_PATH to /full/path/to/key.json`\n"
        "6️⃣ Share your Drive/Sheets/Docs with the service account email\n\n"
        "*Option B — OAuth2 (easier, personal account):*\n"
        "1️⃣ Same console → APIs & Services → Credentials\n"
        "2️⃣ Create OAuth 2.0 Client ID → Desktop App → Download JSON\n"
        "3️⃣ Save as: `~/.ghostdesk/google_oauth_secret.json`\n"
        "4️⃣ First use opens a browser once to authorize → cached forever\n\n"
        "*Then use in chat:*\n"
        "  `list my drive files`\n"
        "  `upload report.pdf to drive`\n"
        "  `show my calendar events`\n"
        "  `create event: Team meeting tomorrow at 3pm`\n"
        "  `read google doc docs.google.com/document/d/ID`\n"
        "  `check gmail inbox`\n"
        "  `find contact John in my contacts`"
    ),
}


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_env_path() -> Path:
    """Return the active .env file path, creating it if absent."""
    from config import USER_DATA_DIR
    p = USER_DATA_DIR / ".env"
    if not p.exists():
        p.touch()
    return p


def _read_env_file() -> dict:
    """Parse the .env file into a key→value dict."""
    env_path = _get_env_path()
    result = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Could not read .env: {e}")
    return result


def _write_env_key(key: str, value: str) -> bool:
    """Update or insert a key=value line in the .env file."""
    env_path = _get_env_path()
    try:
        try:
            with open(env_path, encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        pattern = re.compile(rf"^{re.escape(key)}\s*=", re.IGNORECASE)
        replaced = False
        new_lines = []
        for line in lines:
            if pattern.match(line):
                new_lines.append(f"{key}={value}\n")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Update running process immediately (no restart needed for some flags)
        os.environ[key] = value
        return True

    except Exception as e:
        logger.error(f"Could not write .env: {e}")
        return False


def _mask(key: str, value: str) -> str:
    """Mask sensitive values, showing only first 4 chars."""
    if not value:
        return "_(not set)_"
    if key in _SENSITIVE and len(value) > 4:
        return value[:4] + "●" * min(len(value) - 4, 20)
    return value


# ─── Public API (agent-callable) ─────────────────────────────────────────────

def get_config_status() -> dict:
    """Return a formatted overview of all config settings."""
    current = _read_env_file()

    lines = ["⚙️ *GhostDesk Configuration*\n"]
    missing_required = []

    for group, keys in _CONFIG_GROUPS.items():
        lines.append(f"*{group}*")
        for k in keys:
            v = current.get(k) or os.getenv(k, "")
            display = _mask(k, v)
            status = "✅" if v else "❌"
            lines.append(f"  {status} `{k}` = {display}")
            if not v and group == "Core (Required)":
                missing_required.append(k)
        lines.append("")

    env_path = _get_env_path()
    lines.append(f"📄 Config file: `{env_path}`")
    lines.append("💡 To change: `set EMAIL_ADDRESS to me@gmail.com`")
    lines.append("💡 To get help: `how do I set up email?`")

    if missing_required:
        lines.append(f"\n⚠️ Missing required: {', '.join(missing_required)}")

    return {
        "success": True,
        "text": "\n".join(lines),
        "missing_required": missing_required,
    }


def set_config(key: str, value: str) -> dict:
    """Set a configuration value in the .env file."""
    key = key.strip().upper().replace(" ", "_").replace("-", "_")
    value = str(value).strip()

    # Strip surrounding quotes the user may have typed
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or \
           (value[0] == "'" and value[-1] == "'"):
            value = value[1:-1]

    if not key:
        return {"success": False, "error": "No key name provided."}

    ok = _write_env_key(key, value)
    if not ok:
        return {"success": False, "error": "Failed to write to .env file."}

    display = _mask(key, value)
    return {
        "success": True,
        "text": (
            f"✅ `{key}` → `{display}`\n\n"
            f"⚠️ *Restart GhostDesk for changes to take effect.*\n"
            f"Say `restart ghostdesk` to restart now."
        ),
    }


def get_setup_guide(service: str) -> dict:
    """Return step-by-step setup instructions for a service."""
    q = service.lower().strip()

    # Match by substring in both directions
    for k, guide in _SETUP_GUIDES.items():
        if k in q or q in k:
            return {"success": True, "text": guide}

    # Try harder: keyword matching
    keyword_map = {
        "gmail": "email",
        "outlook": "email",
        "imap": "email",
        "smtp": "email",
        "mail": "email",
        "meta": "whatsapp",
        "facebook": "whatsapp",
        "wa": "whatsapp",
        "anthropic": "claude",
        "gpt": "openai",
        "screen": "screen_watcher",
        "watcher": "screen_watcher",
        "auto": "auto_respond",
        "reply": "auto_respond",
        "ghost": "auto_respond",
        "bot": "telegram_bot",
        "telegram bot": "telegram_bot",
        "whisper": "voice",
        "speech": "voice",
        "transcribe": "voice",
    }
    for kw, guide_key in keyword_map.items():
        if kw in q:
            return {"success": True, "text": _SETUP_GUIDES[guide_key]}

    available = ", ".join(_SETUP_GUIDES.keys())
    return {
        "success": True,
        "text": (
            f"📚 Available setup guides:\n"
            f"`{available}`\n\n"
            f"Example: `how do I set up email?`"
        ),
    }


def suggest_setup() -> dict:
    """Analyse current config and suggest what to configure next."""
    current = _read_env_file()

    def has(k: str) -> bool:
        return bool(current.get(k) or os.getenv(k, ""))

    def is_true(k: str) -> bool:
        return (current.get(k) or os.getenv(k, "")).lower() == "true"

    suggestions = []

    if not has("EMAIL_ADDRESS") or not has("EMAIL_PASSWORD"):
        suggestions.append(
            "📧 *Email not configured*\n"
            "   Say: `how do I set up email?`"
        )

    if not is_true("WHATSAPP_ENABLED"):
        suggestions.append(
            "📱 *WhatsApp not enabled*\n"
            "   Say: `how do I set up WhatsApp?`"
        )

    if not is_true("SCREEN_WATCHER_ENABLED"):
        suggestions.append(
            "👁️ *Screen Watcher is off*\n"
            "   Say: `set SCREEN_WATCHER_ENABLED to true` to enable it"
        )

    if not is_true("AUTO_RESPOND_ENABLED"):
        suggestions.append(
            "🤖 *Auto-Response is off*\n"
            "   Say: `how do I set up auto-respond?`"
        )

    if not is_true("VOICE_TRANSCRIPTION_ENABLED"):
        suggestions.append(
            "🎤 *Voice transcription is off*\n"
            "   Say: `how do I set up voice?`"
        )

    if not suggestions:
        return {
            "success": True,
            "text": (
                "✅ *All major features are configured!*\n\n"
                "Say `show config` to review all settings."
            ),
        }

    text = (
        "💡 *Setup Suggestions*\n"
        "_(Features you can still unlock)_\n\n"
        + "\n\n".join(suggestions)
        + "\n\nSay `show config` to see all current settings."
    )
    return {"success": True, "text": text}


def get_env_path_info() -> dict:
    """Return where the .env file lives."""
    p = _get_env_path()
    return {
        "success": True,
        "text": f"📄 Config file location: `{p}`",
        "path": str(p),
    }
