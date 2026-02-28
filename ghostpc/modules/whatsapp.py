"""
GhostPC WhatsApp Module
Bridges to whatsapp-web.js running as a local Node.js server.
Requires: Node.js + npm install whatsapp-web.js + running bridge server.
"""

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BRIDGE_URL = "http://localhost:3099"
BRIDGE_TIMEOUT = 15


def _check_bridge() -> bool:
    """Check if the WhatsApp bridge server is running."""
    try:
        resp = requests.get(f"{BRIDGE_URL}/status", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def _bridge_error() -> dict:
    return {
        "success": False,
        "error": (
            "WhatsApp bridge is not running.\n"
            "Start it with: cd ghostpc/modules && node whatsapp_bridge.js\n"
            "Or enable it in setup.py"
        )
    }


def get_messages(contact: str, limit: int = 20) -> dict:
    """Get recent messages from a contact."""
    if not _check_bridge():
        return _bridge_error()
    try:
        resp = requests.get(
            f"{BRIDGE_URL}/messages",
            params={"contact": contact, "limit": limit},
            timeout=BRIDGE_TIMEOUT,
        )
        data = resp.json()
        messages = data.get("messages", [])

        lines = [f"💬 Messages from {contact}:\n"]
        for msg in messages:
            direction = "→" if msg.get("fromMe") else "←"
            body = msg.get("body", "")[:100]
            ts = msg.get("timestamp", "")
            lines.append(f"[{ts}] {direction} {body}")

        return {
            "success": True,
            "messages": messages,
            "text": "\n".join(lines),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_message(contact: str, message: str) -> dict:
    """Send a WhatsApp message to a contact."""
    if not _check_bridge():
        return _bridge_error()
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/send",
            json={"contact": contact, "message": message},
            timeout=BRIDGE_TIMEOUT,
        )
        data = resp.json()
        if data.get("success"):
            return {"success": True, "text": f"✅ WhatsApp message sent to {contact}"}
        return {"success": False, "error": data.get("error", "Send failed")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_unread() -> dict:
    """Get all unread WhatsApp messages."""
    if not _check_bridge():
        return _bridge_error()
    try:
        resp = requests.get(f"{BRIDGE_URL}/unread", timeout=BRIDGE_TIMEOUT)
        data = resp.json()
        chats = data.get("chats", [])

        if not chats:
            return {"success": True, "text": "✅ No unread WhatsApp messages.", "chats": []}

        lines = [f"📱 Unread WhatsApp ({len(chats)} chats):\n"]
        for chat in chats[:10]:
            name = chat.get("name", "Unknown")
            count = chat.get("unread_count", 0)
            last = chat.get("last_message", "")[:60]
            lines.append(f"• {name} ({count} unread): {last}")

        return {"success": True, "chats": chats, "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_contacts() -> dict:
    """Get WhatsApp contacts list."""
    if not _check_bridge():
        return _bridge_error()
    try:
        resp = requests.get(f"{BRIDGE_URL}/contacts", timeout=BRIDGE_TIMEOUT)
        data = resp.json()
        contacts = data.get("contacts", [])

        lines = [f"👥 WhatsApp Contacts ({len(contacts)}):\n"]
        for c in contacts[:30]:
            lines.append(f"• {c.get('name', 'Unknown')} — {c.get('number', '')}")

        return {"success": True, "contacts": contacts, "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_file_to_contact(contact: str, file_path: str, caption: str = "") -> dict:
    """Send a file to a WhatsApp contact."""
    if not _check_bridge():
        return _bridge_error()
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/send-file",
            json={"contact": contact, "file_path": file_path, "caption": caption},
            timeout=30,
        )
        data = resp.json()
        if data.get("success"):
            return {"success": True, "text": f"✅ File sent to {contact} on WhatsApp"}
        return {"success": False, "error": data.get("error", "Send failed")}
    except Exception as e:
        return {"success": False, "error": str(e)}
