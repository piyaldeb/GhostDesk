# GhostPC Configuration
# Values are loaded from ~/.ghostdesk/.env (written by `ghostdesk-setup`)

import os
import sys
from pathlib import Path

# ─── User data directory (~/.ghostdesk/) ─────────────────────────────────────
# All runtime data (db, logs, temp) lives here — safe for pip-installed packages
USER_DATA_DIR = Path.home() / ".ghostdesk"
USER_DATA_DIR.mkdir(exist_ok=True)

# Load .env from user data dir, then fallback to cwd
for _env_path in [USER_DATA_DIR / ".env", Path.cwd() / ".env"]:
    if _env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(_env_path))
        except ImportError:
            pass
        break

# ─── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
# Optional: point to a Cloudflare Worker or any reverse proxy for api.telegram.org
# e.g. TELEGRAM_API_BASE=https://myproxy.workers.dev
TELEGRAM_API_BASE   = os.getenv("TELEGRAM_API_BASE", "").rstrip("/")
HTTPS_PROXY         = os.getenv("HTTPS_PROXY", "") or os.getenv("https_proxy", "")

# ─── AI Provider ─────────────────────────────────────────────────────────────
AI_PROVIDER    = os.getenv("AI_PROVIDER", "claude")   # "claude" or "openai"
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL       = os.getenv("AI_MODEL", "claude-sonnet-4-6")

# ─── WhatsApp Cloud API (optional) ───────────────────────────────────────────
# Get credentials from: developers.facebook.com → Your App → WhatsApp → API Setup
WHATSAPP_ENABLED      = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")   # Meta permanent access token
WHATSAPP_PHONE_ID     = os.getenv("WHATSAPP_PHONE_ID", "")       # Phone Number ID
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "ghostdesk")  # webhook verify token

# ─── Email (optional) ─────────────────────────────────────────────────────────
EMAIL_IMAP     = os.getenv("EMAIL_IMAP", "")
EMAIL_SMTP     = os.getenv("EMAIL_SMTP", "")
EMAIL_ADDRESS  = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# ─── Agent Behavior ───────────────────────────────────────────────────────────
AGENT_NAME          = os.getenv("AGENT_NAME", "GhostPC")
SCREENSHOT_INTERVAL = int(os.getenv("SCREENSHOT_INTERVAL", "0"))
MEMORY_ENABLED      = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
MAX_FILE_SEND_MB    = int(os.getenv("MAX_FILE_SEND_MB", "50"))

# ─── Paths (all in ~/.ghostdesk/) ────────────────────────────────────────────
MEMORY_DIR = USER_DATA_DIR / "memory"
LOGS_DIR   = USER_DATA_DIR / "logs"
TEMP_DIR   = USER_DATA_DIR / "temp"
DB_PATH    = MEMORY_DIR / "ghost.db"
LOG_PATH   = LOGS_DIR  / "agent.log"

MEMORY_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# ─── Auto-Response ────────────────────────────────────────────────────────────
AUTO_RESPOND_ENABLED      = os.getenv("AUTO_RESPOND_ENABLED", "false").lower() == "true"
AUTO_RESPOND_WHATSAPP     = os.getenv("AUTO_RESPOND_WHATSAPP", "false").lower() == "true"
AUTO_RESPOND_EMAIL        = os.getenv("AUTO_RESPOND_EMAIL",    "false").lower() == "true"
AUTO_RESPOND_TELEGRAM     = os.getenv("AUTO_RESPOND_TELEGRAM", "false").lower() == "true"
AUTO_RESPOND_MODE         = os.getenv("AUTO_RESPOND_MODE", "suggest")   # "suggest" | "auto"
AUTO_RESPOND_CONTEXT_DAYS = int(os.getenv("AUTO_RESPOND_CONTEXT_DAYS", "2"))
AUTO_RESPOND_WHITELIST    = os.getenv("AUTO_RESPOND_WHITELIST", "")  # comma-sep, empty=all
EMAIL_POLL_INTERVAL       = int(os.getenv("EMAIL_POLL_INTERVAL", "300"))  # seconds

# ─── Telegram User Client (for personal DM auto-response) ─────────────────────
TELEGRAM_API_ID   = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# ─── Voice Module ─────────────────────────────────────────────────────────────
# Requires OPENAI_API_KEY even if primary AI provider is Claude
VOICE_TRANSCRIPTION_ENABLED = os.getenv("VOICE_TRANSCRIPTION_ENABLED", "true").lower() == "true"
VOICE_REPLY_ENABLED         = os.getenv("VOICE_REPLY_ENABLED", "false").lower() == "true"

# ─── Screen Watcher ───────────────────────────────────────────────────────────
SCREEN_WATCHER_ENABLED  = os.getenv("SCREEN_WATCHER_ENABLED",  "false").lower() == "true"
SCREEN_WATCHER_INTERVAL = int(os.getenv("SCREEN_WATCHER_INTERVAL", "30"))   # seconds
PRIORITY_CONTACTS       = os.getenv("PRIORITY_CONTACTS", "")                 # e.g. "Boss,Manager,John"
SCREEN_IDLE_SECONDS     = int(os.getenv("SCREEN_IDLE_SECONDS", "180"))       # 3 min idle = walked away

# ─── Personality Clone ────────────────────────────────────────────────────────
PERSONALITY_CLONE_ENABLED = os.getenv("PERSONALITY_CLONE_ENABLED", "true").lower() == "true"

# ─── Autonomous Mode ──────────────────────────────────────────────────────────
AUTONOMOUS_MODE_ENABLED = os.getenv("AUTONOMOUS_MODE_ENABLED", "true").lower() == "true"

# ─── Platform flags ───────────────────────────────────────────────────────────
IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"
IS_LINUX   = sys.platform.startswith("linux")
