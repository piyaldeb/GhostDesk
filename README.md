# 👻 GhostDesk

**AI-powered PC remote control via a single Telegram bot.**
Works on Windows and Mac. Runs locally. Controlled from anywhere.

```bash
pip install ghostdesk
ghostdesk-setup     # one-time wizard
ghostdesk           # start the agent
```

---

## What it does

GhostDesk is a self-hosted AI agent that runs on your PC as a background process. Send any natural language command from Telegram — on your phone, from anywhere — and your computer does it.

- 📸 **Screenshots** — see your screen remotely
- 📊 **Excel → PDF Reports** — point it at any Excel file, get a formatted report
- 📁 **File Management** — find, read, move, zip, send files via Telegram
- 🌐 **Browser Automation** — web search, scrape pages, fill forms (Playwright)
- 📅 **Scheduler** — "every Monday at 9am, send me my downloads summary"
- 📧 **Email** — read inbox, send emails (IMAP/SMTP)
- 💬 **WhatsApp** — read/send messages (optional, requires Node.js)
- 🔌 **Any API** — "call the GitHub API with my token and list my repos"
- 🧠 **Memory** — SQLite-backed history, notes, stored credentials

---

## Installation

```bash
pip install ghostdesk
playwright install chromium   # one-time browser install
ghostdesk-setup               # enter your Telegram token + AI key
ghostdesk                     # 👻 GhostDesk is alive
```

Install from git (latest):
```bash
pip install git+https://github.com/piyaldeb/GhostDesk.git
```

---

## Requirements

- Python 3.10+
- A **Telegram Bot Token** → create via [@BotFather](https://t.me/botfather)
- An **AI API key** → [Anthropic (Claude)](https://console.anthropic.com) or [OpenAI](https://platform.openai.com)
- Node.js 18+ (only if you want WhatsApp mirroring)

---

## Example Commands

```
take a screenshot
show system stats
find the latest Excel in Downloads and make a production report as PDF
open Chrome
every Monday at 9am, show me files modified this week
remember my openweather key is abc123
call the weather API for Dhaka
check my Gmail for unread emails
search the web for Python async tutorials
```

---

## Config location

All data is stored in `~/.ghostdesk/` — your database, logs, temp files, and `.env`.
Nothing is written into the Python package directory.

---

## Security

The bot only responds to your specific Telegram Chat ID set during setup.
All other users are silently ignored — no response, no error.

---

## License

MIT
