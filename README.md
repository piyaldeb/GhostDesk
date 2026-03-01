# 👻 GhostDesk

**AI-powered PC remote control via a single Telegram bot.**
Works on Windows and Mac. Runs locally. Controlled from anywhere.

```bash
pip install ghostdesk
ghostdesk-setup     # one-time wizard
ghostdesk           # start the agent
```

---

## What It Does

GhostDesk is a self-hosted AI agent that runs on your PC as a background process.
Send any natural language command from Telegram — on your phone, from anywhere — and your computer does it.

---

## Features

### Core
| Feature | Command |
|---|---|
| 📸 Screenshots | `take a screenshot` |
| 🖥️ System stats | `show CPU and RAM usage` |
| 📁 File management | `find the latest Excel in Downloads` |
| 🌐 Browser automation | `search the web for Python async tutorials` |
| 📧 Email | `check my Gmail for unread emails` |
| 💬 WhatsApp | `send a WhatsApp to John: running late` |
| 📊 Excel → PDF reports | `make a production report from sales.xlsx` |
| 🔌 Any API | `call the weather API and tell me Dhaka forecast` |
| 🧠 Memory | `remember my GitHub token is abc123` |
| ⏰ Scheduler | `every Monday at 9am send me a file summary` |

### Auto-Response (new)
Incoming messages are read, AI drafts a reply, you approve via Telegram before sending.
Supports WhatsApp, Email (IMAP), and Telegram personal DMs.

### Voice (new)
Send a voice note to the bot. It's transcribed by OpenAI Whisper and executed as a command.
Optionally, GhostDesk replies as a voice note using OpenAI TTS.

### Screen Watcher (new)
GhostDesk takes a screenshot every N seconds and analyzes it with Vision AI.
If it detects an error, security alert, or critical warning — you get an instant Telegram alert.
Also enables memory queries: `what was on my screen at 3pm?`

### Personality Clone + Ghost Mode (new)
GhostDesk analyzes your outgoing message history and learns to write exactly like you.
**Ghost Mode**: auto-replies to a contact in your exact style for a set duration.
`ghost mode for John for 2 hours` → GhostDesk handles all incoming messages from John, sounding like you.

### Autonomous Agent Mode (new)
Give GhostDesk a complex, multi-step goal. It breaks it into steps, executes them one by one, and reports progress on Telegram.
`autonomously: find all Excel files in Downloads, generate PDF reports, and email them to boss@company.com`

---

## Installation

### Requirements
- Python 3.10+
- A **Telegram Bot Token** → create via [@BotFather](https://t.me/botfather)
- An **AI API key** → [Anthropic (Claude)](https://console.anthropic.com) or [OpenAI](https://platform.openai.com)
- Node.js 18+ *(only for WhatsApp mirroring)*

### Install from PyPI
```bash
pip install ghostdesk
playwright install chromium     # one-time browser install
ghostdesk-setup                 # interactive setup wizard
ghostdesk                       # start the agent
```

### Install from GitHub (latest)
```bash
pip install git+https://github.com/piyaldeb/GhostDesk.git
playwright install chromium
ghostdesk-setup
ghostdesk
```

### Optional extras
```bash
pip install ghostdesk[autorespond]   # Telegram DM auto-response (Pyrogram)
```

---

## Setup Wizard — Step by Step

Run `ghostdesk-setup` once. It walks you through all configuration:

### Step 1 — Telegram Bot
1. Open Telegram → search for **@BotFather**
2. Send `/newbot` → give it a name → copy the **Bot Token**
3. Paste the token into the wizard
4. The wizard will tell you to send `/start` to your bot to capture your **Chat ID**

### Step 2 — AI Provider
Choose Claude (Anthropic) or OpenAI:
- **Claude** (recommended): get key from [console.anthropic.com](https://console.anthropic.com)
- **OpenAI**: get key from [platform.openai.com](https://platform.openai.com)

> If you use Claude as your primary AI but want voice transcription (Whisper), also add `OPENAI_API_KEY` to `~/.ghostdesk/.env`.

### Step 3 — WhatsApp (optional)
Requires Node.js 18+ and `whatsapp-web.js`:
```bash
cd ghostpc/modules
npm install whatsapp-web.js qrcode-terminal node-fetch
```
On first run, a QR code appears in the terminal — scan it with WhatsApp on your phone.

### Step 4 — Email (optional)
Provide your IMAP/SMTP credentials. For Gmail:
1. Enable 2FA on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an App Password → paste it as `EMAIL_PASSWORD`

Settings:
```
IMAP server: imap.gmail.com
SMTP server: smtp.gmail.com
```

### Step 5 — Auto-Response (optional)
When someone messages you, GhostDesk reads recent history with them, drafts an AI reply, and sends it to your Telegram for approval:

```
[✅ Send It]  [✏️ Edit Reply]  [⏭ Skip]
```

- **Suggest mode** (default): always shows the draft for approval before sending
- **Auto mode**: sends immediately without approval

For Telegram DM auto-response, you need API credentials from [my.telegram.org](https://my.telegram.org):
1. Go to my.telegram.org → "API development tools"
2. Create an app → copy `api_id` and `api_hash`
3. Enter them in the wizard
4. First run: you'll be prompted for your phone number + OTP (one-time)

### Step 6 — Voice Module (optional)
Send voice notes to the bot — they're transcribed and executed as commands.
Requires `OPENAI_API_KEY` even if your primary AI is Claude (Whisper is OpenAI-only).

To also receive voice note replies, enable `VOICE_REPLY_ENABLED=true`.

### Step 7 — Screen Watcher (optional)
GhostDesk monitors your screen in the background.
- Screenshots are analyzed by Vision AI
- Alerts sent to Telegram instantly (errors, security warnings, crashes)
- Full history queryable: `what was on my screen at 3pm?`

Recommended interval: 30 seconds. Set lower (10s) for tighter monitoring.

### Step 8 — Advanced AI Features

**Personality Clone / Ghost Mode**
- Analyzes your outgoing message history to extract your writing style
- Generates replies that sound exactly like you
- Ghost Mode auto-replies to contacts for a set duration in your exact style
- Enabled by default

**Autonomous Mode**
- Breaks complex goals into steps and executes them one by one
- Reports progress on Telegram with ✅/❌ per step
- Enabled by default

---

## Example Commands

```
# Core
take a screenshot
show system stats
open Chrome
find resume.docx and send it to me
find the latest Excel in Downloads and make a production report as PDF
every Monday at 9am, show me files modified this week
remember my OpenWeather key is abc123
call the weather API for Dhaka
check my Gmail for unread emails
search the web for Python async tutorials

# Voice
[send a voice message] "find my latest report and send it"

# Screen Watcher
what was on my screen at 3pm?
what happened on my PC between 2pm and 4pm?

# Ghost Mode / Personality
ghost mode for John for 2 hours
build my style profile
show ghost sessions
stop ghost for John

# Autonomous Mode
autonomously: find all Excel files in Downloads, convert to PDFs, and email them to boss@company.com
your goal is: research top Python libraries for data analysis and save a summary note
auto task: take a screenshot, analyze it, and save a note about what I was working on
```

---

## Configuration Reference

All settings live in `~/.ghostdesk/.env`. Edit manually or re-run `ghostdesk-setup`.

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# AI Provider
AI_PROVIDER=claude                  # claude | openai
CLAUDE_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...               # also needed for Whisper voice transcription
AI_MODEL=claude-opus-4-5

# WhatsApp
WHATSAPP_ENABLED=false

# Email
EMAIL_ADDRESS=you@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_IMAP=imap.gmail.com
EMAIL_SMTP=smtp.gmail.com

# Auto-Response
AUTO_RESPOND_ENABLED=false
AUTO_RESPOND_MODE=suggest           # suggest | auto
AUTO_RESPOND_WHATSAPP=false
AUTO_RESPOND_EMAIL=false
AUTO_RESPOND_TELEGRAM=false
AUTO_RESPOND_CONTEXT_DAYS=2
AUTO_RESPOND_WHITELIST=             # comma-separated contacts, empty = all
EMAIL_POLL_INTERVAL=300             # seconds between email checks

# Telegram User Client (for DM auto-response)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# Voice Module
VOICE_TRANSCRIPTION_ENABLED=true
VOICE_REPLY_ENABLED=false

# Screen Watcher
SCREEN_WATCHER_ENABLED=false
SCREEN_WATCHER_INTERVAL=30          # seconds between screenshots

# Advanced Features
PERSONALITY_CLONE_ENABLED=true
AUTONOMOUS_MODE_ENABLED=true
```

---

## Architecture

```
~/.ghostdesk/                    ← all runtime data (never inside pip package)
├── .env                         ← your credentials
├── memory/ghost.db              ← SQLite (commands, notes, schedules, conversations, screen_log)
├── logs/agent.log               ← full operation log
└── temp/                        ← screenshots, voice files, generated PDFs

ghostpc/                         ← Python package
├── main.py                      ← Telegram bot entry point
├── config.py                    ← reads .env, exports all settings
├── wizard.py                    ← ghostdesk-setup wizard
├── core/
│   ├── ai.py                    ← Claude/OpenAI wrapper, structured JSON action plans
│   ├── agent.py                 ← central brain, module dispatcher
│   ├── memory.py                ← SQLite layer (6 tables + FTS)
│   ├── scheduler.py             ← APScheduler, human cron parsing
│   └── autonomous.py            ← multi-step goal execution (NEW)
└── modules/
    ├── pc_control.py            ← screenshots, app control, system stats
    ├── file_system.py           ← find, read, move, zip files
    ├── document.py              ← Excel→PDF, report generation
    ├── browser.py               ← Playwright automation
    ├── whatsapp.py              ← WhatsApp REST client
    ├── whatsapp_bridge.js       ← Node.js whatsapp-web.js bridge
    ├── email_handler.py         ← IMAP/SMTP
    ├── media.py                 ← audio/video control
    ├── api_connector.py         ← universal HTTP API caller
    ├── notifications.py         ← Windows toast notifications
    ├── auto_responder.py        ← AI reply pipeline, approval cards
    ├── telegram_client.py       ← Pyrogram user client (DM auto-response)
    ├── voice.py                 ← Whisper transcription + TTS (NEW)
    ├── screen_watcher.py        ← background vision monitor (NEW)
    └── personality.py           ← style clone + ghost mode (NEW)
```

### How the AI Works

Every command goes through this pipeline:

```
User types command
      ↓
GhostAgent builds context (PC state + recent memory)
      ↓
AI returns structured JSON action plan:
  {
    "thought": "I'll take a screenshot and send it",
    "actions": [
      { "module": "pc_control", "function": "screenshot", "args": {} },
      { "module": "telegram", "function": "send_file", "args": {"file_path": "{result_of_action_0}"} }
    ]
  }
      ↓
Agent executes actions sequentially
      ↓
Results reported back on Telegram
```

### Autonomous Mode Flow

```
User: "autonomously: find all Excel files and email them"
      ↓
AI breaks into steps:
  1. list_files(folder=Downloads, extension=.xlsx)
  2. generate_report(data={result_of_step_0})
  3. send_email(to=boss@..., subject="Reports", body={result_of_step_1})
      ↓
Each step executed via GhostAgent
      ↓
Progress reported: ⚙️ Step 1/3... ✅ Step 1... ⚙️ Step 2/3...
      ↓
Final: 🎯 Goal Complete!
```

### Auto-Response Flow

```
Incoming message (WhatsApp / Email / Telegram DM)
      ↓
Log to conversations table
      ↓
Fetch last 2 days of history with that contact
      ↓
AI drafts reply (or Personality Clone if ghost mode active)
      ↓
Suggest mode → Approval card on Telegram:
  [✅ Send It]  [✏️ Edit Reply]  [⏭ Skip]
      ↓
Owner approves → sent to contact
```

---

## Security

- The bot only responds to your configured Telegram Chat ID
- All other users are silently ignored — no response, no error message
- Credentials stored in `~/.ghostdesk/.env` (never inside the Python package)
- Telegram session files stored in `~/.ghostdesk/telegram_session/` — **never share or commit these**
- Destructive actions (delete, restart, shutdown) require an inline confirmation button before executing

---

## Troubleshooting

**"Missing config" error on start**
→ Run `ghostdesk-setup` to create `~/.ghostdesk/.env`

**Voice transcription fails**
→ Set `OPENAI_API_KEY` in `~/.ghostdesk/.env` (required for Whisper even if using Claude)

**WhatsApp QR code doesn't appear**
→ Run `node ghostpc/modules/whatsapp_bridge.js` manually in a terminal

**Screen watcher not sending alerts**
→ Set `SCREEN_WATCHER_ENABLED=true` and restart. Check `agent.log` for vision errors.

**Telegram DM auto-response asks for phone number**
→ Normal on first run (Pyrogram session setup). Session saved, won't ask again.

**"pyrogram not installed"**
→ `pip install ghostdesk[autorespond]` or `pip install pyrogram tgcrypto`

---

## License

MIT
