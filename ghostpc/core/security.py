"""
GhostPC Security Layer
Permission tiers for all module functions, action audit log, and PIN verification.

Tiers:
  SAFE     (0) — read-only / status queries — always allowed, logged if SECURITY_LOG_ENABLED
  MODERATE (1) — writes, sends, automation — allowed, logged
  DANGEROUS(2) — destructive/irreversible — allowed, logged prominently (existing confirm UX)
  CRITICAL (3) — restart / shutdown — blocked until PIN session is active
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Permission Tier Constants ────────────────────────────────────────────────

SAFE      = 0
MODERATE  = 1
DANGEROUS = 2
CRITICAL  = 3

_TIER_NAMES = {SAFE: "SAFE", MODERATE: "MODERATE", DANGEROUS: "DANGEROUS", CRITICAL: "CRITICAL"}


# ─── Function → Tier Map ──────────────────────────────────────────────────────

_TIER_MAP: dict = {
    # ── pc_control — read ops ──────────────────────────────────────────────────
    "pc_control.screenshot":        SAFE,
    "pc_control.get_open_apps":     SAFE,
    "pc_control.get_system_stats":  SAFE,
    "pc_control.get_system_info":   SAFE,
    "pc_control.get_disk_info":     SAFE,
    "pc_control.get_network_info":  SAFE,
    "pc_control.ping":              SAFE,
    "pc_control.get_battery_info":  SAFE,
    "pc_control.get_clipboard":     SAFE,
    "pc_control.list_windows":      SAFE,
    "pc_control.list_services":     SAFE,
    "pc_control.get_processes":     SAFE,
    "pc_control.get_env_var":       SAFE,
    "pc_control.check_for_updates": SAFE,
    # ── pc_control — action ops ────────────────────────────────────────────────
    "pc_control.open_app":          MODERATE,
    "pc_control.close_app":         MODERATE,
    "pc_control.type_text":         MODERATE,
    "pc_control.press_key":         MODERATE,
    "pc_control.click":             MODERATE,
    "pc_control.move_mouse":        MODERATE,
    "pc_control.focus_window":      MODERATE,
    "pc_control.minimize_window":   MODERATE,
    "pc_control.maximize_window":   MODERATE,
    "pc_control.set_clipboard":     MODERATE,
    "pc_control.open_folder":       MODERATE,
    "pc_control.search_app":        MODERATE,
    "pc_control.install_app":       MODERATE,
    "pc_control.update_ghostdesk":  MODERATE,
    "pc_control.enable_autostart":  MODERATE,
    "pc_control.disable_autostart": MODERATE,
    "pc_control.set_env_var":       MODERATE,
    "pc_control.lock_pc":           MODERATE,
    # ── pc_control — dangerous ops ─────────────────────────────────────────────
    "pc_control.kill_process":      DANGEROUS,
    "pc_control.run_command":       DANGEROUS,
    "pc_control.sleep_pc":          DANGEROUS,
    "pc_control.hibernate_pc":      DANGEROUS,
    "pc_control.empty_recycle_bin": DANGEROUS,
    "pc_control.manage_service":    DANGEROUS,
    # ── pc_control — critical ops (require PIN) ────────────────────────────────
    "pc_control.restart_pc":        CRITICAL,
    "pc_control.shutdown_pc":       CRITICAL,

    # ── file_system ────────────────────────────────────────────────────────────
    "file_system.find_file":            SAFE,
    "file_system.list_files":           SAFE,
    "file_system.read_file":            SAFE,
    "file_system.send_file_to_telegram": SAFE,
    "file_system.zip_folder":           MODERATE,
    "file_system.move_file":            MODERATE,
    "file_system.delete_file":          DANGEROUS,

    # ── email ──────────────────────────────────────────────────────────────────
    "email.get_emails":   SAFE,
    "email.send_email":   MODERATE,
    "email.reply_email":  MODERATE,

    # ── whatsapp ───────────────────────────────────────────────────────────────
    "whatsapp.get_messages":  SAFE,
    "whatsapp.get_unread":    SAFE,
    "whatsapp.send_message":  MODERATE,

    # ── document ───────────────────────────────────────────────────────────────
    "document.read_excel":          SAFE,
    "document.read_pdf":            SAFE,
    "document.read_google_sheet":   SAFE,
    "document.generate_report":     MODERATE,
    "document.write_excel":         MODERATE,
    "document.update_cell":         MODERATE,
    "document.write_google_sheet":  MODERATE,
    "document.update_google_cell":  MODERATE,
    "document.create_pdf":          MODERATE,
    "document.merge_pdfs":          MODERATE,
    "document.fill_form":           MODERATE,

    # ── browser ────────────────────────────────────────────────────────────────
    "browser.get_page_text":    SAFE,
    "browser.search_web":       SAFE,
    "browser.scrape_page":      SAFE,
    "browser.open_url":         MODERATE,
    "browser.fill_form_on_web": MODERATE,
    "browser.click_element":    MODERATE,

    # ── google_services — read ops ─────────────────────────────────────────────
    "google_services.list_drive_files":    SAFE,
    "google_services.search_drive":        SAFE,
    "google_services.list_calendar_events": SAFE,
    "google_services.get_calendar_event":  SAFE,
    "google_services.read_google_doc":     SAFE,
    "google_services.get_gmail_messages":  SAFE,
    "google_services.get_gmail_full_body": SAFE,
    "google_services.list_google_contacts": SAFE,
    # ── google_services — write ops ────────────────────────────────────────────
    "google_services.download_from_drive":    MODERATE,
    "google_services.upload_to_drive":        MODERATE,
    "google_services.create_calendar_event":  MODERATE,
    "google_services.append_to_google_doc":   MODERATE,
    "google_services.create_google_doc":      MODERATE,
    "google_services.send_gmail":             MODERATE,
    "google_services.reply_gmail":            MODERATE,
    # ── google_services — delete ops ──────────────────────────────────────────
    "google_services.delete_drive_file":      DANGEROUS,
    "google_services.delete_calendar_event":  DANGEROUS,

    # ── memory ─────────────────────────────────────────────────────────────────
    "memory.get_notes":           SAFE,
    "memory.search_memory":       SAFE,
    "memory.save_note":           MODERATE,
    "memory.save_api_credential": MODERATE,

    # ── scheduler ──────────────────────────────────────────────────────────────
    "scheduler.list_schedules":  SAFE,
    "scheduler.create_schedule": MODERATE,
    "scheduler.delete_schedule": DANGEROUS,

    # ── workflow ───────────────────────────────────────────────────────────────
    "workflow.list_workflows_text":             SAFE,
    "workflow.create_workflow_from_description": MODERATE,
    "workflow.run_workflow_now":                MODERATE,
    "workflow.delete_workflow_by_id":           DANGEROUS,

    # ── screen_watcher ─────────────────────────────────────────────────────────
    "screen_watcher.query_screen_history": SAFE,
    "screen_watcher.watcher_status":       SAFE,
    "screen_watcher.start_watcher":        MODERATE,
    "screen_watcher.stop_watcher":         MODERATE,

    # ── personality ────────────────────────────────────────────────────────────
    "personality.get_personality_status":      SAFE,
    "personality.get_ghost_replies":           SAFE,
    "personality.get_ghost_sessions":          SAFE,
    "personality.build_contact_profile":       SAFE,
    "personality.draft_reply":                 SAFE,
    "personality.refine_reply":                SAFE,
    "personality.generate_reply_as_user":      MODERATE,
    "personality.enable_ghost_mode":           MODERATE,
    "personality.disable_ghost_mode":          MODERATE,
    "personality.learn_from_sent_emails":      MODERATE,
    "personality.learn_from_whatsapp_export":  MODERATE,
    "personality.setup_personality":           MODERATE,

    # ── voice / media ──────────────────────────────────────────────────────────
    "voice.transcribe_voice":  SAFE,
    "voice.text_to_speech":    MODERATE,
    "media.get_current_playing": SAFE,
    "media.play_media":          MODERATE,
    "media.pause":               MODERATE,

    # ── api_connector ──────────────────────────────────────────────────────────
    "api_connector.call_api":           MODERATE,
    "api_connector.call_api_with_auth": MODERATE,

    # ── config_manager ─────────────────────────────────────────────────────────
    "config_manager.get_config_status": SAFE,
    "config_manager.get_setup_guide":   SAFE,
    "config_manager.suggest_setup":     SAFE,
    "config_manager.get_env_path_info": SAFE,
    "config_manager.set_config":        MODERATE,

    # ── telegram (internal) ────────────────────────────────────────────────────
    "telegram.send_message": SAFE,
    "telegram.send_file":    SAFE,
}


def get_tier(module: str, function: str) -> int:
    """Return the permission tier for a module.function pair. Defaults to MODERATE."""
    return _TIER_MAP.get(f"{module}.{function}", MODERATE)


def get_tier_name(tier: int) -> str:
    return _TIER_NAMES.get(tier, "UNKNOWN")


# ─── SQLite Audit Log ─────────────────────────────────────────────────────────

_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS action_audit (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    module    TEXT    NOT NULL,
    function  TEXT    NOT NULL,
    args      TEXT,
    tier      TEXT    NOT NULL,
    outcome   TEXT    NOT NULL,
    note      TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    from config import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_AUDIT_DDL)
    return conn


def log_action(module: str, function: str, args: dict, tier: int, outcome: str, note: str = ""):
    """Append an entry to the action_audit table."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO action_audit (timestamp,module,function,args,tier,outcome,note) VALUES (?,?,?,?,?,?,?)",
            (
                datetime.now().isoformat(),
                module, function,
                json.dumps(args, default=str)[:800],
                get_tier_name(tier),
                outcome,
                note,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"Audit log write failed: {exc}")


def get_audit_log(limit: int = 50) -> list:
    """Return recent audit entries, newest first."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM action_audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"Audit log read failed: {exc}")
        return []


# ─── PIN Session ──────────────────────────────────────────────────────────────

_pin_unlocked_until: Optional[float] = None
PIN_SESSION_TTL = 300  # seconds (5 minutes)


def is_pin_unlocked() -> bool:
    """True if a valid PIN session is currently active."""
    import time
    if _pin_unlocked_until is None:
        return False
    return time.time() < _pin_unlocked_until


def verify_pin(entered: str) -> bool:
    """
    Verify entered PIN against SECURITY_PIN config value.
    On success, opens a 5-minute session and returns True.
    If SECURITY_PIN is not set, always returns True (no PIN protection).
    """
    global _pin_unlocked_until
    import time
    from config import SECURITY_PIN
    if not SECURITY_PIN:
        # No PIN configured → critical actions are always allowed
        _pin_unlocked_until = time.time() + PIN_SESSION_TTL
        return True
    if entered.strip() == SECURITY_PIN.strip():
        _pin_unlocked_until = time.time() + PIN_SESSION_TTL
        return True
    return False


def lock_pin():
    """Immediately revoke the current PIN session."""
    global _pin_unlocked_until
    _pin_unlocked_until = None


# ─── Permission Gate ──────────────────────────────────────────────────────────

def check_permission(module: str, function: str, args: dict) -> str:
    """
    Check whether an action is permitted by the security policy.

    Returns:
        'allowed'   — proceed normally
        'needs_pin' — CRITICAL action and no active PIN session; caller must prompt for PIN

    Always logs to audit log when SECURITY_LOG_ENABLED is true.
    """
    try:
        from config import SECURITY_LOG_ENABLED
    except ImportError:
        SECURITY_LOG_ENABLED = True

    tier = get_tier(module, function)

    if tier in (SAFE, MODERATE):
        if SECURITY_LOG_ENABLED:
            log_action(module, function, args, tier, "allowed")
        return "allowed"

    elif tier == DANGEROUS:
        # Log prominently; existing confirm UX in modules/main.py handles user blocking
        if SECURITY_LOG_ENABLED:
            log_action(module, function, args, tier, "allowed_dangerous")
        return "allowed"

    elif tier == CRITICAL:
        if is_pin_unlocked():
            if SECURITY_LOG_ENABLED:
                log_action(module, function, args, tier, "allowed_pin_session")
            return "allowed"
        if SECURITY_LOG_ENABLED:
            log_action(module, function, args, tier, "blocked_needs_pin")
        return "needs_pin"

    return "allowed"
