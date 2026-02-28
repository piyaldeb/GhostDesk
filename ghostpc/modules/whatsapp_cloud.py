"""
GhostDesk WhatsApp Cloud API Module
Uses Meta's WhatsApp Business Cloud API — no Node.js, no QR code.

Setup: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
  1. Create Meta App → WhatsApp → API Setup
  2. Copy Access Token + Phone Number ID → ghostdesk-setup
  3. (Optional) Set webhook URL to receive incoming messages
"""

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"


def _cfg():
    from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_ID
    return WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_ID


def _headers() -> dict:
    token, _ = _cfg()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _normalize_number(number: str) -> str:
    """Strip spaces/dashes, ensure no leading +."""
    return number.replace(" ", "").replace("-", "").replace("+", "").strip()


# ─── Send ─────────────────────────────────────────────────────────────────────

def send_message(contact: str, message: str) -> dict:
    """
    Send a WhatsApp message via Cloud API.
    `contact` can be a phone number (e.g. '8801712345678') or a saved contact name.
    """
    _, phone_id = _cfg()
    if not phone_id:
        return {"success": False, "error": "WHATSAPP_PHONE_ID not set. Run ghostdesk-setup."}

    number = _normalize_number(contact)

    try:
        resp = requests.post(
            f"{GRAPH_URL}/{phone_id}/messages",
            headers=_headers(),
            json={
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": message},
            },
            timeout=15,
        )
        data = resp.json()
        if resp.ok and data.get("messages"):
            msg_id = data["messages"][0].get("id", "")
            return {
                "success": True,
                "text": f"✅ WhatsApp message sent to {contact} (id: {msg_id})",
            }
        err = data.get("error", {}).get("message", str(data))
        return {"success": False, "error": f"Send failed: {err}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_file_to_contact(contact: str, file_path: str, caption: str = "") -> dict:
    """Upload a file and send it as a WhatsApp document."""
    _, phone_id = _cfg()
    if not phone_id:
        return {"success": False, "error": "WHATSAPP_PHONE_ID not set."}

    import os
    from pathlib import Path

    number = _normalize_number(contact)
    fp = Path(file_path)
    if not fp.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        # Step 1: upload media
        token, _ = _cfg()
        with open(fp, "rb") as f:
            upload_resp = requests.post(
                f"{GRAPH_URL}/{phone_id}/media",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (fp.name, f, _mime_type(fp))},
                data={"messaging_product": "whatsapp"},
                timeout=60,
            )
        if not upload_resp.ok:
            return {"success": False, "error": f"Upload failed: {upload_resp.text}"}

        media_id = upload_resp.json().get("id")

        # Step 2: send document
        resp = requests.post(
            f"{GRAPH_URL}/{phone_id}/messages",
            headers=_headers(),
            json={
                "messaging_product": "whatsapp",
                "to": number,
                "type": "document",
                "document": {
                    "id": media_id,
                    "caption": caption,
                    "filename": fp.name,
                },
            },
            timeout=15,
        )
        if resp.ok:
            return {"success": True, "text": f"✅ File sent to {contact} on WhatsApp"}
        return {"success": False, "error": resp.text}

    except Exception as e:
        return {"success": False, "error": str(e)}


def _mime_type(path) -> str:
    import mimetypes
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_messages(contact: str, limit: int = 20) -> dict:
    """
    Fetch recent messages with a contact from GhostDesk's local conversation log.
    (Cloud API does not support reading message history — messages are logged locally
    as they arrive via webhook.)
    """
    try:
        from core.memory import get_conversation_history
        msgs = get_conversation_history(contact, "whatsapp", days=7)
        if not msgs:
            return {
                "success": True,
                "messages": [],
                "text": f"No logged messages with {contact} in the last 7 days.",
            }

        lines = [f"💬 Messages with {contact}:\n"]
        for m in msgs[-limit:]:
            arrow = "→" if m["direction"] == "out" else "←"
            ts = m["timestamp"][:16].replace("T", " ")
            lines.append(f"[{ts}] {arrow} {m['message'][:120]}")

        return {"success": True, "messages": msgs, "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_unread() -> dict:
    """Return recently received (incoming) WhatsApp messages from the local log."""
    try:
        from datetime import datetime, timedelta
        from core.memory import get_conversation_history
        import sqlite3
        from config import DB_PATH

        since = (datetime.now() - timedelta(hours=24)).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT contact, message, timestamp FROM conversations
                   WHERE source='whatsapp' AND direction='in' AND timestamp >= ?
                   ORDER BY timestamp DESC LIMIT 30""",
                (since,)
            ).fetchall()

        if not rows:
            return {"success": True, "text": "✅ No unread WhatsApp messages in the last 24h.", "chats": []}

        lines = [f"📱 Recent WhatsApp messages ({len(rows)}):\n"]
        for r in rows:
            ts = r["timestamp"][:16].replace("T", " ")
            lines.append(f"[{ts}] {r['contact']}: {r['message'][:80]}")

        return {"success": True, "chats": [dict(r) for r in rows], "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Webhook handler (called from main.py aiohttp server) ────────────────────

def parse_incoming_webhook(payload: dict) -> list[dict]:
    """
    Parse a WhatsApp Cloud API webhook POST body.
    Returns list of {contact, message, timestamp} dicts.
    """
    messages = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") == "text":
                        messages.append({
                            "contact": msg.get("from", ""),
                            "message": msg["text"].get("body", ""),
                            "timestamp": msg.get("timestamp", ""),
                        })
    except Exception as e:
        logger.error(f"Webhook parse error: {e}")
    return messages
