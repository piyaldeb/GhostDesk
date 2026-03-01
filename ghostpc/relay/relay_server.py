"""
GhostDesk Relay Server
======================
Deploy this on a VPS / Raspberry Pi to queue Telegram commands when your main
PC is offline.  When the PC comes back online it fetches the queue, runs every
stored command, and sends you the results.

Quick start on VPS:
  pip install fastapi uvicorn requests
  export RELAY_SECRET=yoursharedsecret
  python relay_server.py          # listens on port 8765

On the PC, add to ~/.ghostdesk/.env:
  RELAY_URL=https://your.vps.ip:8765
  RELAY_SECRET=yoursharedsecret

Endpoints (all require X-GhostDesk-Secret header):
  POST /heartbeat        — PC sends this every minute to mark itself online
  GET  /status           — show whether PC is online and how many messages are queued
  GET  /queue            — PC fetches queued messages on startup
  POST /dequeue          — PC tells relay which messages it processed (by ID)
  POST /queue_message    — manually enqueue a command (for testing)
"""

import os
import time
import uuid

try:
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError:
    raise SystemExit("Install dependencies: pip install fastapi uvicorn")

# ─── Config ───────────────────────────────────────────────────────────────────

SECRET  = os.getenv("RELAY_SECRET", "changeme")
PC_OFFLINE_THRESHOLD = 90  # seconds without heartbeat → PC considered offline
MAX_QUEUE = 200             # max queued messages

# ─── State (in-memory — restart clears queue; use SQLite for persistence) ─────

_last_heartbeat: float = 0.0
_queue: list = []           # [{"id": str, "text": str, "sender": str, "ts": float}]

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="GhostDesk Relay", version="1.0")


def _auth(secret: str):
    if secret != SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: wrong RELAY_SECRET")


# ─── Heartbeat ────────────────────────────────────────────────────────────────

@app.post("/heartbeat")
async def heartbeat(
    request: Request,
    x_ghostdesk_secret: str = Header(...),
):
    """PC calls this every minute to register itself as online."""
    _auth(x_ghostdesk_secret)
    global _last_heartbeat
    _last_heartbeat = time.time()
    return {"ok": True, "queued": len(_queue)}


# ─── Status ───────────────────────────────────────────────────────────────────

@app.get("/status")
async def status(x_ghostdesk_secret: str = Header(...)):
    _auth(x_ghostdesk_secret)
    age = time.time() - _last_heartbeat if _last_heartbeat else None
    return {
        "pc_online": _last_heartbeat > 0 and age < PC_OFFLINE_THRESHOLD,
        "last_heartbeat_age_s": round(age, 1) if age is not None else None,
        "queued": len(_queue),
    }


# ─── Queue ────────────────────────────────────────────────────────────────────

@app.get("/queue")
async def get_queue(x_ghostdesk_secret: str = Header(...)):
    """PC fetches all pending messages on startup."""
    _auth(x_ghostdesk_secret)
    return {"messages": _queue, "count": len(_queue)}


@app.post("/dequeue")
async def dequeue(request: Request, x_ghostdesk_secret: str = Header(...)):
    """PC tells relay which messages have been processed (remove by ID)."""
    _auth(x_ghostdesk_secret)
    global _queue
    data = await request.json()
    ids = set(data.get("ids", []))
    before = len(_queue)
    _queue = [m for m in _queue if m["id"] not in ids]
    return {"ok": True, "removed": before - len(_queue), "remaining": len(_queue)}


@app.post("/queue_message")
async def queue_message(request: Request, x_ghostdesk_secret: str = Header(...)):
    """
    Manually enqueue a command (useful for testing or a lightweight
    Telegram bot proxy that runs on the VPS while the PC is offline).
    """
    _auth(x_ghostdesk_secret)
    if len(_queue) >= MAX_QUEUE:
        raise HTTPException(status_code=429, detail="Queue full")
    data = await request.json()
    msg = {
        "id":     str(uuid.uuid4()),
        "text":   data.get("text", "").strip(),
        "sender": data.get("sender", "relay"),
        "ts":     time.time(),
    }
    if not msg["text"]:
        raise HTTPException(status_code=400, detail="text is required")
    _queue.append(msg)
    return {"ok": True, "id": msg["id"], "queued": len(_queue)}


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("RELAY_PORT", "8765"))
    print(f"GhostDesk Relay listening on 0.0.0.0:{port}")
    print(f"Secret: {'(set)' if SECRET != 'changeme' else '⚠️  USING DEFAULT — change RELAY_SECRET!'}")
    uvicorn.run(app, host="0.0.0.0", port=port)
