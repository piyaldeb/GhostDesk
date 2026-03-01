"""
GhostDesk Personality Clone
Analyzes outgoing message history to clone the user's writing style,
then generates AI replies that sound exactly like the user.

Ghost Mode: silently auto-replies to a contact for a set duration
using the user's cloned personality — no AI disclosure.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Active ghost sessions: { contact_id: { expires_at, source, contact_name, notify } }
_ghost_sessions: dict = {}

# Last generated draft — enables "refine that reply" follow-up commands
_last_draft: dict = {}

# ─── Style Analysis Prompt ────────────────────────────────────────────────────

STYLE_PROMPT = """You are a linguistics expert analyzing someone's personal writing style.

Here are messages written by the USER (these are their outgoing/sent messages):
{messages}

Study these messages carefully. Return ONLY a JSON object describing their style:
{{
  "vocabulary": "casual / formal / technical / street / academic",
  "message_length": "very brief (1-5 words) / brief (1 sentence) / medium (2-4 sentences) / detailed",
  "emoji_usage": "never / rare / sometimes / often / always",
  "tone": "warm / professional / direct / playful / sarcastic / blunt / neutral",
  "language": "English / Bengali / Mixed EN-BN / Other",
  "capitalization": "proper case / all lowercase / all caps / erratic",
  "punctuation": "minimal (no periods) / standard / heavy (lots of !!!)",
  "filler_words": ["word1", "word2"],
  "common_openers": ["opener1", "opener2"],
  "example_replies": ["short sample reply in their style", "medium sample reply in their style"]
}}

Return ONLY valid JSON. No markdown, no explanation, no extra text."""


CLONE_PROMPT = """You are writing a message PRETENDING TO BE the user.
Your task: craft a reply that sounds EXACTLY like how this person actually writes.
Do NOT be generic. Do NOT sound like an AI.

User's writing style profile:
{style}

Conversation history with {contact} (last {days} days):
{history}

New message from {contact}:
"{incoming}"

Write ONLY the reply text. Mirror their style precisely: same vocabulary, same length pattern,
same emoji frequency, same language mix. Be them, not a polished version of them."""

REFINE_PROMPT = """Refine this message draft based on the instruction below.
Keep the same language, tone, and general intent — only apply the requested change.

Original draft:
"{draft}"

Instruction: {instruction}

Return ONLY the refined message text. No explanation, no quotes around it."""


# ─── Internal Helpers ─────────────────────────────────────────────────────────


def _purge_expired():
    now = datetime.now()
    expired = [k for k, v in _ghost_sessions.items() if v["expires_at"] < now]
    for k in expired:
        _ghost_sessions.pop(k, None)


# ─── Public API ───────────────────────────────────────────────────────────────


def build_contact_profile(contact_name: str, source: Optional[str] = None) -> dict:
    """
    Analyze the user's outgoing message history to extract their writing style.

    Args:
        contact_name: Contact name/ID to filter history (or empty for all)
        source: "whatsapp" | "email" | "telegram" (or None for all)

    Returns:
        {"success": bool, "profile": dict, "message_count": int}
    """
    try:
        from core.memory import get_connection
        from core.ai import get_ai

        with get_connection() as conn:
            query = "SELECT message FROM conversations WHERE direction = 'out'"
            params: list = []
            if source:
                query += " AND source = ?"
                params.append(source)
            query += " ORDER BY timestamp DESC LIMIT 200"
            rows = conn.execute(query, params).fetchall()

        if len(rows) < 5:
            return {
                "success": False,
                "error": (
                    "Not enough sent message history to build a style profile. "
                    "Need at least 5 outgoing messages in the conversation log."
                ),
            }

        messages_text = "\n---\n".join([r["message"] for r in rows[:100]])
        ai = get_ai()
        raw = ai.call(
            "You are a linguistics expert analyzing writing style.",
            STYLE_PROMPT.format(messages=messages_text[:6000]),
            max_tokens=1024,
        )

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        profile = json.loads(raw)
        logger.info(f"Style profile built for '{contact_name}' from {len(rows)} messages")
        return {"success": True, "profile": profile, "message_count": len(rows)}

    except json.JSONDecodeError:
        return {"success": False, "error": "AI returned an invalid style profile format"}
    except Exception as e:
        logger.error(f"build_contact_profile error: {e}")
        return {"success": False, "error": str(e)}


def generate_reply_as_user(
    incoming_message: str,
    contact: str,
    source: str = "whatsapp",
    days: int = 2,
    style_override: Optional[dict] = None,
) -> dict:
    """
    Generate a reply that sounds like the user, using their cloned style.

    Args:
        incoming_message: The message received from the contact
        contact: Contact ID/name
        source: Platform ("whatsapp", "email", "telegram")
        days: Days of history to use as context
        style_override: Pre-built style dict (skips profile build if provided)

    Returns:
        {"success": bool, "reply": str}
    """
    try:
        from core.memory import get_conversation_history
        from core.ai import get_ai

        if style_override:
            style_json = json.dumps(style_override, indent=2)
        else:
            profile_result = build_contact_profile(contact, source)
            if profile_result.get("success"):
                style_json = json.dumps(profile_result["profile"], indent=2)
            else:
                # Fallback to minimal style hints
                style_json = json.dumps({
                    "tone": "natural, conversational",
                    "message_length": "brief",
                    "notes": "Match the user's general messaging style",
                })

        history = get_conversation_history(contact, source, days=days)
        history_text = "\n".join([
            f"{'Me' if m['direction'] == 'out' else contact}: {m['message']}"
            for m in history
        ]) or "(No prior messages)"

        ai = get_ai()
        prompt = CLONE_PROMPT.format(
            style=style_json,
            contact=contact,
            days=days,
            history=history_text[:4000],
            incoming=incoming_message,
        )
        reply = ai.call(
            "You are a personality mirroring assistant.",
            prompt,
            max_tokens=512,
        )
        return {"success": True, "reply": reply.strip()}

    except Exception as e:
        logger.error(f"generate_reply_as_user error: {e}")
        return {"success": False, "error": str(e)}


def enable_ghost_mode(
    contact: str,
    duration_minutes: int,
    source: str = "whatsapp",
    contact_name: str = "",
    notify: bool = False,
) -> dict:
    """
    Enable ghost mode: auto-reply to a contact in the user's style for N minutes.

    Args:
        notify: If True, send owner a Telegram message after each auto-reply.
                If False (default), replies silently with no notifications.

    Returns:
        {"success": bool, "text": str, "expires_at": str}
    """
    _purge_expired()
    expires_at = datetime.now() + timedelta(minutes=duration_minutes)
    _ghost_sessions[contact] = {
        "expires_at": expires_at,
        "source": source,
        "contact_name": contact_name or contact,
        "duration_minutes": duration_minutes,
        "notify": notify,
    }
    expires_str = expires_at.strftime("%H:%M")
    name = contact_name or contact
    mode_label = "notify mode" if notify else "fully silent"
    logger.info(f"Ghost mode ON ({mode_label}): {name} ({source}) for {duration_minutes}min")
    return {
        "success": True,
        "text": (
            f"Ghost mode activated for *{name}* on {source} — {mode_label}\n"
            f"Duration: {duration_minutes} minutes — active until {expires_str}\n"
            f"I'll auto-reply in your style. Say 'stop ghost for {name}' to cancel early."
        ),
        "expires_at": expires_at.isoformat(),
    }


def disable_ghost_mode(contact: str) -> dict:
    """Disable ghost mode for a specific contact."""
    _purge_expired()
    session = _ghost_sessions.pop(contact, None)
    if session:
        name = session.get("contact_name", contact)
        return {"success": True, "text": f"Ghost mode disabled for {name}."}
    return {"success": False, "text": f"No active ghost session for contact: {contact}"}


def get_ghost_sessions() -> dict:
    """List all currently active ghost mode sessions."""
    _purge_expired()
    if not _ghost_sessions:
        return {"success": True, "text": "No active ghost mode sessions.", "sessions": []}

    sessions = []
    for contact_id, s in _ghost_sessions.items():
        remaining = int((s["expires_at"] - datetime.now()).total_seconds() / 60)
        sessions.append({
            "contact": contact_id,
            "name": s.get("contact_name", contact_id),
            "source": s.get("source", "?"),
            "remaining_minutes": max(0, remaining),
        })

    lines = [
        f"• {s['name']} ({s['source']}) — {s['remaining_minutes']}min remaining"
        for s in sessions
    ]
    return {
        "success": True,
        "text": "Active ghost mode sessions:\n" + "\n".join(lines),
        "sessions": sessions,
    }


def is_ghost_active(contact: str) -> bool:
    """Return True if ghost mode is currently active for this contact."""
    _purge_expired()
    return contact in _ghost_sessions


def get_ghost_session(contact: str) -> Optional[dict]:
    """Return the full ghost session dict for a contact, or None if not active."""
    _purge_expired()
    return _ghost_sessions.get(contact)


def draft_reply(
    incoming_message: str,
    contact: str,
    source: str = "whatsapp",
    days: int = 2,
) -> dict:
    """
    Generate a reply draft in the user's style and store it for potential refinement.
    The user can review, edit, or ask to "refine that reply" before deciding to send.

    Returns:
        {"success": bool, "reply": str, "text": str}
    """
    result = generate_reply_as_user(incoming_message, contact, source, days)
    if result.get("success"):
        _last_draft.update({
            "reply":            result["reply"],
            "incoming_message": incoming_message,
            "contact":          contact,
            "source":           source,
            "days":             days,
        })
        return {
            "success": True,
            "reply": result["reply"],
            "text": (
                f"Draft reply to *{contact}*:\n\n{result['reply']}\n\n"
                f"Say 'refine that reply — [instruction]' to adjust, or approve and send manually."
            ),
        }
    return result


def refine_reply(instruction: str) -> dict:
    """
    Refine the last generated draft based on a natural language instruction.
    Example: "make it shorter", "be more formal", "add an emoji".

    Returns:
        {"success": bool, "reply": str, "text": str}
    """
    if not _last_draft.get("reply"):
        return {
            "success": False,
            "text": (
                "No recent draft to refine. "
                "First generate one with 'how would I reply to this?' and paste the message."
            ),
        }
    try:
        from core.ai import get_ai
        ai = get_ai()
        prompt = REFINE_PROMPT.format(draft=_last_draft["reply"], instruction=instruction)
        refined = ai.call("You are a message editing assistant.", prompt, max_tokens=512).strip()
        _last_draft["reply"] = refined
        contact = _last_draft.get("contact", "contact")
        return {
            "success": True,
            "reply": refined,
            "text": f"Refined reply to *{contact}*:\n\n{refined}",
        }
    except Exception as e:
        logger.error(f"refine_reply error: {e}")
        return {"success": False, "error": str(e)}


def get_ghost_replies(days: int = 1) -> dict:
    """
    List outgoing AI-generated replies sent in the last N days.
    Queries the conversations table for direction='out' entries.

    Returns:
        {"success": bool, "text": str, "count": int}
    """
    try:
        from core.memory import get_connection
        since = (datetime.now() - timedelta(days=days)).isoformat()

        with get_connection() as conn:
            rows = conn.execute(
                """SELECT timestamp, source, contact, message
                   FROM conversations
                   WHERE direction = 'out' AND timestamp >= ?
                   ORDER BY timestamp DESC LIMIT 50""",
                (since,),
            ).fetchall()

        if not rows:
            period = "today" if days == 1 else f"the last {days} days"
            return {"success": True, "text": f"No auto-replies sent in {period}.", "count": 0}

        period = "today" if days == 1 else f"the last {days} days"
        lines = [
            f"[{r['timestamp'][:16].replace('T', ' ')}] → {r['contact']} ({r['source']}): {r['message'][:80]}"
            for r in rows
        ]
        return {
            "success": True,
            "text": f"Auto-replies sent ({period}):\n\n" + "\n".join(lines),
            "count": len(rows),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Personality Learning ──────────────────────────────────────────────────────

def learn_from_sent_emails(limit: int = 150) -> dict:
    """
    Pull sent emails via IMAP and store them as personality training data.
    Strips quoted replies so only the user's own words are learned.
    """
    import imaplib
    import email as email_lib
    from email.header import decode_header as _dh

    from config import EMAIL_ADDRESS, EMAIL_PASSWORD, EMAIL_IMAP

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        return {
            "success": False,
            "needs_setup": True,
            "text": (
                "Email not configured — I need your email credentials to learn your writing style.\n\n"
                "Set these first:\n"
                "  `set EMAIL_ADDRESS to you@gmail.com`\n"
                "  `set EMAIL_PASSWORD to your-app-password`\n"
                "  `set EMAIL_IMAP to imap.gmail.com`\n\n"
                "Then say `learn my writing style from email` again."
            ),
        }

    try:
        imap_host = EMAIL_IMAP or "imap.gmail.com"
        imap = imaplib.IMAP4_SSL(imap_host)
        imap.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

        # Find Sent folder (varies by provider)
        sent_folder = None
        for name in ["[Gmail]/Sent Mail", "Sent", "Sent Items", "Sent Messages",
                     "INBOX.Sent", "Sent Mail"]:
            try:
                status, _ = imap.select(f'"{name}"')
                if status == "OK":
                    sent_folder = f'"{name}"'
                    break
            except Exception:
                continue

        if not sent_folder:
            imap.logout()
            return {"success": False, "error": "Could not find Sent folder. Check IMAP settings."}

        _, data = imap.search(None, "ALL")
        uids = data[0].split()
        # Most recent first
        uids = uids[-limit:] if len(uids) > limit else uids

        from core.memory import get_connection

        stored = 0
        with get_connection() as conn:
            for uid in reversed(uids):  # newest first
                try:
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email_lib.message_from_bytes(raw)

                    # Extract plain text body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ct = part.get_content_type()
                            if ct == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # Strip quoted lines (> prefix) and email headers in body
                    lines = []
                    for line in body.splitlines():
                        stripped = line.strip()
                        if not stripped.startswith(">") and not stripped.startswith("On ") \
                                and not stripped.startswith("From:") \
                                and not stripped.startswith("Sent:"):
                            lines.append(line)
                    body = "\n".join(lines).strip()

                    if len(body) > 30:
                        date_str = msg.get("Date", "")
                        conn.execute(
                            "INSERT OR IGNORE INTO conversations "
                            "(contact, direction, message, source, timestamp) VALUES (?, ?, ?, ?, ?)",
                            ("_email_training", "out", body[:2000], "email", date_str),
                        )
                        stored += 1
                except Exception:
                    continue
            conn.commit()

        imap.logout()
        return {
            "success": True,
            "stored": stored,
            "text": (
                f"✅ Learned from *{stored}* sent emails.\n"
                f"Your writing style profile has been updated.\n"
                f"Say `build my style profile` to see the analysis."
            ),
        }

    except imaplib.IMAP4.error as e:
        return {
            "success": False,
            "error": f"IMAP login failed: {e}\nCheck EMAIL_ADDRESS, EMAIL_PASSWORD, and EMAIL_IMAP.",
        }
    except Exception as e:
        logger.error(f"learn_from_sent_emails error: {e}")
        return {"success": False, "error": str(e)}


def store_screen_behavior(text_snippet: str, app_name: str = "") -> None:
    """
    Called by screen_watcher when it detects the user composing text.
    Stores the snippet as personality training data (outgoing behavior).
    """
    if not text_snippet or len(text_snippet.strip()) < 20:
        return
    try:
        from core.memory import get_connection
        from datetime import datetime
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations "
                "(contact, direction, message, source, timestamp) VALUES (?, ?, ?, ?, ?)",
                ("_screen_training", "out", text_snippet[:1000], f"screen:{app_name}",
                 datetime.now().isoformat()),
            )
            conn.commit()
    except Exception as e:
        logger.debug(f"store_screen_behavior error: {e}")


def get_personality_status() -> dict:
    """Show how much training data is available for the personality clone."""
    try:
        from core.memory import get_connection
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE direction = 'out'"
            ).fetchone()[0]
            email_count = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE direction = 'out' AND source = 'email'"
            ).fetchone()[0]
            screen_count = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE direction = 'out' AND source LIKE 'screen:%'"
            ).fetchone()[0]
            wa_count = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE direction = 'out' AND source = 'whatsapp'"
            ).fetchone()[0]

        quality = "excellent" if total >= 100 else "good" if total >= 30 else "limited"
        tip = ""
        if email_count == 0:
            tip = "\n💡 Say `learn my writing style from email` to add email training data."
        elif total < 30:
            tip = "\n💡 More data = better clone. Keep using the bot and enable screen watcher."

        return {
            "success": True,
            "total": total,
            "text": (
                f"🧠 *Personality Clone Data*\n\n"
                f"Total training samples: *{total}* ({quality})\n"
                f"  📧 From email: {email_count}\n"
                f"  👁️ From screen: {screen_count}\n"
                f"  📱 From WhatsApp: {wa_count}"
                + tip
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def setup_personality() -> dict:
    """
    Guided setup for personality clone — checks data sources and suggests next steps.
    Called automatically when PERSONALITY_CLONE_ENABLED=true on first boot.
    """
    from config import EMAIL_ADDRESS, EMAIL_PASSWORD, SCREEN_WATCHER_ENABLED

    status = get_personality_status()
    total = status.get("total", 0)

    lines = ["🧠 *Personality Clone Setup*\n"]

    # Email source
    if EMAIL_ADDRESS and EMAIL_PASSWORD:
        lines.append("📧 Email: ✅ configured")
        if total < 20:
            lines.append(
                "   → Say `learn my writing style from email` to import your sent messages"
            )
    else:
        lines.append("📧 Email: ❌ not configured (needed for best style learning)")
        lines.append("   → Say `how do I set up email?` for steps")

    # Screen watcher
    if SCREEN_WATCHER_ENABLED:
        lines.append("👁️ Screen Watcher: ✅ active — learning from your typing in real time")
    else:
        lines.append("👁️ Screen Watcher: ❌ off")
        lines.append("   → Say `set SCREEN_WATCHER_ENABLED to true` then restart")

    # Training data summary
    lines.append(f"\n📊 Training samples: *{total}*")
    if total == 0:
        lines.append("⚠️ No training data yet — the bot will use a generic style until you add data.")
    elif total < 30:
        lines.append("⚡ Getting started — a few more samples will improve accuracy.")
    else:
        lines.append("✅ Enough data for accurate personality cloning.")

    lines.append("\nSay `build my style profile` to see the AI's style analysis of you.")

    return {"success": True, "text": "\n".join(lines)}
