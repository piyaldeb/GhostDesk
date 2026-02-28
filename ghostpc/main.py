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

    help_text = (
        "👻 *GhostPC Help*\n\n"
        "*Built-in Commands:*\n"
        "/start — Welcome message\n"
        "/screenshot — Take & send screenshot now\n"
        "/stats — System stats (CPU, RAM, disk)\n"
        "/memory — Last 10 commands\n"
        "/notes — List saved notes\n"
        "/schedules — Active scheduled tasks\n"
        "/help — This message\n\n"
        "*Just type anything naturally:*\n"
        "• `open Downloads folder`\n"
        "• `find report.xlsx and convert to PDF`\n"
        "• `check my Gmail for unread emails`\n"
        "• `call the weather API and tell me the forecast`\n"
        "• `remember my GitHub token is abc123`\n"
        "• `every day at 8am send me the news`\n\n"
        "*Send files:* Upload any file and ask what to do with it."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


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

DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "restart", "reboot", "shutdown", "format",
    "close all", "kill process", "wipe"
]


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

    await agent.handle(user_text)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses (confirmations)."""
    query = update.callback_query
    chat_id = query.message.chat.id
    await query.answer()

    pending = _pending_confirmations.pop(chat_id, None)

    if query.data == "confirm_yes" and pending:
        await query.edit_message_text("✅ Confirmed. Executing...")
        agent: GhostAgent = pending["agent"]

        async def send(text: str):
            await context.bot.send_message(chat_id=chat_id, text=text)

        # Re-create agent with fresh send fn (query context may differ)
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


# ─── WhatsApp Bridge ─────────────────────────────────────────────────────────

def start_whatsapp_bridge():
    """Start the WhatsApp bridge subprocess (Node.js)."""
    try:
        import subprocess
        bridge_path = Path(__file__).parent / "modules" / "whatsapp_bridge.js"
        if bridge_path.exists():
            subprocess.Popen(
                ["node", str(bridge_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("WhatsApp bridge started.")
        else:
            logger.warning("WhatsApp bridge script not found.")
    except Exception as e:
        logger.warning(f"WhatsApp bridge failed: {e}")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def validate_config():
    """Validate required config values are present."""
    missing = []
    if not config.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
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
    print("   Press Ctrl+C to stop.\n")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("screenshot", cmd_screenshot))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("schedules", cmd_schedules))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Start scheduler in background thread
    threading.Thread(target=start_scheduler, args=(app,), daemon=True).start()

    # Start WhatsApp bridge if enabled
    if config.WHATSAPP_ENABLED:
        threading.Thread(target=start_whatsapp_bridge, daemon=True).start()

    # Run Telegram bot (blocking)
    logger.info("Starting Telegram polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
