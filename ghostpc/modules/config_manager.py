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
    "Security": [
        "SECURITY_PIN",
        "SECURITY_LOG_ENABLED",
    ],
    "Local LLM (Ollama)": [
        "OLLAMA_ENABLED",
        "OLLAMA_URL",
        "OLLAMA_MODEL",
    ],
    "Offline Relay": [
        "RELAY_URL",
        "RELAY_SECRET",
        "RELAY_HEARTBEAT_INTERVAL",
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
# Each guide answers "how do I set up X?" with exact step-by-step instructions.
# Sub-guides answer specific sub-questions like "how do I get the relay URL?".

_SETUP_GUIDES = {

    # ══════════════════════════════════════════════════════════════════════════
    # TELEGRAM BOT
    # ══════════════════════════════════════════════════════════════════════════
    "telegram_bot": (
        "🤖 *Telegram Bot — Complete Setup Guide*\n\n"
        "You need two things: a *bot token* and your *chat ID*.\n\n"
        "─────────────────\n"
        "*STEP 1 — Create the bot (get bot token)*\n"
        "1. Open Telegram on your phone or PC\n"
        "2. Search for `@BotFather` (the official blue-tick bot)\n"
        "3. Send: `/newbot`\n"
        "4. Enter a display name (e.g. `My GhostDesk`)\n"
        "5. Enter a username ending in `bot` (e.g. `myghostdesk_bot`)\n"
        "6. BotFather replies with a token like:\n"
        "   `123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`\n"
        "   ← Copy this — it is your `TELEGRAM_BOT_TOKEN`\n\n"
        "─────────────────\n"
        "*STEP 2 — Get your Chat ID (your personal ID)*\n"
        "1. In Telegram, search for `@userinfobot`\n"
        "2. Send: `/start`\n"
        "3. It replies with your numeric ID, e.g. `Id: 987654321`\n"
        "   ← That number is your `TELEGRAM_CHAT_ID`\n\n"
        "─────────────────\n"
        "*STEP 3 — Apply settings in chat*\n"
        "  `set TELEGRAM_BOT_TOKEN to 123456789:AAHdqTcv...`\n"
        "  `set TELEGRAM_CHAT_ID to 987654321`\n\n"
        "*STEP 4 — Restart:* `restart ghostdesk`\n"
        "*STEP 5 — Open your new bot in Telegram and send:* `/start`"
    ),

    "bot_token": (
        "🔑 *How to get a Telegram Bot Token*\n\n"
        "1. Open Telegram → search `@BotFather`\n"
        "2. Send: `/newbot`\n"
        "3. Choose a name and username (username must end in `bot`)\n"
        "4. BotFather sends a message like:\n\n"
        "   `Done! Congratulations on your new bot. You will find it at t.me/yourbot.`\n"
        "   `Use this token to access the HTTP API:`\n"
        "   `123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`\n\n"
        "5. Copy the token string → that is your `TELEGRAM_BOT_TOKEN`\n\n"
        "*Apply it:* `set TELEGRAM_BOT_TOKEN to 123456789:AAHd...`"
    ),

    "chat_id": (
        "🆔 *How to get your Telegram Chat ID*\n\n"
        "Your Chat ID is the numeric ID of your personal Telegram account.\n"
        "It tells GhostDesk who is allowed to control the bot.\n\n"
        "*Method 1 (easiest):*\n"
        "1. In Telegram, search for `@userinfobot`\n"
        "2. Send: `/start`\n"
        "3. It replies: `Id: 987654321` ← this is your Chat ID\n\n"
        "*Method 2:*\n"
        "1. Search for `@RawDataBot` or `@getidsbot`\n"
        "2. Send any message → it shows your numeric ID\n\n"
        "*Apply it:* `set TELEGRAM_CHAT_ID to 987654321`\n\n"
        "⚠️ Must be a number, not a username."
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # AI PROVIDERS
    # ══════════════════════════════════════════════════════════════════════════
    "claude": (
        "🧠 *Claude (Anthropic) API — Setup Guide*\n\n"
        "*STEP 1 — Create account & get API key*\n"
        "1. Go to: https://console.anthropic.com\n"
        "2. Sign up (or log in)\n"
        "3. Add a payment method (billing → add card)\n"
        "4. Go to: `API Keys` → `Create Key`\n"
        "5. Name it (e.g. `GhostDesk`) and copy the key:\n"
        "   `sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxx`\n\n"
        "*STEP 2 — Choose a model*\n"
        "  `claude-sonnet-4-6`  ← recommended (fast + smart, lower cost)\n"
        "  `claude-opus-4-6`    ← most capable, higher cost\n"
        "  `claude-haiku-4-5-20251001`  ← fastest, cheapest\n\n"
        "*STEP 3 — Apply settings*\n"
        "  `set AI_PROVIDER to claude`\n"
        "  `set CLAUDE_API_KEY to sk-ant-api03-xxxx`\n"
        "  `set AI_MODEL to claude-sonnet-4-6`\n\n"
        "*STEP 4 — Restart:* `restart ghostdesk`\n\n"
        "💡 Cost: ~$0.003 per command with Sonnet. Most users spend <$1/day."
    ),

    "openai": (
        "🤖 *OpenAI API — Setup Guide*\n\n"
        "*STEP 1 — Create account & get API key*\n"
        "1. Go to: https://platform.openai.com\n"
        "2. Sign up (or log in)\n"
        "3. Go to: `API Keys` → `Create new secret key`\n"
        "4. Copy the key: `sk-proj-xxxxxxxxxxxxxxxxxxxxxx`\n"
        "   ⚠️ You can only see it once — save it immediately!\n\n"
        "*STEP 2 — Add credits*\n"
        "  Billing → Payment methods → Add credits (minimum $5)\n\n"
        "*STEP 3 — Choose a model*\n"
        "  `gpt-4o`        ← recommended (fast + smart)\n"
        "  `gpt-4o-mini`   ← cheaper, good for most tasks\n"
        "  `gpt-4-turbo`   ← older, very capable\n\n"
        "*STEP 4 — Apply settings*\n"
        "  `set AI_PROVIDER to openai`\n"
        "  `set OPENAI_API_KEY to sk-proj-xxxx`\n"
        "  `set AI_MODEL to gpt-4o`\n\n"
        "*STEP 5 — Restart:* `restart ghostdesk`"
    ),

    "api_key": (
        "🔑 *How to get an AI API Key*\n\n"
        "*For Claude (recommended):*\n"
        "  console.anthropic.com → API Keys → Create Key\n"
        "  Key starts with: `sk-ant-...`\n\n"
        "*For OpenAI (GPT):*\n"
        "  platform.openai.com → API Keys → Create new secret key\n"
        "  Key starts with: `sk-proj-...` or `sk-...`\n\n"
        "*Apply Claude key:* `set CLAUDE_API_KEY to sk-ant-xxxx`\n"
        "*Apply OpenAI key:* `set OPENAI_API_KEY to sk-proj-xxxx`\n"
        "*Switch provider:* `set AI_PROVIDER to claude` (or `openai`)"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # EMAIL
    # ══════════════════════════════════════════════════════════════════════════
    "email": (
        "📧 *Email — Complete Setup Guide*\n\n"
        "GhostDesk reads and sends email via IMAP/SMTP — no browser needed.\n\n"
        "─────────────────\n"
        "*GMAIL SETUP (most common)*\n\n"
        "*STEP 1 — Enable 2-Step Verification (required for app passwords)*\n"
        "1. Go to: https://myaccount.google.com/security\n"
        "2. Click `2-Step Verification` → follow setup\n\n"
        "*STEP 2 — Create an App Password*\n"
        "1. Same page → scroll to `App passwords`\n"
        "   (If not visible: https://myaccount.google.com/apppasswords)\n"
        "2. Select app: `Mail` | Select device: `Windows Computer`\n"
        "3. Click `Generate` → copy the 16-character code (e.g. `abcd efgh ijkl mnop`)\n"
        "   ← This is your `EMAIL_PASSWORD` (not your Google password!)\n\n"
        "*STEP 3 — Apply settings*\n"
        "  `set EMAIL_ADDRESS to yourname@gmail.com`\n"
        "  `set EMAIL_PASSWORD to abcdefghijklmnop` _(no spaces)_\n"
        "  `set EMAIL_IMAP to imap.gmail.com`\n"
        "  `set EMAIL_SMTP to smtp.gmail.com`\n\n"
        "─────────────────\n"
        "*OTHER PROVIDERS*\n"
        "  Outlook/Hotmail: `imap.outlook.com` / `smtp.office365.com`\n"
        "  Yahoo:  `imap.mail.yahoo.com` / `smtp.mail.yahoo.com`\n"
        "  ProtonMail: needs ProtonMail Bridge app first\n"
        "  Custom domain: use your host's IMAP/SMTP settings\n\n"
        "*STEP 4 — Restart:* `restart ghostdesk`\n\n"
        "💡 Test it: `check my unread emails`"
    ),

    "app_password": (
        "🔑 *How to Create a Gmail App Password*\n\n"
        "Gmail blocks normal passwords for 3rd-party apps. You need an App Password.\n\n"
        "*Requirements:* 2-Step Verification must be ON first.\n\n"
        "*Steps:*\n"
        "1. Go to: https://myaccount.google.com/apppasswords\n"
        "   (or: Google Account → Security → 2-Step Verification → App passwords)\n"
        "2. 'Select app' → choose *Mail*\n"
        "3. 'Select device' → choose *Windows Computer*\n"
        "4. Click `Generate`\n"
        "5. A yellow box shows: `abcd efgh ijkl mnop`\n"
        "   Copy it (without spaces): `abcdefghijklmnop`\n\n"
        "*Apply it:* `set EMAIL_PASSWORD to abcdefghijklmnop`\n\n"
        "⚠️ This is NOT your normal Gmail password. It is a special 16-char code."
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # WHATSAPP
    # ══════════════════════════════════════════════════════════════════════════
    "whatsapp": (
        "📱 *WhatsApp — Complete Setup Guide*\n\n"
        "GhostDesk supports WhatsApp via the Meta Cloud API.\n"
        "This lets you send/receive messages programmatically.\n\n"
        "─────────────────\n"
        "*STEP 1 — Create a Meta Developer Account*\n"
        "1. Go to: https://developers.facebook.com\n"
        "2. Log in with Facebook or create an account\n"
        "3. Go to `My Apps` → `Create App`\n"
        "4. Choose type: `Business` → click Next\n"
        "5. Add a display name (e.g. `GhostDesk WA`)\n"
        "6. Click `Create App`\n\n"
        "─────────────────\n"
        "*STEP 2 — Add WhatsApp Product*\n"
        "1. In your app dashboard → scroll to `Add products`\n"
        "2. Find `WhatsApp` → click `Set up`\n"
        "3. Go to `WhatsApp → API Setup`\n\n"
        "─────────────────\n"
        "*STEP 3 — Get your credentials*\n"
        "On the API Setup page:\n"
        "  • `Phone Number ID` → copy it ← this is `WHATSAPP_PHONE_ID`\n"
        "  • Click `Generate access token` → copy it ← `WHATSAPP_ACCESS_TOKEN`\n"
        "   _(for permanent token: Business Settings → System Users)_\n\n"
        "─────────────────\n"
        "*STEP 4 — Apply settings*\n"
        "  `set WHATSAPP_ENABLED to true`\n"
        "  `set WHATSAPP_PHONE_ID to 123456789012345`\n"
        "  `set WHATSAPP_ACCESS_TOKEN to EAAxxxxxxxx`\n\n"
        "*STEP 5 — Restart:* `restart ghostdesk`\n\n"
        "💡 Test it: `send whatsapp to +1234567890: hello`"
    ),

    "whatsapp_token": (
        "🔑 *How to get a WhatsApp Access Token*\n\n"
        "*Temporary token (expires in 24h):*\n"
        "1. developers.facebook.com → Your App → WhatsApp → API Setup\n"
        "2. Click `Generate access token`\n"
        "3. Copy the `EAA...` string\n\n"
        "*Permanent token (recommended):*\n"
        "1. Business Settings → Users → System Users\n"
        "2. Create a System User with `Admin` role\n"
        "3. Add Assets → select your WhatsApp phone number\n"
        "4. Generate token → select `whatsapp_business_messaging` scope\n"
        "5. Copy the long `EAA...` token\n\n"
        "*Apply it:* `set WHATSAPP_ACCESS_TOKEN to EAAxxxxxxxx`"
    ),

    "phone_id": (
        "📞 *How to get the WhatsApp Phone Number ID*\n\n"
        "This is NOT your actual phone number — it's a Meta internal ID.\n\n"
        "*Steps:*\n"
        "1. Go to: developers.facebook.com → Your App → WhatsApp → API Setup\n"
        "2. Under `From`, you'll see your phone number and below it: `Phone number ID`\n"
        "3. Copy that number (looks like: `102938475611234`)\n\n"
        "*Apply it:* `set WHATSAPP_PHONE_ID to 102938475611234`"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # GOOGLE SERVICES
    # ══════════════════════════════════════════════════════════════════════════
    "google_services": (
        "🗂️ *Google Services — Complete Setup Guide*\n"
        "(Drive, Calendar, Docs, Gmail, Contacts — all in one setup)\n\n"
        "All Google services share the same credentials. Set up once, use all.\n\n"
        "─────────────────\n"
        "*OPTION A — OAuth2 (easier, for personal accounts)*\n\n"
        "*STEP 1 — Create Google Cloud project*\n"
        "1. Go to: https://console.cloud.google.com\n"
        "2. Click `Select a project` (top bar) → `New Project`\n"
        "3. Name it (e.g. `GhostDesk`) → `Create`\n\n"
        "*STEP 2 — Enable APIs*\n"
        "1. Left menu → `APIs & Services` → `Library`\n"
        "2. Search and enable each:\n"
        "   • `Google Drive API`\n"
        "   • `Google Calendar API`\n"
        "   • `Google Docs API`\n"
        "   • `Gmail API`\n"
        "   • `Google Sheets API`\n"
        "   • `People API` (for Contacts)\n\n"
        "*STEP 3 — Create OAuth2 credentials*\n"
        "1. `APIs & Services` → `Credentials` → `Create Credentials`\n"
        "2. Choose: `OAuth 2.0 Client IDs`\n"
        "3. Configure consent screen (if asked): External, add your email as test user\n"
        "4. Application type: `Desktop app` → Name: `GhostDesk` → `Create`\n"
        "5. Click `Download JSON` → save the file\n"
        "6. Rename and move it to: `C:\\Users\\YourName\\.ghostdesk\\google_oauth_secret.json`\n\n"
        "*STEP 4 — First use (authorize once)*\n"
        "  Say: `list my drive files`\n"
        "  A browser opens → log in → click Allow → done forever.\n\n"
        "─────────────────\n"
        "*OPTION B — Service Account (for automation, no browser)*\n"
        "1. `IAM & Admin` → `Service Accounts` → `Create Service Account`\n"
        "2. Name it → `Create and Continue` → `Done`\n"
        "3. Click the service account → `Keys` → `Add Key` → `JSON` → Download\n"
        "4. Save as: `C:\\Users\\YourName\\.ghostdesk\\google_service_account.json`\n"
        "5. Share your Drive/Sheets/Docs with the service account email\n"
        "   `set GOOGLE_SHEETS_CREDS_PATH to C:\\Users\\YourName\\.ghostdesk\\google_service_account.json`\n\n"
        "💡 Test: `list my drive files` or `show my calendar events`"
    ),

    "google_sheets": (
        "📊 *Google Sheets — Setup Guide*\n\n"
        "Same credentials as all Google Services. See `how to set up google services`.\n\n"
        "*Quick path (OAuth2):*\n"
        "1. console.cloud.google.com → Enable `Google Sheets API`\n"
        "2. Credentials → OAuth 2.0 Client ID → Desktop App → Download JSON\n"
        "3. Save as: `~/.ghostdesk/google_oauth_secret.json`\n"
        "4. Say: `read my google sheet [URL or ID]` → browser opens once to authorize\n\n"
        "*Then use in chat:*\n"
        "  `read my google sheet docs.google.com/spreadsheets/d/ID`\n"
        "  `write to google sheet ID: Name=Alice, Score=95`\n"
        "  `update cell B3 in sheet ID to 500`"
    ),

    "google_credentials": (
        "🔑 *How to get Google API Credentials*\n\n"
        "*For OAuth2 (personal account):*\n"
        "1. https://console.cloud.google.com → Your Project\n"
        "2. APIs & Services → Credentials → Create Credentials\n"
        "3. OAuth 2.0 Client IDs → Desktop App → Create → Download JSON\n"
        "4. Save as: `~/.ghostdesk/google_oauth_secret.json`\n\n"
        "*For Service Account (automation):*\n"
        "1. IAM & Admin → Service Accounts → Create\n"
        "2. Keys tab → Add Key → JSON → Download\n"
        "3. Save as: `~/.ghostdesk/google_service_account.json`\n"
        "4. `set GOOGLE_SHEETS_CREDS_PATH to /path/to/key.json`\n\n"
        "Both require enabling APIs first in `APIs & Services → Library`."
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # OFFLINE RELAY / VPS
    # ══════════════════════════════════════════════════════════════════════════
    "relay": (
        "📡 *Offline Queue Relay — Complete Setup Guide*\n\n"
        "The relay queues your commands when your PC is off.\n"
        "When your PC starts, it fetches and runs them automatically.\n\n"
        "─────────────────\n"
        "*STEP 1 — Get a VPS (or use a Raspberry Pi)*\n\n"
        "Cheap VPS options (all have free trials or low cost):\n"
        "  • Oracle Cloud Free Tier: oracle.com/cloud/free (always free)\n"
        "  • Hetzner: hetzner.com (€4/month)\n"
        "  • DigitalOcean: digitalocean.com ($5/month, $200 free credit)\n"
        "  • Vultr: vultr.com ($3.50/month)\n"
        "  • Raspberry Pi at home (free if you have one)\n\n"
        "Choose Ubuntu 22.04 or 24.04. Get the server's IP address.\n\n"
        "─────────────────\n"
        "*STEP 2 — Deploy relay on VPS*\n"
        "SSH into your VPS, then run these commands:\n"
        "  `pip install fastapi uvicorn requests`\n"
        "  `export RELAY_SECRET=mysupersecretkey123`\n"
        "  `export RELAY_PORT=8765`\n"
        "  `python ghostpc/relay/relay_server.py`\n\n"
        "To keep it running after logout:\n"
        "  `nohup python relay_server.py &`\n\n"
        "─────────────────\n"
        "*STEP 3 — Get your Relay URL*\n"
        "Your relay URL is: `http://YOUR_VPS_IP:8765`\n"
        "Example: `http://45.67.89.123:8765`\n\n"
        "Open port 8765 in your VPS firewall:\n"
        "  Ubuntu: `sudo ufw allow 8765`\n"
        "  Oracle Cloud: Security List → Add Ingress Rule → Port 8765\n\n"
        "─────────────────\n"
        "*STEP 4 — Configure your PC*\n"
        "  `set RELAY_URL to http://45.67.89.123:8765`\n"
        "  `set RELAY_SECRET to mysupersecretkey123`\n\n"
        "*STEP 5 — Restart:* `restart ghostdesk`\n\n"
        "─────────────────\n"
        "*STEP 6 — Test it*\n"
        "From any device, POST to the relay to queue a command:\n"
        "  Endpoint: `POST http://YOUR_VPS_IP:8765/queue_message`\n"
        "  Header: `X-GhostDesk-Secret: mysupersecretkey123`\n"
        "  Body: `{\"text\": \"take a screenshot\"}`\n\n"
        "When your PC starts, it will run the command and send you the result!"
    ),

    "relay_url": (
        "🌐 *How to get your Relay URL*\n\n"
        "The relay URL is just: `http://YOUR_VPS_IP:8765`\n\n"
        "*Find your VPS IP:*\n"
        "  → Log into your VPS provider dashboard\n"
        "  → Find `IP Address` or `Public IP` of your server\n"
        "  → Example: `45.67.89.123`\n\n"
        "*Your relay URL will be:*\n"
        "  `http://45.67.89.123:8765`\n\n"
        "*Make sure port 8765 is open:*\n"
        "  Ubuntu: `sudo ufw allow 8765`\n"
        "  CentOS: `sudo firewall-cmd --add-port=8765/tcp --permanent`\n"
        "  Oracle Cloud: Navigate to VCN → Security Lists → Add Ingress Rule → Port 8765\n\n"
        "*Apply it:* `set RELAY_URL to http://45.67.89.123:8765`"
    ),

    "vps": (
        "🖥️ *How to get a VPS (Virtual Private Server)*\n\n"
        "A VPS is a small online server that runs 24/7 — needed for the relay.\n\n"
        "*Free options:*\n"
        "  🟢 Oracle Cloud Free Tier — always free, 1 core, 1GB RAM\n"
        "     https://oracle.com/cloud/free\n"
        "     Choose: `Ubuntu 22.04`, compute instance\n\n"
        "*Cheap paid options ($3–5/month):*\n"
        "  • Hetzner: https://hetzner.com/cloud — €4/mo, very fast\n"
        "  • Vultr: https://vultr.com — $3.50/mo\n"
        "  • DigitalOcean: https://digitalocean.com — $5/mo ($200 free credit)\n"
        "  • Linode/Akamai: https://linode.com — $5/mo\n\n"
        "*Setup steps:*\n"
        "1. Create account on any provider above\n"
        "2. Create a server: Ubuntu 22.04, smallest plan\n"
        "3. SSH into it (they'll give you IP + password)\n"
        "4. Run: `pip install fastapi uvicorn`\n"
        "5. Upload `relay_server.py` and run it\n\n"
        "*Then:* `how do I get my relay URL?`"
    ),

    "relay_secret": (
        "🔐 *Relay Secret Key — What it is and how to set it*\n\n"
        "The relay secret is a password that protects your relay server.\n"
        "Anyone with this secret can queue commands to your PC.\n\n"
        "*Make a strong secret:*\n"
        "  Use a random string of 20+ characters.\n"
        "  Example: `gd-relay-xK9mPq7vN3wL2rT8`\n\n"
        "*Set it in TWO places (both must match):*\n\n"
        "On the VPS (before starting relay_server.py):\n"
        "  `export RELAY_SECRET=gd-relay-xK9mPq7vN3wL2rT8`\n\n"
        "On your PC:\n"
        "  `set RELAY_SECRET to gd-relay-xK9mPq7vN3wL2rT8`\n\n"
        "⚠️ If the secrets don't match, the relay will return 403 Forbidden."
    ),

    "relay_deploy": (
        "🚀 *How to Deploy the Relay Server on VPS*\n\n"
        "*Method 1 — Copy the file to VPS:*\n"
        "From your PC:\n"
        "  `scp ghostpc/relay/relay_server.py user@YOUR_VPS_IP:~/`\n\n"
        "Then SSH into VPS and run:\n"
        "  `pip install fastapi uvicorn`\n"
        "  `RELAY_SECRET=yourpassword python relay_server.py`\n\n"
        "*Method 2 — Run with git clone on VPS:*\n"
        "  `git clone https://github.com/YourUser/GhostDesk.git`\n"
        "  `pip install fastapi uvicorn`\n"
        "  `cd GhostDesk`\n"
        "  `RELAY_SECRET=yourpassword python ghostpc/relay/relay_server.py`\n\n"
        "*Run as a permanent background service (systemd):*\n"
        "Create `/etc/systemd/system/ghostdesk-relay.service` with:\n\n"
        "  [Unit]\n"
        "  Description=GhostDesk Relay\n"
        "  After=network.target\n\n"
        "  [Service]\n"
        "  Environment=RELAY\\_SECRET=yourpassword\n"
        "  ExecStart=/usr/bin/python3 /root/relay\\_server.py\n"
        "  Restart=always\n\n"
        "  [Install]\n"
        "  WantedBy=multi-user.target\n\n"
        "Then enable and start it:\n"
        "  `sudo systemctl enable ghostdesk-relay`\n"
        "  `sudo systemctl start ghostdesk-relay`"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # OLLAMA / LOCAL LLM
    # ══════════════════════════════════════════════════════════════════════════
    "ollama": (
        "🤖 *Local LLM (Ollama) — Complete Setup Guide*\n\n"
        "Run simple commands on your PC without internet or API cost.\n"
        "Screenshot, open app, type text, stats → local. Email, documents → cloud.\n\n"
        "─────────────────\n"
        "*STEP 1 — Install Ollama*\n"
        "  Option A: Download from https://ollama.ai → run installer\n"
        "  Option B: In PowerShell/CMD:\n"
        "    `winget install Ollama.Ollama`\n\n"
        "  Verify: open CMD and run: `ollama --version`\n"
        "  Should print something like: `ollama version 0.5.x`\n\n"
        "─────────────────\n"
        "*STEP 2 — Pull a model*\n"
        "Open CMD and choose one:\n"
        "  `ollama pull llama3.2:3b`   ← 2GB RAM, very fast (recommended start)\n"
        "  `ollama pull llama3.2:8b`   ← 5GB RAM, smarter\n"
        "  `ollama pull mistral:7b`    ← 4GB RAM, good alternative\n"
        "  `ollama pull phi3:mini`     ← 2GB RAM, Microsoft model\n\n"
        "This downloads the model (may take a few minutes).\n\n"
        "─────────────────\n"
        "*STEP 3 — Verify Ollama is running*\n"
        "Ollama runs as a background service after install.\n"
        "Test: open browser → go to `http://localhost:11434/api/tags`\n"
        "Should show JSON with your models listed.\n\n"
        "─────────────────\n"
        "*STEP 4 — Enable in GhostDesk*\n"
        "  `set OLLAMA_ENABLED to true`\n"
        "  `set OLLAMA_MODEL to llama3.2:3b`\n\n"
        "*STEP 5 — Restart:* `restart ghostdesk`\n\n"
        "─────────────────\n"
        "*How routing works:*\n"
        "  `take a screenshot` → Ollama (local, free)\n"
        "  `write an email to boss about the meeting` → Claude/GPT (cloud)\n\n"
        "💡 Check which model handled a command in the GhostDesk log file."
    ),

    "ollama_model": (
        "🧩 *How to choose an Ollama model*\n\n"
        "Models are tradeoffs between size (RAM), speed, and quality.\n\n"
        "*Recommendations by RAM:*\n"
        "  2GB RAM:  `ollama pull phi3:mini` or `ollama pull llama3.2:3b`\n"
        "  4GB RAM:  `ollama pull mistral:7b`\n"
        "  8GB RAM:  `ollama pull llama3.2:8b` or `ollama pull llama3.1:8b`\n"
        "  16GB+ RAM: `ollama pull llama3.1:70b` (very smart but slow)\n\n"
        "*List installed models:*\n"
        "  Run in CMD: `ollama list`\n\n"
        "*Pull a model:*\n"
        "  `ollama pull llama3.2:3b`\n\n"
        "*Apply model choice in GhostDesk:*\n"
        "  `set OLLAMA_MODEL to llama3.2:3b`\n"
        "  `restart ghostdesk`"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # SECURITY / PIN
    # ══════════════════════════════════════════════════════════════════════════
    "security": (
        "🛡️ *Security Layer — Complete Guide*\n\n"
        "GhostDesk has 4 permission tiers for all actions:\n\n"
        "  🟢 *SAFE* — screenshot, read files, check stats → always runs\n"
        "  🟡 *MODERATE* — open app, send email, install apps → runs normally\n"
        "  🔴 *DANGEROUS* — delete files, kill processes, run commands → needs confirmation\n"
        "  🔐 *CRITICAL* — restart PC, shutdown → blocked until PIN entered\n\n"
        "─────────────────\n"
        "*Set up a PIN to protect restart/shutdown:*\n\n"
        "*Method 1 — via chat (easiest):*\n"
        "  `set SECURITY_PIN to 1234`\n"
        "  `restart ghostdesk`\n\n"
        "*Method 2 — edit .env file:*\n"
        "1. Open: `C:\\Users\\YourName\\.ghostdesk\\.env`\n"
        "2. Add line: `SECURITY_PIN=1234`\n"
        "3. Restart GhostDesk\n\n"
        "─────────────────\n"
        "*How to use PIN:*\n"
        "  You: `restart pc`\n"
        "  Bot: 🔐 PIN Required — reply `/pin 1234`\n"
        "  You: `/pin 1234`\n"
        "  Bot: 🔓 Unlocked for 5 minutes\n"
        "  You: `restart pc` (resend)\n"
        "  Bot: ✅ Restarting...\n\n"
        "─────────────────\n"
        "*Audit log — see all actions:*\n"
        "  `/audit` — shows last 25 actions with tier and outcome\n"
        "  Disable logging: `set SECURITY_LOG_ENABLED to false`\n\n"
        "💡 Leave SECURITY_PIN blank to disable PIN protection entirely."
    ),

    "pin": (
        "🔐 *How to set and use a Security PIN*\n\n"
        "*Set your PIN:*\n"
        "  `set SECURITY_PIN to 1234`\n"
        "  `restart ghostdesk`\n\n"
        "*When you need it:*\n"
        "  Restart PC and shutdown commands will say:\n"
        "  `🔐 PIN Required — reply /pin YOUR_PIN`\n\n"
        "*Enter PIN:*\n"
        "  `/pin 1234`\n"
        "  Bot replies: `🔓 Unlocked for 5 minutes`\n\n"
        "*Then resend your original command.*\n\n"
        "Session lasts 5 minutes — after that you need to /pin again.\n\n"
        "To disable PIN: `set SECURITY_PIN to` (blank value) → restart"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # SCREEN WATCHER
    # ══════════════════════════════════════════════════════════════════════════
    "screen_watcher": (
        "👁️ *Screen Watcher — Setup Guide*\n\n"
        "Watches your screen every 30 seconds and alerts you via Telegram when it detects:\n"
        "  • Error dialogs / crash messages\n"
        "  • Download completion pop-ups\n"
        "  • Incoming calls\n"
        "  • Low battery warnings\n"
        "  • Media paused / notifications\n\n"
        "*STEP 1 — Enable it:*\n"
        "  `set SCREEN_WATCHER_ENABLED to true`\n\n"
        "*STEP 2 — Set check interval (optional):*\n"
        "  `set SCREEN_WATCHER_INTERVAL to 30` _(seconds, default 30)_\n\n"
        "*STEP 3 — Set idle detection (optional):*\n"
        "  `set SCREEN_IDLE_SECONDS to 180` _(default: 3 min idle = away)_\n\n"
        "*STEP 4 — Set priority contacts (optional):*\n"
        "  `set PRIORITY_CONTACTS to Boss,Manager,John`\n"
        "  _(alerts when these names appear on screen)_\n\n"
        "*STEP 5 — Restart:* `restart ghostdesk`\n\n"
        "Commands:\n"
        "  `start screen watcher` / `stop screen watcher`\n"
        "  `what did my screen show at 3pm?` (search history)"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # AUTO-RESPONSE
    # ══════════════════════════════════════════════════════════════════════════
    "auto_respond": (
        "🤖 *Auto-Response — Setup Guide*\n\n"
        "GhostDesk can auto-reply to WhatsApp/email/Telegram in your writing style.\n\n"
        "*Two modes:*\n"
        "  `suggest` — GhostDesk drafts a reply, you approve it before it sends\n"
        "  `auto`    — GhostDesk sends automatically (no approval needed)\n\n"
        "─────────────────\n"
        "*STEP 1 — Enable auto-response:*\n"
        "  `set AUTO_RESPOND_ENABLED to true`\n\n"
        "*STEP 2 — Choose mode:*\n"
        "  `set AUTO_RESPOND_MODE to suggest` _(safe, recommended to start)_\n\n"
        "*STEP 3 — Choose channels:*\n"
        "  `set AUTO_RESPOND_EMAIL to true`     ← for email (needs email setup)\n"
        "  `set AUTO_RESPOND_WHATSAPP to true`  ← for WhatsApp (needs WA setup)\n"
        "  `set AUTO_RESPOND_TELEGRAM to true`  ← for Telegram DMs\n\n"
        "*STEP 4 — Set poll interval for email:*\n"
        "  `set EMAIL_POLL_INTERVAL to 300` _(check every 5 minutes, default)_\n\n"
        "*STEP 5 — Restart:* `restart ghostdesk`\n\n"
        "─────────────────\n"
        "*Manual ghost mode (on-demand):*\n"
        "  `auto-reply to Boss for 2 hours` → GhostDesk handles all replies\n"
        "  `stop ghost mode for Boss`        → back to manual"
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # VOICE
    # ══════════════════════════════════════════════════════════════════════════
    "voice": (
        "🎤 *Voice — Setup Guide*\n\n"
        "Send voice messages to GhostDesk — it transcribes them and runs the command.\n"
        "Uses OpenAI Whisper for transcription.\n\n"
        "*STEP 1 — Get OpenAI API key*\n"
        "  (Even if you use Claude for main AI, Whisper requires OpenAI)\n"
        "  Go to: https://platform.openai.com → API Keys → Create\n"
        "  Copy: `sk-proj-xxxxxx`\n\n"
        "*STEP 2 — Enable voice:*\n"
        "  `set VOICE_TRANSCRIPTION_ENABLED to true`\n"
        "  `set OPENAI_API_KEY to sk-proj-xxxx`\n\n"
        "*STEP 3 (optional) — Enable voice replies:*\n"
        "  `set VOICE_REPLY_ENABLED to true`\n"
        "  _(Bot speaks back to you as a voice note)_\n\n"
        "*STEP 4 — Restart:* `restart ghostdesk`\n\n"
        "*How to use:*\n"
        "  Press microphone in Telegram → record your command → send\n"
        "  Bot transcribes and executes it\n\n"
        "💡 Test: Record `take a screenshot` and send as voice note."
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # PERSONALITY CLONE
    # ══════════════════════════════════════════════════════════════════════════
    "personality_clone": (
        "🧠 *Personality Clone — Setup Guide*\n\n"
        "Teaches GhostDesk to write exactly like you.\n"
        "Used for: auto-replies, ghost mode, draft suggestions.\n\n"
        "─────────────────\n"
        "*Method 1 — WhatsApp chat export (fastest)*\n"
        "1. Open WhatsApp on your phone\n"
        "2. Open any chat (1-on-1 works best)\n"
        "3. Tap ⋮ (3 dots) → `More` → `Export Chat`\n"
        "4. Choose: `Without Media`\n"
        "5. Save the `.txt` file (or extract if zipped)\n"
        "6. Send that file directly to this Telegram bot\n"
        "   GhostDesk auto-detects it and learns from your messages!\n\n"
        "─────────────────\n"
        "*Method 2 — Email sent history*\n"
        "Requires email to be configured first.\n"
        "Then say: `learn my writing style from email`\n"
        "GhostDesk reads your sent emails and learns your style.\n\n"
        "─────────────────\n"
        "*Check status:* `personality status`\n"
        "*See data count:* `how much personality data do I have?`\n\n"
        "The more data you add, the better the replies match your style."
    ),

    "whatsapp_export": (
        "📱 *How to export a WhatsApp chat*\n\n"
        "*On Android:*\n"
        "1. Open WhatsApp → open the chat\n"
        "2. Tap the 3 dots (⋮) at top right\n"
        "3. More → Export Chat\n"
        "4. Choose `Without Media`\n"
        "5. Share/save the `.txt` file\n\n"
        "*On iPhone:*\n"
        "1. Open WhatsApp → open the chat\n"
        "2. Tap the contact/group name at the top\n"
        "3. Scroll down → `Export Chat`\n"
        "4. Choose `Without Media`\n"
        "5. Save or AirDrop the `.txt` file\n\n"
        "*Send to GhostDesk:*\n"
        "Drag the `.txt` file into this Telegram chat.\n"
        "GhostDesk will auto-detect it and start learning!"
    ),
}

# ─── Guide aliases — natural language → guide key ─────────────────────────────
# These allow questions like "how to get relay url" to find the right guide.

_GUIDE_ALIASES = {
    # Telegram bot
    "bot": "telegram_bot",
    "botfather": "telegram_bot",
    "bot token": "bot_token",
    "token": "bot_token",
    "telegram token": "bot_token",
    "chat id": "chat_id",
    "my id": "chat_id",
    "userid": "chat_id",
    "user id": "chat_id",
    # AI providers
    "anthropic": "claude",
    "claude api": "claude",
    "gpt": "openai",
    "gpt4": "openai",
    "gpt-4": "openai",
    "api key": "api_key",
    "ai key": "api_key",
    "key": "api_key",
    # Email
    "gmail": "email",
    "imap": "email",
    "smtp": "email",
    "mail": "email",
    "outlook": "email",
    "yahoo": "email",
    "app password": "app_password",
    "application password": "app_password",
    "16 digit": "app_password",
    # WhatsApp
    "meta": "whatsapp",
    "facebook": "whatsapp",
    "wa": "whatsapp",
    "whatsapp token": "whatsapp_token",
    "access token": "whatsapp_token",
    "phone id": "phone_id",
    "phone number id": "phone_id",
    # Google
    "google": "google_services",
    "drive": "google_services",
    "google drive": "google_services",
    "calendar": "google_services",
    "google calendar": "google_services",
    "gmail": "google_services",
    "google docs": "google_services",
    "contacts": "google_services",
    "sheets": "google_sheets",
    "spreadsheet": "google_sheets",
    "service account": "google_credentials",
    "oauth": "google_credentials",
    "oauth2": "google_credentials",
    "credentials": "google_credentials",
    # Relay
    "relay": "relay",
    "offline": "relay",
    "relay url": "relay_url",
    "relay ip": "relay_url",
    "vps ip": "relay_url",
    "server url": "relay_url",
    "server ip": "relay_url",
    "vps": "vps",
    "server": "vps",
    "cheap vps": "vps",
    "free vps": "vps",
    "raspberry pi": "vps",
    "relay secret": "relay_secret",
    "relay password": "relay_secret",
    "relay key": "relay_secret",
    "deploy relay": "relay_deploy",
    "deploy": "relay_deploy",
    "install relay": "relay_deploy",
    # Ollama / local LLM
    "ollama": "ollama",
    "local llm": "ollama",
    "local model": "ollama",
    "llm": "ollama",
    "offline ai": "ollama",
    "llama": "ollama",
    "mistral": "ollama",
    "model": "ollama_model",
    "which model": "ollama_model",
    "ollama model": "ollama_model",
    # Security
    "security": "security",
    "pin": "pin",
    "set pin": "pin",
    "change pin": "pin",
    "audit": "security",
    "audit log": "security",
    "permission": "security",
    "permissions": "security",
    # Screen watcher
    "screen": "screen_watcher",
    "watcher": "screen_watcher",
    "screen watcher": "screen_watcher",
    "monitor": "screen_watcher",
    # Auto-response
    "auto reply": "auto_respond",
    "auto respond": "auto_respond",
    "auto response": "auto_respond",
    "ghost mode": "auto_respond",
    "auto": "auto_respond",
    # Voice
    "voice": "voice",
    "whisper": "voice",
    "speech": "voice",
    "transcribe": "voice",
    "microphone": "voice",
    # Personality
    "personality": "personality_clone",
    "clone": "personality_clone",
    "writing style": "personality_clone",
    "style": "personality_clone",
    "whatsapp export": "whatsapp_export",
    "export chat": "whatsapp_export",
    "export whatsapp": "whatsapp_export",
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
    """
    Return step-by-step setup instructions for a service.
    Accepts natural language queries like 'how do I get relay url'.
    """
    q = service.lower().strip()
    # Remove common question prefixes so "how do I get X" → "X"
    for prefix in ("how do i ", "how to ", "how can i ", "what is ", "where is ",
                   "where do i find ", "how do i get ", "get ", "setup ", "set up ",
                   "configure ", "guide for ", "help with ", "connect "):
        if q.startswith(prefix):
            q = q[len(prefix):]

    # 1. Direct key match
    if q in _SETUP_GUIDES:
        return {"success": True, "text": _SETUP_GUIDES[q]}

    # 2. Exact alias match
    if q in _GUIDE_ALIASES:
        key = _GUIDE_ALIASES[q]
        if key in _SETUP_GUIDES:
            return {"success": True, "text": _SETUP_GUIDES[key]}

    # 3. Substring match in aliases (longest match wins)
    best_match = None
    best_len = 0
    for alias, key in _GUIDE_ALIASES.items():
        if alias in q and len(alias) > best_len:
            if key in _SETUP_GUIDES:
                best_match = key
                best_len = len(alias)
    if best_match:
        return {"success": True, "text": _SETUP_GUIDES[best_match]}

    # 4. Substring match directly in guide keys
    for k, guide in _SETUP_GUIDES.items():
        if k in q or q in k:
            return {"success": True, "text": guide}

    # 5. Nothing found — list available guides
    return {
        "success": True,
        "text": list_guides()["text"],
    }


def list_guides() -> dict:
    """Return a formatted list of all available setup guides."""
    sections = {
        "🤖 AI Setup": ["claude", "openai", "api_key", "ollama", "ollama_model"],
        "📱 Messaging": ["telegram_bot", "bot_token", "chat_id", "whatsapp",
                         "whatsapp_token", "phone_id"],
        "📧 Email": ["email", "app_password"],
        "🗂️ Google": ["google_services", "google_sheets", "google_credentials"],
        "📡 Offline Relay": ["relay", "relay_url", "relay_secret", "relay_deploy", "vps"],
        "🛡️ Security": ["security", "pin"],
        "🧠 Features": ["personality_clone", "whatsapp_export", "auto_respond",
                        "screen_watcher", "voice"],
    }
    lines = ["📚 *GhostDesk Setup Guides*\n", "Ask any of these to get step-by-step help:\n"]
    for section, keys in sections.items():
        lines.append(f"*{section}*")
        for k in keys:
            if k in _SETUP_GUIDES:
                # Get first line of guide as a short description
                first_line = _SETUP_GUIDES[k].split("\n")[0].replace("*", "").strip()
                label = k.replace("_", " ").title()
                lines.append(f"  `guide for {k}` — _{label}_")
        lines.append("")
    lines.append("💬 Or just ask naturally:")
    lines.append("  `how do I get my relay URL?`")
    lines.append("  `how to get app password for gmail?`")
    lines.append("  `how to deploy the relay on VPS?`")
    lines.append("  `how to set up Ollama?`")
    return {"success": True, "text": "\n".join(lines)}


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

    if not has("SECURITY_PIN"):
        suggestions.append(
            "🛡️ *No security PIN set*\n"
            "   Say: `how do I set a security PIN?`\n"
            "   Or: `set SECURITY_PIN to 1234`"
        )

    if not is_true("OLLAMA_ENABLED"):
        suggestions.append(
            "🤖 *Local LLM (Ollama) not enabled*\n"
            "   Run AI commands locally — no cloud cost for simple tasks.\n"
            "   Say: `how do I set up Ollama?`"
        )

    if not has("RELAY_URL"):
        suggestions.append(
            "📡 *Offline relay not configured*\n"
            "   Control your PC even when it was offline (queued commands).\n"
            "   Say: `how do I set up the relay?`"
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
