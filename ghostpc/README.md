# 👻 GhostPC

**GhostPC** is a self-hosted AI agent that runs as a background process on your Windows PC, giving you complete remote control through a single Telegram bot. Powered by Claude or GPT-4, it understands natural language and executes real actions — opening apps, reading Excel files, generating PDF reports, browsing the web, sending emails, and infinitely more.

---

## What is GhostPC?

Imagine having a highly capable assistant permanently running on your PC. You send a Telegram message from your phone, and your PC does it. Instantly. No remote desktop. No VPN. Just a Telegram message, and your computer obeys.

GhostPC is that assistant. It turns natural language into structured actions using AI, executes them on your local machine, and reports back — all through Telegram.

---

## Features

| Category | Capabilities |
|---|---|
| **PC Control** | Screenshot, open/close apps, system stats, lock, restart, type text, press keys |
| **File System** | Find files, read/write, move/copy/delete, zip, send via Telegram |
| **Document Intelligence** | Read Excel, write Excel, generate PDF/DOCX reports from any data (AI-powered) |
| **Browser Automation** | Open URLs, web search, form filling, scraping (Playwright) |
| **WhatsApp** | Read/send messages, get unread, send files (whatsapp-web.js bridge) |
| **Email** | Read INBOX, send email, reply, attachments (IMAP/SMTP) |
| **Media** | Play/pause/skip, volume control, get current playing |
| **Universal API** | Call any HTTP API with any auth method — infinitely extensible |
| **Scheduler** | "Every Monday at 9am, send me my Downloads summary" — any command, scheduled |
| **Memory** | SQLite-backed: command history, notes, API credentials — forever |

---

## Requirements

- **Python 3.10+** (Windows 10/11)
- **Node.js 18+** (only for WhatsApp bridge)
- A **Telegram Bot Token** (create via [@BotFather](https://t.me/botfather))
- An **AI API key** — [Anthropic (Claude)](https://console.anthropic.com) or [OpenAI](https://platform.openai.com)

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/yourname/ghostpc.git
cd ghostpc

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser
playwright install chromium

# 4. Run the setup wizard
python setup.py

# 5. Start GhostPC
python main.py
```

GhostPC runs as a persistent background process. It will start the Telegram bot, initialize the database, and load your scheduled tasks automatically.

---

## Usage Examples

All commands are plain natural language. Send them to your bot in Telegram:

### PC Control
```
take a screenshot
show system stats
open Chrome
close Notepad
lock my PC
what apps are open right now?
```

### Files
```
find the latest Excel file in Downloads
list all PDF files on my Desktop
send me the file report.xlsx from Downloads
zip the Projects folder and send it
move budget.xlsx from Downloads to Documents
```

### Document Intelligence (flagship)
```
open production_data.xlsx and generate a production report as PDF
read the Excel in Downloads and give me a financial summary
create a PDF with this content: [your text]
merge all PDFs in my Desktop folder
```

### Browser & Web
```
search the web for Python tutorials
open https://github.com
get the text from bbc.com/news
take a screenshot of google.com
```

### Scheduling
```
every Monday at 9am, send me the list of files modified last week
every day at 8am, take a screenshot
every hour, check my email for unread messages
```

### API Integration
```
remember my openweathermap key is abc123
call the weather API for Dhaka
remember my github token is ghp_xxxx
use the GitHub API to list my repos
```

### Memory & Notes
```
remember: my server IP is 192.168.1.100
what did I ask you yesterday about Excel?
list my saved notes
save a note: Title=Meeting Notes, Content=Discussed Q4 targets
```

### Email
```
check my inbox
send an email to boss@company.com with subject "Report" and body "Please see attached"
get last 5 unread emails
```

---

## How Memory Works

Every command you send, along with the AI's thought process and the result, is saved to a local SQLite database at `memory/ghost.db`. This means:

1. **Context awareness** — The AI always knows your last 10 commands before planning new ones.
2. **Search** — Ask "what did I ask about sales reports last week?" and GhostPC searches its memory.
3. **Credentials** — Say "remember my API key is XYZ" and it's stored securely (locally, never sent anywhere).
4. **Notes** — "Remember: my server password is..." creates a searchable note.

The database never leaves your machine.

---

## How to Add API Integrations

You don't need to code anything. Just tell GhostPC:

```
remember my openweathermap api key is YOUR_KEY_HERE
```

Then ask:
```
call the weather API and tell me the forecast for Dhaka
```

GhostPC's AI knows how to build the correct API request using your stored credential.

For any API, you can also instruct directly:
```
call GET https://api.github.com/users/octocat with bearer token MY_TOKEN
```

---

## Project Structure

```
ghostpc/
├── main.py                  ← Entry point (Telegram bot + startup)
├── config.py                ← Configuration (loaded from .env)
├── setup.py                 ← First-time setup wizard
├── requirements.txt
├── core/
│   ├── agent.py             ← Central AI routing brain
│   ├── memory.py            ← SQLite memory layer
│   ├── ai.py                ← Claude/OpenAI wrapper
│   └── scheduler.py         ← APScheduler task engine
├── modules/
│   ├── pc_control.py        ← Screenshot, apps, system control
│   ├── file_system.py       ← File operations
│   ├── document.py          ← Excel, PDF, DOCX, reports (flagship)
│   ├── browser.py           ← Playwright web automation
│   ├── whatsapp.py          ← WhatsApp bridge client
│   ├── whatsapp_bridge.js   ← Node.js WhatsApp bridge server
│   ├── email_handler.py     ← IMAP/SMTP email
│   ├── media.py             ← Audio/video control
│   ├── notifications.py     ← Windows notifications
│   └── api_connector.py     ← Universal HTTP API caller
├── memory/
│   └── ghost.db             ← SQLite database (auto-created)
└── logs/
    └── agent.log
```

---

## WhatsApp Bridge Setup (Optional)

```bash
# In the modules/ directory
npm install whatsapp-web.js express qrcode-terminal

# Start the bridge
node whatsapp_bridge.js

# Scan the QR code with your WhatsApp
# The bridge runs on localhost:3099
```

Set `WHATSAPP_ENABLED=true` in your `.env` to start the bridge automatically with GhostPC.

---

## FAQ

**Q: What happens when my PC is off?**
The agent only works when your PC is on and running `python main.py`. If your PC is off, the Telegram bot won't respond. The scheduler won't fire. GhostPC is a *local* agent, not a cloud service. For 24/7 availability, run it on a PC that stays on, or use Windows Task Scheduler to auto-start it at boot.

**Q: Is my data sent anywhere?**
Your commands are sent to your chosen AI provider (Anthropic/OpenAI) to generate action plans. File contents and screenshots are processed locally unless you explicitly ask GhostPC to send them. API keys and notes are stored only in your local SQLite database.

**Q: How do I auto-start on boot?**
Add a shortcut to `python main.py` to your Windows Startup folder (`Win+R → shell:startup`), or use Windows Task Scheduler.

**Q: Can I use it without an AI API key?**
No. The AI is the brain. Without it, natural language routing doesn't work.

**Q: What if an action fails?**
The agent catches all errors, asks the AI for a recovery suggestion, and reports both the error and the suggestion back to you in Telegram.

**Q: Is it secure?**
The bot only responds to your specific `TELEGRAM_CHAT_ID`. All other users are silently ignored. Your `.env` file contains your credentials — keep it private and never commit it to git.

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Add your module to the `modules/` folder
4. Register it in `core/agent.py`'s system prompt and dispatch table
5. Submit a pull request

All modules must follow the pattern: functions return `{"success": True/False, "text": "...", ...}` for consistent agent handling.

---

## License

MIT License. Use it, modify it, deploy it. Credit appreciated but not required.

---

*GhostPC — One bot. One command. Anything is possible.*
