"""
GhostPC Offline Queue
Sends periodic heartbeats to a relay server (VPS/Pi) and fetches any messages
that were queued while the PC was offline.

Setup:
  1. Deploy ghostpc/relay/relay_server.py on a VPS/Raspberry Pi.
  2. Set RELAY_URL=https://your.vps.com:8765 in ~/.ghostdesk/.env
  3. Set RELAY_SECRET=yoursharedsecret in BOTH the VPS .env and PC .env
  4. Start the PC — heartbeats begin automatically; queue is fetched on each startup.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _headers() -> dict:
    from config import RELAY_SECRET
    return {
        "X-GhostDesk-Secret": RELAY_SECRET,
        "Content-Type": "application/json",
    }


def send_heartbeat() -> bool:
    """POST /heartbeat to the relay. Returns True on success."""
    try:
        from config import RELAY_URL, RELAY_SECRET
        if not RELAY_URL or not RELAY_SECRET:
            return False
        import requests
        r = requests.post(
            f"{RELAY_URL}/heartbeat",
            headers=_headers(),
            json={"ts": time.time()},
            timeout=5,
        )
        return r.status_code == 200
    except Exception as exc:
        logger.debug(f"Heartbeat failed: {exc}")
        return False


def fetch_queued_messages() -> list:
    """
    GET /queue from the relay.
    Returns a list of message dicts: [{"id": "...", "text": "...", "ts": ...}, ...]
    Returns [] on error or if relay is not configured.
    """
    try:
        from config import RELAY_URL, RELAY_SECRET
        if not RELAY_URL or not RELAY_SECRET:
            return []
        import requests
        r = requests.get(
            f"{RELAY_URL}/queue",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("messages", [])
        return []
    except Exception as exc:
        logger.debug(f"Queue fetch failed: {exc}")
        return []


def dequeue_messages(message_ids: list) -> bool:
    """POST /dequeue to tell the relay to remove processed messages."""
    if not message_ids:
        return True
    try:
        from config import RELAY_URL, RELAY_SECRET
        if not RELAY_URL or not RELAY_SECRET:
            return False
        import requests
        r = requests.post(
            f"{RELAY_URL}/dequeue",
            headers=_headers(),
            json={"ids": message_ids},
            timeout=5,
        )
        return r.status_code == 200
    except Exception as exc:
        logger.debug(f"Dequeue failed: {exc}")
        return False


# ─── Background Heartbeat Thread ──────────────────────────────────────────────

_heartbeat_running = False
_heartbeat_thread: Optional[threading.Thread] = None


def start_heartbeat(interval: int = 60):
    """
    Start a daemon thread that sends heartbeats every `interval` seconds.
    Idempotent — calling again while already running is a no-op.
    """
    global _heartbeat_running, _heartbeat_thread
    if _heartbeat_running:
        return

    _heartbeat_running = True

    def _loop():
        while _heartbeat_running:
            send_heartbeat()
            time.sleep(interval)

    _heartbeat_thread = threading.Thread(
        target=_loop, daemon=True, name="ghostdesk-heartbeat"
    )
    _heartbeat_thread.start()
    logger.info(f"Relay heartbeat started (every {interval}s → {_get_relay_url()})")


def stop_heartbeat():
    """Stop the heartbeat thread."""
    global _heartbeat_running
    _heartbeat_running = False


def _get_relay_url() -> str:
    try:
        from config import RELAY_URL
        return RELAY_URL or "(not configured)"
    except Exception:
        return "(not configured)"
