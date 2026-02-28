"""
GhostDesk Auto-Responder
Listens for incoming messages (WhatsApp, Email, Telegram DMs),
drafts an AI reply using conversation history, and sends it to
the owner's Telegram for approval before dispatching.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─── In-memory pending state ─────────────────────────────────────────────────
# Keyed by the Telegram message_id of the approval card
_pending_approvals: dict[int, dict] = {}

# When owner clicks "Edit Reply", their next plain-text message is the reply
# Keyed by chat_id (owner's chat)
_awaiting_edit: dict[int, dict] = {}


# ─── AI Persona Prompt ────────────────────────────────────────────────────────

PERSONA_PROMPT = """You are drafting a reply on behalf of the user. Your job is to write a natural,
human-sounding response that the user can send (or lightly edit) immediately.

Rules:
- Match the tone and language of the conversation (formal/casual, English/Bengali/etc.)
- Be concise — no fluff, no long explanations unless the conversation requires it
- Never mention you are an AI or assistant
- Do NOT add greetings if the conversation is ongoing
- Reply only to what was asked — don't over-answer

Conversation history with {contact} (last {days} days):
{history}

New incoming message from {contact}:
"{incoming}"

Write ONLY the reply text. Nothing else."""


# ─── Core Logic ──────────────────────────────────────────────────────────────

def _is_whitelisted(contact: str) -> bool:
    """Check if contact is in the auto-respond whitelist (empty = all contacts)."""
    from config import AUTO_RESPOND_WHITELIST
    whitelist = [w.strip().lower() for w in AUTO_RESPOND_WHITELIST.split(",") if w.strip()]
    if not whitelist:
        return True
    return contact.lower() in whitelist


def _format_history(history: list[dict]) -> str:
    """Format conversation history for the AI prompt."""
    if not history:
        return "(No previous messages)"
    lines = []
    for msg in history:
        direction = "Me" if msg["direction"] == "out" else "Them"
        ts = msg["timestamp"][:16].replace("T", " ")
        lines.append(f"[{ts}] {direction}: {msg['message']}")
    return "\n".join(lines)


async def process_incoming(
    contact: str,
    contact_name: str,
    incoming_message: str,
    source: str,           # "whatsapp" | "email" | "telegram"
    email_id: Optional[str] = None,
    email_subject: Optional[str] = None,
    bot=None,              # telegram.ext.Application
    chat_id: Optional[int] = None,
) -> None:
    """
    Full pipeline: log → get context → AI draft → send approval card.
    Called from the WhatsApp webhook, email poller, and Telegram user client.
    """
    from config import AUTO_RESPOND_CONTEXT_DAYS, AUTO_RESPOND_MODE, TELEGRAM_CHAT_ID
    from core.memory import log_conversation, get_conversation_history

    if not _is_whitelisted(contact):
        logger.debug(f"Auto-response: {contact} not in whitelist, skipping.")
        return

    # 1. Log the incoming message
    log_conversation(source, contact, incoming_message, direction="in")

    # 2. Get conversation history
    days = AUTO_RESPOND_CONTEXT_DAYS
    history = get_conversation_history(contact, source, days=days)

    # 3. Generate suggested reply
    suggested = await _generate_reply(contact, contact_name, incoming_message, history, days)

    # 4. Decide: suggest (send to Telegram for approval) or auto-send
    owner_chat = chat_id or int(TELEGRAM_CHAT_ID)

    if AUTO_RESPOND_MODE == "auto":
        await _send_reply(contact, source, suggested, email_id=email_id, email_subject=email_subject)
        log_conversation(source, contact, suggested, direction="out")
        if bot:
            await bot.bot.send_message(
                chat_id=owner_chat,
                text=f"✅ Auto-replied to *{contact_name or contact}* on {source}:\n\n_{suggested}_",
                parse_mode="Markdown"
            )
    else:
        await _queue_for_approval(
            contact=contact,
            contact_name=contact_name,
            source=source,
            incoming=incoming_message,
            suggested=suggested,
            email_id=email_id,
            email_subject=email_subject,
            bot=bot,
            owner_chat=owner_chat,
        )


async def _generate_reply(
    contact: str,
    contact_name: str,
    incoming: str,
    history: list[dict],
    days: int,
) -> str:
    """Call AI to draft a reply."""
    try:
        from core.ai import get_ai
        ai = get_ai()

        prompt = PERSONA_PROMPT.format(
            contact=contact_name or contact,
            days=days,
            history=_format_history(history),
            incoming=incoming,
        )
        reply = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ai.call("You are a message reply assistant.", prompt, max_tokens=512)
        )
        return reply.strip()
    except Exception as e:
        logger.error(f"Auto-responder AI error: {e}")
        return "(Could not generate reply)"


async def _queue_for_approval(
    contact: str,
    contact_name: str,
    source: str,
    incoming: str,
    suggested: str,
    email_id: Optional[str],
    email_subject: Optional[str],
    bot,
    owner_chat: int,
) -> None:
    """Send approval card to owner's Telegram with 3 action buttons."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    display_name = contact_name or contact
    source_icon = {"whatsapp": "💬", "email": "📧", "telegram": "✈️"}.get(source, "📨")
    subject_line = f"\n📌 Subject: _{email_subject}_" if email_subject else ""

    text = (
        f"{source_icon} *New {source.title()} from {display_name}*{subject_line}\n\n"
        f"*They said:*\n_{incoming[:400]}_\n\n"
        f"*Suggested reply:*\n`{suggested[:600]}`"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Send It",    callback_data="ar_send"),
            InlineKeyboardButton("✏️ Edit Reply", callback_data="ar_edit"),
            InlineKeyboardButton("⏭ Skip",        callback_data="ar_skip"),
        ]
    ])

    try:
        sent_msg = await bot.bot.send_message(
            chat_id=owner_chat,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

        # Store pending state keyed by this Telegram message id
        _pending_approvals[sent_msg.message_id] = {
            "contact": contact,
            "contact_name": display_name,
            "source": source,
            "incoming": incoming,
            "suggested_reply": suggested,
            "email_id": email_id,
            "email_subject": email_subject,
        }

    except Exception as e:
        logger.error(f"Could not send approval card: {e}")


# ─── Callback Handlers (called from main.py) ─────────────────────────────────

async def handle_approval_callback(query, context) -> None:
    """
    Handle the 3 approval buttons: ar_send, ar_edit, ar_skip.
    Called from main.py's CallbackQueryHandler.
    """
    from core.memory import log_conversation

    await query.answer()
    msg_id = query.message.message_id
    chat_id = query.message.chat.id
    data = query.data

    pending = _pending_approvals.get(msg_id)
    if not pending:
        await query.edit_message_text("⏰ This reply card has expired.")
        return

    if data == "ar_send":
        _pending_approvals.pop(msg_id, None)
        try:
            await _send_reply(
                contact=pending["contact"],
                source=pending["source"],
                message=pending["suggested_reply"],
                email_id=pending.get("email_id"),
                email_subject=pending.get("email_subject"),
            )
            log_conversation(pending["source"], pending["contact"], pending["suggested_reply"], "out")
            await query.edit_message_text(
                f"✅ Sent to {pending['contact_name']}:\n\n{pending['suggested_reply']}"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to send: {e}")

    elif data == "ar_edit":
        # Store the context; next plain message from owner is the reply
        _awaiting_edit[chat_id] = pending
        _pending_approvals.pop(msg_id, None)
        await query.edit_message_text(
            f"✏️ Type your reply to *{pending['contact_name']}* now.\n"
            f"_(Send any message and it will be dispatched immediately)_",
            parse_mode="Markdown"
        )

    elif data == "ar_skip":
        _pending_approvals.pop(msg_id, None)
        await query.edit_message_text(
            f"⏭ Skipped reply to {pending['contact_name']}."
        )


async def handle_edit_reply_message(user_text: str, chat_id: int, context) -> bool:
    """
    If the owner is in 'edit reply' mode, treat their message as the reply to send.
    Returns True if the message was consumed as a reply (main.py should NOT route to agent).
    """
    from core.memory import log_conversation

    pending = _awaiting_edit.pop(chat_id, None)
    if not pending:
        return False

    try:
        await _send_reply(
            contact=pending["contact"],
            source=pending["source"],
            message=user_text,
            email_id=pending.get("email_id"),
            email_subject=pending.get("email_subject"),
        )
        log_conversation(pending["source"], pending["contact"], user_text, "out")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Your reply sent to *{pending['contact_name']}*.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Failed to send your reply: {e}"
        )

    return True


# ─── Reply Dispatcher ─────────────────────────────────────────────────────────

async def _send_reply(
    contact: str,
    source: str,
    message: str,
    email_id: Optional[str] = None,
    email_subject: Optional[str] = None,
) -> None:
    """Route the approved reply to the correct messaging platform."""
    if source == "whatsapp":
        from modules.whatsapp import send_message
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: send_message(contact, message)
        )
        if not result.get("success"):
            raise RuntimeError(result.get("error", "WhatsApp send failed"))

    elif source == "email":
        from modules.email_handler import reply_email, send_email
        if email_id:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: reply_email(email_id, message)
            )
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: send_email(contact, f"Re: {email_subject or ''}", message)
            )
        if not result.get("success"):
            raise RuntimeError(result.get("error", "Email send failed"))

    elif source == "telegram":
        from modules.telegram_client import get_user_client
        client = get_user_client()
        if client:
            await client.send_reply(contact, message)
        else:
            raise RuntimeError("Telegram user client not initialized")

    else:
        raise ValueError(f"Unknown source: {source}")
