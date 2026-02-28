#!/usr/bin/env python3
"""
GhostPC — Main Entry Point
Telegram bot + agent bootstrap + scheduler + optional WhatsApp bridge.
"""

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

# When installed via pip, bare imports (import config, from core.x import)
# need the package directory on sys.path.
sys.path.insert(0, str(Path(__file__).parent))

# Load .env before importing config
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed, fallback to os.environ

import config  # noqa: E402 — must come after dotenv load

# ─── Logging Setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(config.LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ghostpc")

# ─── Telegram Imports ─────────────────────────────────────────────────────────

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode

from core.memory import init_db, get_recent_commands, get_notes, get_active_schedules
from core.agent import GhostAgent
from modules.pc_control import screenshot, get_system_stats


# ─── ASCII Banner ─────────────────────────────────────────────────────────────

BANNER = r"""
  ██████  ██░ ██  ▒█████    ██████ ▄▄▄█████▓ ██▓███   ▄████▄
▒██    ▒ ▓██░ ██▒▒██▒  ██▒▒██    ▒ ▓  ██▒ ▓▒▓██░  ██▒▒██▀ ▀█
░ ▓██▄   ▒██▀▀██░▒██░  ██▒░ ▓██▄   ▒ ▓██░ ▒░▓██░ ██▓▒▒▓█    ▄
  ▒   ██▒░▓█ ░██ ▒██   ██░  ▒   ██▒░ ▓██▓ ░ ▒██▄█▓▒ ▒▒▓▓▄ ▄██▒
▒██████▒▒░▓█▒░██▓░ ████▓▒░▒██████▒▒  ▒██▒ ░ ▒██▒ ░  ░▒ ▓███▀ ░
▒ ▒▓▒ ▒ ░ ▒ ░░▒░▒░ ▒░▒░▒░ ▒ ▒▓▒ ▒ ░  ▒ ░░   ▒▓▒░ ░  ░░ ░▒ ▒  ░
░ ░▒  ░ ░ ▒ ░▒░ ░  ░ ▒ ▒░ ░ ░▒  ░ ░    ░    ░▒ ░       ░  ▒
░  ░  ░   ░  ░░ ░░ ░ ░ ▒  ░  ░  ░    ░      ░░       ░
      ░   ░  ░  ░    ░ ░        ░                     ░ ░
                                                      ░
"""


# ─── Security Guard ───────────────────────────────────────────────────────────

def _is_authorized(update: Update) -> bool:
    """Only respond to the configured TELEGRAM_CHAT_ID."""
    allowed = str(config.TELEGRAM_CHAT_ID).strip()
    if not allowed:
        return True  # If not configured, allow (setup mode)
    return str(update.effective_chat.id) == allowed


# ─── Bot Handlers ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    await update.message.reply_text(
        "👻 *GhostPC is alive and watching your PC.*\n\n"
        "Just talk to me naturally. Examples:\n"
        "• `take a screenshot`\n"
        "• `show me system stats`\n"
        "• `find the latest Excel file in Downloads and make a report`\n"
        "• `open Chrome`\n"
        "• `remind me every Monday to check emails`\n\n"
        "Use /help for the full command list.",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    # Detect which features are active so help is personalised
    features_on  = []
    features_off = []

    if config.WHATSAPP_ENABLED:
        features_on.append("WhatsApp (personal)")
    else:
        features_off.append("WhatsApp — set WHATSAPP_ENABLED=true in .env, requires Node.js (nodejs.org)")

    if config.EMAIL_ADDRESS:
        features_on.append("Email")
    else:
        features_off.append("Email — add EMAIL_ADDRESS + EMAIL_PASSWORD in .env")

    if config.SCREEN_WATCHER_ENABLED:
        features_on.append(f"Screen Watcher (every {config.SCREEN_WATCHER_INTERVAL}s)")
    else:
        features_off.append("Screen Watcher — set SCREEN_WATCHER_ENABLED=true in .env")

    if config.AUTO_RESPOND_ENABLED:
        features_on.append(f"Auto-Response ({config.AUTO_RESPOND_MODE} mode)")
    else:
        features_off.append("Auto-Response — set AUTO_RESPOND_ENABLED=true in .env")

    if config.VOICE_TRANSCRIPTION_ENABLED:
        features_on.append("Voice transcription")

    if config.PERSONALITY_CLONE_ENABLED:
        features_on.append("Personality Clone / Ghost Mode")

    if config.AUTONOMOUS_MODE_ENABLED:
        features_on.append("Autonomous Mode")

    active_block = ("✅ Active: " + ", ".join(features_on)) if features_on else ""
    inactive_block = ""
    if features_off:
        inactive_block = "\n\n⚙️ *Not configured yet:*\n" + "\n".join(f"  • {f}" for f in features_off)
        inactive_block += "\n\nRun `ghostdesk-config` in CMD to edit .env, or `ghostdesk-setup` to re-run the wizard."

    help_text = (
        "👻 *GhostPC — Full Guide*\n\n"

        + (active_block + "\n\n" if active_block else "")

        + "─────────────────────────\n"
        "*📌 Slash Commands*\n"
        "/screenshot — Take a screenshot now\n"
        "/stats — CPU, RAM, disk, uptime\n"
        "/memory — Your last 10 commands\n"
        "/notes — Saved notes & reminders\n"
        "/schedules — Active scheduled tasks\n"
        "/help — This guide\n\n"

        "─────────────────────────\n"
        "*🖥️ PC Control*\n"
        "• `take a screenshot`\n"
        "• `what apps are open`\n"
        "• `open Notepad` / `close Chrome`\n"
        "• `install VLC` / `install 7-Zip`\n"
        "• `type hello world`\n"
        "• `press Ctrl+S`\n"
        "• `lock the PC` / `restart in 5 minutes`\n\n"

        "─────────────────────────\n"
        "*📁 Files & Documents*\n"
        "• `find report.xlsx in Downloads`\n"
        "• `read the file C:\\Users\\me\\notes.txt`\n"
        "• `zip my Desktop folder and send it`\n"
        "• `convert report.xlsx to PDF`\n"
        "• `create a PDF: Dear John, meeting at 3pm`\n"
        "• `merge all PDFs in my Desktop`\n\n"

        "─────────────────────────\n"
        "*🌐 Browser & Web*\n"
        "• `open youtube.com`\n"
        "• `search the web for Python tutorials`\n"
        "• `get the text from bbc.com/news`\n"
        "• `fill the login form on example.com`\n\n"

        "─────────────────────────\n"
        "*🧠 Memory & Notes*\n"
        "• `remember my server password is abc123`\n"
        "• `save a note: buy groceries tomorrow`\n"
        "• `search my notes for password`\n"
        "• `what did I ask you yesterday?`\n\n"

        "─────────────────────────\n"
        "*⏰ Scheduler*\n"
        "• `every day at 9am take a screenshot`\n"
        "• `every Monday at 8am send me system stats`\n"
        "• `every 30 minutes check for new emails`\n"
        "• `/schedules` → then `delete schedule 2`\n\n"

        "─────────────────────────\n"
        "*📱 WhatsApp* (personal — message anyone)\n"
        "• `send WhatsApp to 8801712345678: I'm on my way`\n"
        "• `send WhatsApp to John: running late`\n"
        "• `show my unread WhatsApp messages`\n"
        "• `get last 10 messages from John on WhatsApp`\n\n"

        "─────────────────────────\n"
        "*📧 Email*\n"
        "• `check my unread emails`\n"
        "• `send email to boss@work.com: I'll be late`\n"
        "• `reply to the last email from John`\n\n"

        "─────────────────────────\n"
        "*🎤 Voice*\n"
        "Send a voice note → it's transcribed and executed as a command.\n"
        "• Example: record \"take a screenshot and send it\"\n\n"

        "─────────────────────────\n"
        "*🤖 Autonomous Mode*\n"
        "Give a complex multi-step goal — GhostDesk plans and executes it:\n"
        "• `autonomously: find all Excel files, make PDFs, zip them`\n"
        "• `autonomously: research top 5 Python web frameworks and save a summary note`\n\n"

        "─────────────────────────\n"
        "*👤 Ghost Mode (Personality Clone)*\n"
        "GhostDesk learns your writing style and replies AS YOU:\n"
        "• `how would I reply to: hey are you free tonight?`\n"
        "• `auto-reply to Boss for 2 hours` — enables Ghost Mode\n"
        "• `stop ghost mode for Boss`\n"
        "• `show ghost replies today`\n\n"

        "─────────────────────────\n"
        "*👁️ Screen Watcher*\n"
        "Watches your screen every 30s and alerts you:\n"
        "• `start screen watcher` / `stop screen watcher`\n"
        "• Alerts: errors, crashes, downloads, calls, battery, media paused\n\n"

        "─────────────────────────\n"
        "*📎 File Upload*\n"
        "Drag & drop any file into this chat → ask what to do:\n"
        "• `read it` / `convert to PDF` / `analyse this Excel`\n\n"

        "─────────────────────────\n"
        "*⚙️ Config*\n"
        "• Edit settings: run `ghostdesk-config` in CMD\n"
        "• Re-run full setup: run `ghostdesk-setup` in CMD\n"
        + inactive_block
    )

    # Split into chunks (Telegram 4096 char limit)
    chunk = 4000
    for i in range(0, len(help_text), chunk):
        await update.message.reply_text(help_text[i:i+chunk], parse_mode=ParseMode.MARKDOWN)


async def cmd_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    await update.message.reply_text("📸 Taking screenshot...")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, screenshot)
        if result.get("success") and result.get("file_path"):
            with open(result["file_path"], "rb") as f:
                await update.message.reply_photo(f, caption="Screenshot")
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Screenshot failed')}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, get_system_stats)
        text = result.get("text", str(result))
        await update.message.reply_text(f"🖥️ *System Stats*\n\n{text}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    cmds = get_recent_commands(10)
    if not cmds:
        await update.message.reply_text("📭 No commands in memory yet.")
        return

    lines = ["🧠 *Recent Commands:*\n"]
    for c in cmds:
        status = "✅" if c["success"] else "❌"
        ts = c["timestamp"][:16].replace("T", " ")
        lines.append(f"{status} `{ts}` — {c['user_input'][:60]}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    notes = get_notes(10)
    if not notes:
        await update.message.reply_text("📭 No notes saved yet.")
        return

    lines = ["📝 *Notes:*\n"]
    for n in notes:
        ts = n["timestamp"][:10]
        lines.append(f"• [{n['id']}] *{n['title']}* ({ts})\n  {n['content'][:80]}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    schedules = get_active_schedules()
    if not schedules:
        await update.message.reply_text("📭 No active schedules.")
        return

    lines = ["⏰ *Active Schedules:*\n"]
    for s in schedules:
        lines.append(f"• [{s['id']}] `{s['cron_expression']}` — {s['command_text'][:60]}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── Message Handler ─────────────────────────────────────────────────────────

# Pending confirmations: { chat_id: { "action": ..., "plan": ... } }
_pending_confirmations: dict = {}

# Auto-response approval state (keyed by Telegram message_id of the card)
from modules.auto_responder import (
    _pending_approvals,
    _awaiting_edit,
    handle_approval_callback,
    handle_edit_reply_message,
)

DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "restart", "reboot", "shutdown", "format",
    "close all", "kill process", "wipe"
]

# Triggers for autonomous mode — prefix matching
AUTONOMOUS_TRIGGERS = (
    "autonomously:",
    "autonomously ",
    "your goal is:",
    "your goal is ",
    "auto task:",
    "auto task ",
    "run autonomously:",
)


def _needs_confirmation(plan: dict) -> bool:
    """Check if any action in the plan is destructive."""
    for action in plan.get("actions", []):
        args = action.get("args", {})
        if args.get("confirm") is True:
            return True
        fn = action.get("function", "").lower()
        if any(k in fn for k in ["delete", "restart", "shutdown", "kill", "format"]):
            return True
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    user_text = update.message.text.strip()
    chat_id = update.effective_chat.id

    async def send(text: str):
        # Split messages > 4096 chars
        for i in range(0, len(text), 4000):
            await context.bot.send_message(chat_id=chat_id, text=text[i:i+4000])

    async def send_file(file_path: str, caption: str = ""):
        path = Path(file_path)
        if not path.exists():
            await send(f"⚠️ File not found: {file_path}")
            return
        file_size_mb = path.stat().st_size / (1024 * 1024)

        if file_size_mb > config.MAX_FILE_SEND_MB:
            # Try zipping first
            await send(f"📦 File is {file_size_mb:.1f}MB, zipping...")
            try:
                from modules.file_system import zip_file
                zip_result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: zip_file(str(path))
                )
                if zip_result.get("success"):
                    path = Path(zip_result["zip_path"])
                    file_size_mb = path.stat().st_size / (1024 * 1024)
            except Exception as e:
                await send(f"⚠️ Could not zip: {e}")

        if file_size_mb > 50:
            await send(f"⚠️ File too large to send ({file_size_mb:.1f}MB > 50MB limit)")
            return

        with open(path, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)

    agent = GhostAgent(send, send_file)

    # Pre-check for destructive keywords before parsing
    user_lower = user_text.lower()
    if any(k in user_lower for k in DESTRUCTIVE_KEYWORDS):
        # Get the plan first, then confirm
        from core.ai import get_ai
        from core.memory import build_memory_context
        ai = get_ai()
        try:
            plan = ai.parse_action_plan(user_text, build_memory_context(5))
        except Exception:
            await agent.handle(user_text)
            return

        if _needs_confirmation(plan):
            _pending_confirmations[chat_id] = {
                "plan": plan,
                "user_input": user_text,
                "agent": agent,
            }
            thought = plan.get("thought", "")
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, do it", callback_data="confirm_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="confirm_no"),
                ]
            ])
            await update.message.reply_text(
                f"⚠️ *Confirmation Required*\n\n{thought}\n\nProceed?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            return

    # Check if owner is in "edit reply" mode first
    if await handle_edit_reply_message(user_text, chat_id, context):
        return  # message was consumed as an edited reply

    # ── Autonomous Mode ──────────────────────────────────────────────────────
    if config.AUTONOMOUS_MODE_ENABLED and any(
        user_lower.startswith(t) for t in AUTONOMOUS_TRIGGERS
    ):
        from core.autonomous import run_goal
        await run_goal(user_text, send, send_file)
        return

    await agent.handle(user_text)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses (confirmations + auto-reply approvals)."""
    query = update.callback_query
    chat_id = query.message.chat.id
    await query.answer()

    # ── Auto-response approval buttons ──────────────────────────────────────
    if query.data in ("ar_send", "ar_edit", "ar_skip"):
        await handle_approval_callback(query, context)
        return

    # ── Screen watcher action buttons ────────────────────────────────────────
    if query.data.startswith("sw_dismiss:"):
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if query.data.startswith("sw_fix_error:"):
        err = query.data.split(":", 1)[1]
        await query.edit_message_reply_markup(reply_markup=None)

        async def _sw_send(text: str):
            await context.bot.send_message(chat_id=chat_id, text=text)

        agent = GhostAgent(_sw_send, None)
        asyncio.create_task(agent.handle(f"search the web for a fix for this error: {err}"))
        return

    if query.data.startswith("sw_move_download:"):
        fname = query.data.split(":", 1)[1]
        await query.edit_message_reply_markup(reply_markup=None)

        async def _sw_send(text: str):
            await context.bot.send_message(chat_id=chat_id, text=text)

        agent = GhostAgent(_sw_send, None)
        asyncio.create_task(
            agent.handle(
                f"find the recently downloaded file named '{fname}' in the Downloads folder "
                f"and move it to my Projects folder"
            )
        )
        return

    # ── Destructive action confirmation ──────────────────────────────────────
    pending = _pending_confirmations.pop(chat_id, None)

    if query.data == "confirm_yes" and pending:
        await query.edit_message_text("✅ Confirmed. Executing...")
        agent: GhostAgent = pending["agent"]

        async def send(text: str):
            await context.bot.send_message(chat_id=chat_id, text=text)

        await agent.handle(pending["user_input"])

    elif query.data == "confirm_no":
        await query.edit_message_text("❌ Action cancelled.")
    else:
        await query.edit_message_text("❌ Cancelled or expired.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle files uploaded by the user."""
    if not _is_authorized(update):
        return

    doc = update.message.document
    file = await doc.get_file()
    save_dir = config.TEMP_DIR
    save_path = save_dir / doc.file_name

    await update.message.reply_text(f"📥 Receiving {doc.file_name}...")
    await file.download_to_drive(str(save_path))

    chat_id = update.effective_chat.id

    async def send(text: str):
        await context.bot.send_message(chat_id=chat_id, text=text)

    async def send_file_fn(fp: str, caption: str = ""):
        with open(fp, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)

    agent = GhostAgent(send, send_file_fn)
    await agent.handle_file_upload(str(save_path), doc.file_name)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages — transcribe via Whisper, then run through agent."""
    if not _is_authorized(update):
        return

    if not config.VOICE_TRANSCRIPTION_ENABLED:
        await update.message.reply_text("Voice transcription is disabled. Set VOICE_TRANSCRIPTION_ENABLED=true in config.")
        return

    voice = update.message.voice
    file = await voice.get_file()
    save_path = config.TEMP_DIR / f"voice_{voice.file_id}.ogg"
    await file.download_to_drive(str(save_path))

    await update.message.reply_text("🎙️ Transcribing...")

    chat_id = update.effective_chat.id

    async def send(text: str):
        await context.bot.send_message(chat_id=chat_id, text=text)

    async def send_file_fn(fp: str, caption: str = ""):
        with open(fp, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)

    try:
        from modules.voice import transcribe_voice, text_to_speech

        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: transcribe_voice(str(save_path))
        )
        if not result.get("success"):
            await send(f"❌ Transcription failed: {result.get('error')}")
            return

        text = result["text"]
        await send(f"🎙️ *You said:* _{text}_")

        # Route through agent just like a text message
        agent = GhostAgent(send, send_file_fn)
        await agent.handle(text)

        # Optional: reply as voice note
        if config.VOICE_REPLY_ENABLED:
            # Get the last bot response from agent output (captured in send)
            pass  # Voice reply happens automatically via send_file_fn if TTS is called

    except Exception as e:
        await send(f"❌ Voice handler error: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images uploaded by the user."""
    if not _is_authorized(update):
        return

    photo = update.message.photo[-1]  # highest resolution
    file = await photo.get_file()
    save_path = config.TEMP_DIR / f"photo_{photo.file_id}.jpg"
    await file.download_to_drive(str(save_path))

    chat_id = update.effective_chat.id

    async def send(text: str):
        await context.bot.send_message(chat_id=chat_id, text=text)

    async def send_file_fn(fp: str, caption: str = ""):
        with open(fp, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)

    agent = GhostAgent(send, send_file_fn)
    caption = update.message.caption or "image"
    await agent.handle_file_upload(str(save_path), caption + ".jpg")


# ─── Scheduler Thread ────────────────────────────────────────────────────────

def start_scheduler(bot_app: Application):
    """Start APScheduler in a background thread."""
    try:
        from core.scheduler import start_scheduler as _start
        _start(bot_app)
        logger.info("Scheduler started.")
    except Exception as e:
        logger.warning(f"Scheduler failed to start: {e}")


# ─── WhatsApp Bridge (whatsapp-web.js personal account) ──────────────────────

async def _start_whatsapp_bridge(bot_app: "Application"):
    """Auto-install npm deps and start the whatsapp-web.js bridge as a subprocess."""
    import shutil
    import subprocess

    bridge_dir = Path(__file__).parent / "modules"
    bridge_js  = bridge_dir / "whatsapp_bridge.js"

    if not bridge_js.exists():
        logger.warning("whatsapp_bridge.js not found — WhatsApp bridge disabled.")
        return

    node = shutil.which("node")
    npm  = shutil.which("npm")

    if not node or not npm:
        logger.warning("Node.js not installed — WhatsApp bridge disabled. Install from nodejs.org")
        return

    # Auto-install npm deps if node_modules is missing
    if not (bridge_dir / "node_modules").exists():
        logger.info("Installing WhatsApp bridge npm dependencies (first run)...")
        result = subprocess.run(
            [npm, "install"],
            cwd=str(bridge_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(f"npm install failed: {result.stderr[:200]}")
            return
        logger.info("npm install complete.")

    proc = subprocess.Popen(
        [node, "whatsapp_bridge.js"],
        cwd=str(bridge_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    logger.info(f"WhatsApp bridge started (PID {proc.pid}). Scan QR code in terminal when prompted.")

    def _log_bridge(p):
        for line in p.stdout:
            line = line.rstrip()
            if line:
                logger.info(f"[WhatsApp] {line}")

    threading.Thread(target=_log_bridge, args=(proc,), daemon=True).start()
    await _start_whatsapp_incoming_listener(bot_app)


async def _start_whatsapp_incoming_listener(bot_app: "Application"):
    """Listen for incoming WhatsApp messages from the bridge on port 3100."""
    try:
        from aiohttp import web
        from modules.auto_responder import process_incoming

        async def handle_incoming(request):
            try:
                data         = await request.json()
                contact      = data.get("contact", "")
                contact_name = data.get("contact_name", contact)
                body         = data.get("body", "")
                if contact and body and config.AUTO_RESPOND_WHATSAPP:
                    asyncio.create_task(
                        process_incoming(
                            contact=contact,
                            contact_name=contact_name,
                            incoming_message=body,
                            source="whatsapp",
                            bot=bot_app,
                            chat_id=int(config.TELEGRAM_CHAT_ID),
                        )
                    )
            except Exception as e:
                logger.error(f"WhatsApp incoming handler error: {e}")
            return web.Response(text="ok")

        web_app = web.Application()
        web_app.router.add_post("/incoming/whatsapp", handle_incoming)
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 3100)
        await site.start()
        logger.info("WhatsApp incoming listener on port 3100")
    except ImportError:
        logger.warning("aiohttp not installed — WhatsApp incoming listener disabled.")
    except Exception as e:
        logger.warning(f"WhatsApp incoming listener failed: {e}")


# ─── Email Poller ────────────────────────────────────────────────────────────

_email_last_uid: int = 0


async def _poll_emails_job(bot_app: "Application"):
    """APScheduler-compatible coroutine: check for new emails and auto-respond."""
    global _email_last_uid
    if not config.AUTO_RESPOND_EMAIL or not config.EMAIL_ADDRESS:
        return
    try:
        from modules.email_handler import poll_new_emails
        from modules.auto_responder import process_incoming

        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: poll_new_emails(_email_last_uid)
        )
        if not result.get("success"):
            return

        _email_last_uid = result["new_max_uid"]
        for em in result.get("emails", []):
            sender = em["from"]
            subject = em["subject"]
            body = em["body"]
            email_id = em["id"]

            logger.info(f"New email from {sender}: {subject[:40]}")
            await process_incoming(
                contact=sender,
                contact_name=sender.split("<")[0].strip(),
                incoming_message=f"Subject: {subject}\n\n{body}",
                source="email",
                email_id=email_id,
                email_subject=subject,
                bot=bot_app,
                chat_id=int(config.TELEGRAM_CHAT_ID),
            )
    except Exception as e:
        logger.error(f"Email poll error: {e}")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def validate_config():
    """Validate required config values are present."""
    missing = []
    if not config.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    elif not config.TELEGRAM_CHAT_ID.lstrip("-").isdigit():
        print(f"\n❌ TELEGRAM_CHAT_ID must be a numeric user ID, not '{config.TELEGRAM_CHAT_ID}'.")
        print("   Open Telegram, message @userinfobot, send /start — it replies with your numeric ID.")
        print("   Then update TELEGRAM_CHAT_ID in ~/.ghostdesk/.env\n")
        sys.exit(1)
    if config.AI_PROVIDER == "claude" and not config.CLAUDE_API_KEY:
        missing.append("CLAUDE_API_KEY")
    if config.AI_PROVIDER == "openai" and not config.OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")

    if missing:
        print(f"\n❌ Missing config: {', '.join(missing)}")
        print("   Run: ghostdesk-setup\n")
        sys.exit(1)


def main():
    validate_config()
    init_db()

    print(BANNER)
    print("👻 GhostPC is alive.")
    print(f"   AI: {config.AI_PROVIDER} / {config.AI_MODEL}")
    print(f"   Chat ID: {config.TELEGRAM_CHAT_ID}")
    print(f"   DB: {config.DB_PATH}")
    features = []
    if config.VOICE_TRANSCRIPTION_ENABLED: features.append("Voice")
    if config.SCREEN_WATCHER_ENABLED:      features.append(f"ScreenWatch({config.SCREEN_WATCHER_INTERVAL}s)")
    if config.PERSONALITY_CLONE_ENABLED:   features.append("Personality")
    if config.AUTONOMOUS_MODE_ENABLED:     features.append("Autonomous")
    if features:
        print(f"   Features: {', '.join(features)}")
    print("   Press Ctrl+C to stop.\n")

    # Build Application — support Cloudflare Worker proxy or SOCKS5/HTTP proxy
    _builder = Application.builder().token(config.TELEGRAM_BOT_TOKEN)

    if config.TELEGRAM_API_BASE:
        # Route all Bot API calls through the proxy (e.g. Cloudflare Worker)
        _builder = (
            _builder
            .base_url(f"{config.TELEGRAM_API_BASE}/bot")
            .base_file_url(f"{config.TELEGRAM_API_BASE}/file/bot")
        )
        logger.info("Using Telegram API proxy: %s", config.TELEGRAM_API_BASE)

    if config.HTTPS_PROXY:
        # SOCKS5/HTTP proxy for direct Telegram API access behind a firewall
        _builder = _builder.request(HTTPXRequest(proxy=config.HTTPS_PROXY))
        logger.info("Using HTTPS proxy: %s", config.HTTPS_PROXY)

    app = _builder.build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("screenshot", cmd_screenshot))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("schedules", cmd_schedules))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Start scheduler in background thread
    threading.Thread(target=start_scheduler, args=(app,), daemon=True).start()

    # WhatsApp Cloud API webhook starts inside the async event loop (post_init)

    # ── Auto-response setup ──────────────────────────────────────────────────
    if config.AUTO_RESPOND_ENABLED:
        ar_features = []
        if config.AUTO_RESPOND_WHATSAPP: ar_features.append("WhatsApp")
        if config.AUTO_RESPOND_EMAIL:    ar_features.append("Email")
        if config.AUTO_RESPOND_TELEGRAM: ar_features.append("Telegram DMs")
        mode_label = "suggest" if config.AUTO_RESPOND_MODE == "suggest" else "AUTO"
        print(f"   Auto-response: {mode_label} mode — {', '.join(ar_features) or 'none enabled'}")

    async def post_init(application: "Application"):
        """Runs inside the bot's event loop after startup."""
        # WhatsApp personal bridge (whatsapp-web.js)
        if config.WHATSAPP_ENABLED:
            await _start_whatsapp_bridge(application)

        # Email polling via APScheduler
        if config.AUTO_RESPOND_ENABLED and config.AUTO_RESPOND_EMAIL and config.EMAIL_ADDRESS:
            try:
                from apscheduler.schedulers.asyncio import AsyncIOScheduler
                email_scheduler = AsyncIOScheduler()
                email_scheduler.add_job(
                    _poll_emails_job,
                    "interval",
                    seconds=config.EMAIL_POLL_INTERVAL,
                    args=[application],
                    id="email_poller",
                )
                email_scheduler.start()
                logger.info(f"Email poller started (every {config.EMAIL_POLL_INTERVAL}s)")
            except Exception as e:
                logger.warning(f"Email poller failed: {e}")

        # Telegram personal DM client (Pyrogram)
        if config.AUTO_RESPOND_ENABLED and config.AUTO_RESPOND_TELEGRAM:
            from modules.telegram_client import start_user_client
            await start_user_client(application, int(config.TELEGRAM_CHAT_ID))

        # Screen watcher
        if config.SCREEN_WATCHER_ENABLED:
            from modules import screen_watcher as sw
            sw.set_event_loop(asyncio.get_event_loop())
            sw.start_screen_watcher(
                application,
                int(config.TELEGRAM_CHAT_ID),
                config.SCREEN_WATCHER_INTERVAL,
            )
            logger.info(f"Screen watcher started (every {config.SCREEN_WATCHER_INTERVAL}s)")

    app.post_init = post_init

    # Run Telegram bot (blocking)
    logger.info("Starting Telegram polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
