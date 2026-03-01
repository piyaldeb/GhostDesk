"""
GhostDesk Enhanced Screen Watcher

Stateful, multi-category proactive monitor:
- 8-category structured AI analysis per frame (replaces simple ALERT/NORMAL prompt)
- Real battery monitoring via psutil (no AI guessing)
- Mouse idle detection (runs inside the watcher loop — no extra thread)
- Duration-based alerts: error dialog 5 min, form+idle 3 min, media paused 20 min
- Immediate alerts: download complete, incoming call, build finished, notification, security, battery
- Inline keyboard action buttons: Search Fix, Move File, Dismiss
- Priority contact detection for notifications (PRIORITY_CONTACTS config)
"""

import asyncio
import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Set

import psutil
import pyautogui
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_watcher_thread: Optional[threading.Thread] = None
_watcher_running = False
_event_loop: Optional[asyncio.AbstractEventLoop] = None
_bot_app = None          # stored on first start_screen_watcher call
_owner_chat_id: int = 0  # stored on first start_screen_watcher call

# ─── Duration Thresholds ──────────────────────────────────────────────────────

ERROR_PERSIST_SECONDS = 5 * 60    # 5 minutes — error dialog must persist this long before alerting
MEDIA_PAUSE_SECONDS   = 20 * 60   # 20 minutes — media paused this long triggers alert
BATTERY_THRESHOLD     = 10        # percent — alert when unplugged and below this


# ─── State Tracking ───────────────────────────────────────────────────────────

@dataclass
class ScreenState:
    # Error dialog
    error_first_seen: Optional[float] = None
    error_text:       str = ""
    error_alerted:    bool = False   # prevent re-alerting same dialog

    # Form + idle
    form_first_seen: Optional[float] = None
    form_app:        str = ""
    form_alerted:    bool = False

    # Media pause duration
    media_paused_since: Optional[float] = None
    media_app:          str = ""
    media_title:        str = ""
    media_alerted:      bool = False

    # Battery (psutil)
    battery_alerted: bool = False

    # Notification dedup — only alert when content changes
    last_notification_key: str = ""

    # Download dedup — set of filenames already alerted this session
    alerted_downloads: Set[str] = field(default_factory=set)

    # Build dedup — store tick of last build alert so we alert once per build event
    last_build_tick: int = -1

    # Mouse idle detection
    last_mouse_pos: tuple = field(default_factory=lambda: (0, 0))
    idle_since:     Optional[float] = None

    # Frame counter (increments each watcher tick)
    tick: int = 0


# ─── Structured AI Prompt ─────────────────────────────────────────────────────

ANALYSIS_PROMPT = """Analyze this desktop screenshot. Return ONLY a JSON object — no other text, no markdown.

{
  "error_dialog":      {"present": false, "text": ""},
  "download_complete": {"present": false, "filename": ""},
  "form_open":         {"present": false, "app": "", "incomplete": false},
  "incoming_call":     {"present": false, "app": "", "caller": ""},
  "notification":      {"present": false, "app": "", "contact": "", "preview": ""},
  "build_finished":    {"present": false, "success": true, "detail": ""},
  "media_paused":      {"present": false, "app": "", "title": ""},
  "security_alert":    {"present": false, "description": ""}
}

Detection rules — only set present:true when clearly visible on screen:
- error_dialog: Windows/Mac error boxes, "not responding" title bars, crash dialogs, any error popup. text = brief description.
- download_complete: Browser download bar showing 100% or "Download complete" toast. filename = file name shown.
- form_open: Any webpage or desktop form with visible input fields. incomplete = true only if some fields are filled and others appear empty (user was mid-way through).
- incoming_call: Zoom, Teams, Meet, Skype, or any VoIP ringing notification. caller = visible name if any.
- notification: Toast/popup from WhatsApp, Gmail, Outlook, Telegram, Slack, Discord, etc. app = app name, contact = sender name, preview = message text (max 80 chars).
- build_finished: IDE terminal/build panel showing "Build succeeded", "Build failed", "Compilation complete", "0 errors" or similar. success = whether build passed. detail = short status line.
- media_paused: YouTube browser tab, VLC, Spotify, or any video/audio player that is visibly paused (shows play button, progress bar frozen). app = player name, title = content title.
- security_alert: Antivirus popup, firewall prompt, UAC elevation dialog, suspicious login prompt. description = brief summary.

Return the JSON using exact keys above. Default all values to false/"" for undetected categories."""


# ─── Empty Analysis Fallback ─────────────────────────────────────────────────

_EMPTY_ANALYSIS = {
    "error_dialog":      {"present": False, "text": ""},
    "download_complete": {"present": False, "filename": ""},
    "form_open":         {"present": False, "app": "", "incomplete": False},
    "incoming_call":     {"present": False, "app": "", "caller": ""},
    "notification":      {"present": False, "app": "", "contact": "", "preview": ""},
    "build_finished":    {"present": False, "success": True, "detail": ""},
    "media_paused":      {"present": False, "app": "", "title": ""},
    "security_alert":    {"present": False, "description": ""},
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def set_event_loop(loop: asyncio.AbstractEventLoop):
    """Register the bot's asyncio event loop (called from main.py post_init)."""
    global _event_loop
    _event_loop = loop


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _dismiss_btn(tag: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Dismiss", callback_data=f"sw_dismiss:{tag}")
    ]])


# ─── Battery Check (psutil — not AI vision) ───────────────────────────────────

def _check_battery(state: ScreenState) -> Optional[str]:
    """Return alert message if battery is critically low, else None."""
    try:
        batt = psutil.sensors_battery()
        if batt is None:
            return None
        if not batt.power_plugged and batt.percent <= BATTERY_THRESHOLD:
            if not state.battery_alerted:
                state.battery_alerted = True
                return f"Battery at {int(batt.percent)}% and unplugged — connect charger now."
        elif batt.power_plugged or batt.percent > 15:
            state.battery_alerted = False   # reset so next drop triggers again
    except Exception:
        pass
    return None


# ─── Mouse Idle Detection ─────────────────────────────────────────────────────

def _update_idle(state: ScreenState) -> float:
    """
    Check current mouse position. If unchanged since last call, accumulate idle time.
    Returns seconds since last detected user activity.
    """
    try:
        pos = pyautogui.position()
        pos_tuple = (pos.x, pos.y)
        if pos_tuple != state.last_mouse_pos:
            state.last_mouse_pos = pos_tuple
            state.idle_since = None     # movement detected — reset idle clock
        elif state.idle_since is None:
            state.idle_since = time.time()
    except Exception:
        pass
    return time.time() - state.idle_since if state.idle_since else 0.0


# ─── Structured Screenshot Analysis ──────────────────────────────────────────

def _screenshot_mime(image_path: str) -> str:
    """Return correct MIME type based on file extension."""
    ext = image_path.lower().rsplit(".", 1)[-1]
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")


def analyze_screenshot_structured(image_path: str) -> dict:
    """
    Send a screenshot to Vision AI and return the 8-category structured analysis dict.
    Falls back to _EMPTY_ANALYSIS on any error.
    """
    try:
        from config import AI_PROVIDER, CLAUDE_API_KEY, OPENAI_API_KEY, AI_MODEL

        img_b64 = _encode_image(image_path)
        mime = _screenshot_mime(image_path)

        if AI_PROVIDER == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime, "data": img_b64},
                        },
                        {"type": "text", "text": ANALYSIS_PROMPT},
                    ],
                }],
            )
            raw = response.content[0].text.strip()

        elif AI_PROVIDER == "openai":
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=AI_MODEL,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ANALYSIS_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    ],
                }],
            )
            raw = response.choices[0].message.content.strip()

        else:
            return dict(_EMPTY_ANALYSIS)

        # Strip markdown fences if the model wraps output
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw)

    except Exception as e:
        logger.warning(f"Screen analysis error: {e}")
        return dict(_EMPTY_ANALYSIS)


# Backward-compatible alias (used by legacy callers)
def analyze_screenshot(image_path: str) -> dict:
    """Legacy wrapper — returns {"is_alert": bool, "summary": str}."""
    analysis = analyze_screenshot_structured(image_path)
    summary = _summary_from_analysis(analysis)
    is_alert = any(
        analysis.get(k, {}).get("present")
        for k in ("error_dialog", "security_alert", "incoming_call")
    )
    return {"is_alert": is_alert, "summary": summary}


# ─── DB Summary Builder ───────────────────────────────────────────────────────

def _summary_from_analysis(a: dict) -> str:
    """Build a human-readable one-liner for the screen_log DB entry."""
    parts = []
    if a.get("error_dialog", {}).get("present"):
        parts.append(f"Error: {a['error_dialog']['text']}")
    if a.get("download_complete", {}).get("present"):
        parts.append(f"Download: {a['download_complete']['filename']}")
    if a.get("form_open", {}).get("present"):
        parts.append(f"Form open ({a['form_open']['app']})")
    if a.get("incoming_call", {}).get("present"):
        ic = a["incoming_call"]
        parts.append(f"Call: {ic['app']} from {ic['caller']}")
    if a.get("notification", {}).get("present"):
        n = a["notification"]
        parts.append(f"Notification from {n['contact']} ({n['app']})")
    if a.get("build_finished", {}).get("present"):
        status = "OK" if a["build_finished"]["success"] else "FAILED"
        parts.append(f"Build {status}: {a['build_finished']['detail']}")
    if a.get("media_paused", {}).get("present"):
        mp = a["media_paused"]
        parts.append(f"Media paused: {mp['title']} ({mp['app']})")
    if a.get("security_alert", {}).get("present"):
        parts.append(f"Security: {a['security_alert']['description']}")
    return "; ".join(parts) if parts else "Normal activity"


# ─── Alert Processing (state machine) ────────────────────────────────────────

def _process_analysis(
    analysis: dict,
    state: ScreenState,
    idle_secs: float,
    idle_threshold: int,
    priority_contacts: list,
) -> list:
    """
    Compare current frame analysis against accumulated ScreenState.
    Returns a list of alert dicts: {"text", "keyboard", "photo", "priority"}.
    """
    now = time.time()
    alerts = []

    # ── 1. Error Dialog (5-min persistence) ──────────────────────────────────
    ed = analysis.get("error_dialog", {})
    if ed.get("present"):
        err_text = ed.get("text", "Unknown error")
        if state.error_first_seen is None:
            state.error_first_seen = now
            state.error_text = err_text
            state.error_alerted = False
        elif (now - state.error_first_seen) >= ERROR_PERSIST_SECONDS and not state.error_alerted:
            state.error_alerted = True
            err_safe = err_text[:45]   # callback_data max 64 bytes
            alerts.append({
                "text": f"Error dialog has been open for 5+ minutes:\n_{err_text}_\n\nWant me to search for a fix?",
                "keyboard": InlineKeyboardMarkup([[
                    InlineKeyboardButton("Search Fix", callback_data=f"sw_fix_error:{err_safe}"),
                    InlineKeyboardButton("Dismiss",    callback_data="sw_dismiss:error"),
                ]]),
                "photo": True,
                "priority": False,
            })
    else:
        state.error_first_seen = None
        state.error_alerted = False
        state.error_text = ""

    # ── 2. Download Complete (immediate, deduped by filename) ─────────────────
    dc = analysis.get("download_complete", {})
    if dc.get("present"):
        fname = (dc.get("filename") or "file").strip()
        if fname not in state.alerted_downloads:
            state.alerted_downloads.add(fname)
            fname_safe = fname[:45]
            alerts.append({
                "text": f"Download complete: *{fname}*\n\nMove it to your Projects folder?",
                "keyboard": InlineKeyboardMarkup([[
                    InlineKeyboardButton("Move File", callback_data=f"sw_move_download:{fname_safe}"),
                    InlineKeyboardButton("Dismiss",   callback_data="sw_dismiss:download"),
                ]]),
                "photo": False,
                "priority": False,
            })

    # ── 3. Form Open + User Idle ──────────────────────────────────────────────
    fo = analysis.get("form_open", {})
    if fo.get("present") and fo.get("incomplete"):
        if state.form_first_seen is None:
            state.form_first_seen = now
            state.form_app = fo.get("app") or "an application"
            state.form_alerted = False
        if idle_secs >= idle_threshold and not state.form_alerted:
            state.form_alerted = True
            idle_min = max(1, int(idle_secs // 60))
            alerts.append({
                "text": (
                    f"You left a partially-filled form open in *{state.form_app}* "
                    f"and have been idle for {idle_min}+ minute(s). Do you want to come back to it?"
                ),
                "keyboard": _dismiss_btn("form"),
                "photo": True,
                "priority": False,
            })
    else:
        state.form_first_seen = None
        state.form_alerted = False

    # ── 4. Incoming Call (immediate) ──────────────────────────────────────────
    ic = analysis.get("incoming_call", {})
    if ic.get("present"):
        app    = ic.get("app") or "your PC"
        caller = ic.get("caller") or ""
        caller_str = f" from *{caller}*" if caller else ""
        alerts.append({
            "text": f"Incoming call on *{app}*{caller_str}",
            "keyboard": _dismiss_btn("call"),
            "photo": False,
            "priority": False,
        })

    # ── 5. Notification (mirror / priority alert, deduped by content) ─────────
    notif = analysis.get("notification", {})
    if notif.get("present"):
        n_app     = notif.get("app") or ""
        n_contact = notif.get("contact") or ""
        n_preview = notif.get("preview") or ""
        notif_key = f"{n_app}:{n_contact}:{n_preview[:40]}"
        if notif_key != state.last_notification_key:
            state.last_notification_key = notif_key
            is_priority = any(
                p.strip().lower() in n_contact.lower()
                for p in priority_contacts if p.strip()
            )
            contact_str = f" from *{n_contact}*" if n_contact else ""
            app_str     = f" ({n_app})" if n_app else ""
            preview_str = f"\n\n_{n_preview}_" if n_preview else ""
            prefix = "*🔴 PRIORITY ALERT*\n\n" if is_priority else ""
            alerts.append({
                "text": f"{prefix}Notification{contact_str}{app_str}{preview_str}",
                "keyboard": _dismiss_btn("notif"),
                "photo": False,
                "priority": is_priority,
            })
    else:
        state.last_notification_key = ""

    # ── 6. Build Finished (immediate, deduped per tick) ───────────────────────
    bf = analysis.get("build_finished", {})
    if bf.get("present") and state.last_build_tick != state.tick:
        state.last_build_tick = state.tick
        success    = bf.get("success", True)
        detail     = bf.get("detail") or ""
        icon       = "Build succeeded" if success else "Build FAILED"
        detail_str = f"\n_{detail}_" if detail else ""
        alerts.append({
            "text": f"{icon}{detail_str}",
            "keyboard": _dismiss_btn("build"),
            "photo": False,
            "priority": not success,   # failed builds get priority flag
        })

    # ── 7. Media Paused (20-min duration) ────────────────────────────────────
    mp = analysis.get("media_paused", {})
    if mp.get("present"):
        if state.media_paused_since is None:
            state.media_paused_since = now
            state.media_app   = mp.get("app") or "media player"
            state.media_title = mp.get("title") or ""
            state.media_alerted = False
        elif (now - state.media_paused_since) >= MEDIA_PAUSE_SECONDS and not state.media_alerted:
            state.media_alerted = True
            title_str = f' "{state.media_title}"' if state.media_title else ""
            alerts.append({
                "text": f"*{state.media_app}*{title_str} has been paused for 20+ minutes. Did you forget it?",
                "keyboard": _dismiss_btn("media"),
                "photo": False,
                "priority": False,
            })
    else:
        state.media_paused_since = None
        state.media_alerted = False

    # ── 8. Security Alert (immediate) ────────────────────────────────────────
    sa = analysis.get("security_alert", {})
    if sa.get("present"):
        desc = sa.get("description") or "Unknown security event"
        alerts.append({
            "text": f"*SECURITY ALERT*\n\n{desc}",
            "keyboard": _dismiss_btn("security"),
            "photo": True,
            "priority": True,
        })

    return alerts


# ─── Alert Sender ─────────────────────────────────────────────────────────────

async def _send_alert(bot_app, chat_id: int, alert: dict, img_path: str):
    text     = alert.get("text", "")
    keyboard = alert.get("keyboard")
    try:
        await bot_app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        if alert.get("photo") and img_path:
            with open(img_path, "rb") as f:
                await bot_app.bot.send_photo(chat_id=chat_id, photo=f)
    except Exception as e:
        logger.error(f"Alert send failed: {e}")


# ─── Personality Signal Capture ───────────────────────────────────────────────

def _capture_personality_signal(analysis: dict) -> None:
    """
    If the screen analysis reveals outgoing text (notification preview or form content),
    store it as personality training data. Called every 10 watcher ticks.
    """
    # Notification preview — e.g. user is about to send a message
    notif = analysis.get("notification", {})
    if notif.get("present") and notif.get("preview"):
        preview = notif["preview"].strip()
        app = notif.get("app", "")
        if len(preview) > 20:
            try:
                from modules.personality import store_screen_behavior
                store_screen_behavior(preview, app)
            except Exception:
                pass


# ─── Watcher Loop ─────────────────────────────────────────────────────────────

def _watcher_loop(bot_app, owner_chat_id: int, interval: int):
    global _watcher_running
    from modules.pc_control import screenshot
    from core.memory import log_screenshot
    from config import PRIORITY_CONTACTS, SCREEN_IDLE_SECONDS

    priority_contacts = [p.strip() for p in PRIORITY_CONTACTS.split(",") if p.strip()]
    state = ScreenState()

    logger.info(f"Screen watcher started — interval: {interval}s, idle threshold: {SCREEN_IDLE_SECONDS}s")

    while _watcher_running:
        state.tick += 1

        # ── Battery check (psutil — fast, no screenshot needed) ──────────────
        batt_msg = _check_battery(state)
        if batt_msg and bot_app and _event_loop:
            future = asyncio.run_coroutine_threadsafe(
                bot_app.bot.send_message(owner_chat_id, f"🔋 {batt_msg}"),
                _event_loop,
            )
            try:
                future.result(timeout=10)
            except Exception as e:
                logger.error(f"Battery alert error: {e}")

        # ── Mouse idle detection ──────────────────────────────────────────────
        idle_secs = _update_idle(state)

        # ── Screenshot + structured AI analysis ───────────────────────────────
        try:
            result = screenshot()
            if result.get("success") and result.get("file_path"):
                img_path = result["file_path"]
                analysis = analyze_screenshot_structured(img_path)
                log_screenshot(img_path, _summary_from_analysis(analysis))

                # ── Personality behavior capture (every 10 ticks to reduce noise) ─
                if state.tick % 10 == 0:
                    try:
                        from config import PERSONALITY_CLONE_ENABLED
                        if PERSONALITY_CLONE_ENABLED:
                            _capture_personality_signal(analysis)
                    except Exception:
                        pass

                alerts = _process_analysis(
                    analysis, state, idle_secs, SCREEN_IDLE_SECONDS, priority_contacts
                )
                for alert in alerts:
                    if bot_app and _event_loop:
                        future = asyncio.run_coroutine_threadsafe(
                            _send_alert(bot_app, owner_chat_id, alert, img_path),
                            _event_loop,
                        )
                        try:
                            future.result(timeout=15)
                        except Exception as e:
                            logger.error(f"Alert delivery error: {e}")

        except Exception as e:
            logger.error(f"Watcher loop error: {e}")

        time.sleep(interval)

    logger.info("Screen watcher stopped.")


# ─── Public API ───────────────────────────────────────────────────────────────

def start_screen_watcher(bot_app, owner_chat_id: int, interval: int = 30):
    """Launch the background screen watcher thread."""
    global _watcher_thread, _watcher_running, _bot_app, _owner_chat_id
    if _watcher_running:
        return {"success": False, "text": "Screen watcher is already running."}

    # Persist for agent-callable wrappers
    _bot_app = bot_app
    _owner_chat_id = owner_chat_id

    _watcher_running = True
    _watcher_thread = threading.Thread(
        target=_watcher_loop,
        args=(bot_app, owner_chat_id, interval),
        daemon=True,
    )
    _watcher_thread.start()
    logger.info("Screen watcher thread launched.")
    return {"success": True, "text": f"Screen watcher started (checking every {interval}s)."}


# ─── Agent-callable wrappers (no bot_app/chat_id needed) ─────────────────────

def start_watcher(interval: int = 30) -> dict:
    """Agent-callable: start the screen watcher using the already-configured bot."""
    if _bot_app is None:
        return {"success": False, "error": "Bot not initialised yet — GhostDesk must be running first."}
    return start_screen_watcher(_bot_app, _owner_chat_id, interval)


def stop_watcher() -> dict:
    """Agent-callable: stop the screen watcher."""
    return stop_screen_watcher()


def watcher_status() -> dict:
    """Agent-callable: check whether the screen watcher is currently running."""
    return {"success": True, "running": _watcher_running,
            "text": f"Screen watcher is {'running' if _watcher_running else 'stopped'}."}


def stop_screen_watcher() -> dict:
    """Stop the screen watcher gracefully."""
    global _watcher_running
    if not _watcher_running:
        return {"success": False, "text": "Screen watcher is not running."}
    _watcher_running = False
    return {"success": True, "text": "Screen watcher stopped."}


def query_screen_history(time_query: str = "") -> dict:
    """
    Return recent screen activity log entries.
    Answers queries like: "what was on my screen at 3pm?"
    """
    try:
        from core.memory import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT timestamp, ai_summary FROM screen_log ORDER BY timestamp DESC LIMIT 60"
            ).fetchall()

        if not rows:
            return {
                "success": True,
                "text": (
                    "No screen history yet.\n"
                    "Enable SCREEN_WATCHER_ENABLED=true in ~/.ghostdesk/.env to start recording."
                ),
            }

        lines = []
        for r in rows[:40]:
            ts = r["timestamp"][:16].replace("T", " ")
            summary = r["ai_summary"] or "(no summary)"
            lines.append(f"[{ts}] {summary}")

        return {
            "success": True,
            "text": "Screen activity log (most recent first):\n\n" + "\n".join(lines),
            "count": len(rows),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
