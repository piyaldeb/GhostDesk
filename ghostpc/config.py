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

# ─── Google Sheets API ────────────────────────────────────────────────────────
# Path to service account JSON, or leave blank to use OAuth2 (~/.ghostdesk/google_token.json)
GOOGLE_SHEETS_CREDS_PATH = os.getenv("GOOGLE_SHEETS_CREDS_PATH", "")

# ─── Security Layer ───────────────────────────────────────────────────────────
# Set SECURITY_PIN to a numeric PIN to require it for CRITICAL actions
# (restart_pc, shutdown_pc).  Leave blank to disable PIN protection.
SECURITY_PIN         = os.getenv("SECURITY_PIN", "")
SECURITY_LOG_ENABLED = os.getenv("SECURITY_LOG_ENABLED", "true").lower() == "true"

# ─── Local LLM (Ollama) ───────────────────────────────────────────────────────
# Install Ollama from https://ollama.ai, pull a model (e.g. ollama pull llama3.2:3b)
# then set OLLAMA_ENABLED=true.  Simple commands will be routed locally; complex
# tasks (documents, email, personality) continue to use your cloud AI provider.
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "false").lower() == "true"
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# ─── Offline Queue / VPS Relay ────────────────────────────────────────────────
# Deploy ghostpc/relay/relay_server.py on a VPS or Raspberry Pi, then set:
#   RELAY_URL=https://your.vps.ip:8765
#   RELAY_SECRET=yoursharedsecret   (must match relay server's RELAY_SECRET)
# The PC sends heartbeats to the relay every RELAY_HEARTBEAT_INTERVAL seconds.
# On startup it fetches any messages queued while the PC was offline.
RELAY_URL                = os.getenv("RELAY_URL", "")
RELAY_SECRET             = os.getenv("RELAY_SECRET", "")
RELAY_HEARTBEAT_INTERVAL = int(os.getenv("RELAY_HEARTBEAT_INTERVAL", "60"))

# ─── YouTube Insights ─────────────────────────────────────────────────────────
# Reads liked videos + subscriptions to build a taste profile and alert on new content.
# Requires YouTube Data API v3 enabled in Google Cloud Console (same OAuth JSON as Google services).
YOUTUBE_ALERTS_ENABLED        = os.getenv("YOUTUBE_ALERTS_ENABLED", "false").lower() == "true"
YOUTUBE_ALERTS_INTERVAL_HOURS = int(os.getenv("YOUTUBE_ALERTS_INTERVAL_HOURS", "24"))

# ─── Platform flags ───────────────────────────────────────────────────────────
IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"
IS_LINUX   = sys.platform.startswith("linux")
