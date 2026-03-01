"""
GhostDesk Workflow Engine — chat-driven automation flows (n8n-like).

Trigger types : schedule | email_received | whatsapp_received | screen_event | manual
Action types  : notify | send_telegram | send_whatsapp | send_email |
                ai_process | screenshot | run_command | call_service

Workflows are stored in SQLite.  Scheduled workflows are registered with APScheduler.
Event triggers (email / WhatsApp / screen) are fired by their respective listeners.
"""

import asyncio
import json
import logging
import re
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level bot context — set by register_scheduled_workflows so agent-callable
# wrappers (like run_workflow_now) can send photos/messages without a Telegram handler.
_bot_app = None
_chat_id: int = 0


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _db_path() -> str:
    from config import DB_PATH
    return str(DB_PATH)


def _ensure_table():
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT    NOT NULL,
                trigger_type   TEXT    NOT NULL,
                trigger_config TEXT    NOT NULL DEFAULT '{}',
                actions        TEXT    NOT NULL DEFAULT '[]',
                enabled        INTEGER NOT NULL DEFAULT 1,
                created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


_ensure_table()


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def create_workflow(name: str, trigger_type: str,
                    trigger_config: dict, actions: list) -> int:
    with sqlite3.connect(_db_path()) as conn:
        cur = conn.execute(
            "INSERT INTO workflows (name, trigger_type, trigger_config, actions)"
            " VALUES (?,?,?,?)",
            (name, trigger_type,
             json.dumps(trigger_config), json.dumps(actions)),
        )
        conn.commit()
        return cur.lastrowid


def list_workflows() -> list:
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM workflows ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_workflow(wf_id: int) -> Optional[dict]:
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM workflows WHERE id=?", (wf_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_workflow(wf_id: int):
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("DELETE FROM workflows WHERE id=?", (wf_id,))
        conn.commit()


def toggle_workflow(wf_id: int, enabled: bool):
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            "UPDATE workflows SET enabled=? WHERE id=?",
            (int(enabled), wf_id),
        )
        conn.commit()


# ─── Setup checker ────────────────────────────────────────────────────────────

def check_workflow_setup(actions: list) -> list:
    """Return warning strings for any unconfigured services referenced in actions."""
    from config import EMAIL_ADDRESS, WHATSAPP_ENABLED
    warnings = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "send_email" and not EMAIL_ADDRESS:
            warnings.append("Email not configured. Say `connect email` to set it up.")
        elif atype == "send_whatsapp" and not WHATSAPP_ENABLED:
            warnings.append(
                "WhatsApp not enabled. Set WHATSAPP_ENABLED=true in .env "
                "and restart GhostDesk."
            )
        elif atype == "call_service":
            svc = action.get("config", {}).get("service", "")
            if svc:
                try:
                    from core.memory import get_api_credential
                    if not get_api_credential(svc):
                        warnings.append(
                            f"{svc.title()} not connected. "
                            f"Say `connect {svc}` to get setup steps."
                        )
                except Exception:
                    pass
    return warnings


# ─── Natural language parser ──────────────────────────────────────────────────

_PARSE_SYSTEM = (
    "You are a workflow parser. Convert the user description into a JSON workflow definition.\n"
    "Respond with ONLY a JSON object — no markdown fences, no extra text.\n\n"
    "Schema:\n"
    '{\n'
    '  "name": "Short descriptive name (max 40 chars)",\n'
    '  "trigger": {\n'
    '    "type": "schedule | email_received | whatsapp_received | screen_event | manual",\n'
    '    "config": {\n'
    '      // schedule:          {"cron": "0 9 * * *"} or {"interval_minutes": 30}\n'
    '      // email_received:    {"from_contains": "boss"} and/or {"subject_contains": "urgent"}\n'
    '      // whatsapp_received: {"contact_name": "mom"} or {"from_contains": "+1234"}\n'
    '      // screen_event:      {"event_type": "error_dialog|download_complete|incoming_call|build_finished|security_alert"}\n'
    '      // manual:            {}\n'
    "    }\n"
    "  },\n"
    '  "actions": [\n'
    "    {\n"
    '      "type": "notify | send_telegram | send_whatsapp | send_email | ai_process | screenshot | run_command | call_service",\n'
    '      "config": {\n'
    '        // notify:          {"message": "...", "priority": "high"}\n'
    '        // send_telegram:   {"message": "text with {variables}"}\n'
    '        // send_whatsapp:   {"to": "number_or_name", "message": "..."}\n'
    '        // send_email:      {"to": "email", "subject": "...", "body": "..."}\n'
    '        // ai_process:      {"prompt": "summarize: {content}", "store_as": "summary"}\n'
    '        // screenshot:      {}\n'
    '        // run_command:     {"command": "get system stats"}\n'
    '        // call_service:    {"service": "spotify", "action": "pause"}\n'
    "      }\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Template variables usable in any string config:\n"
    "{content} {sender} {subject} {contact_name} {timestamp} {ai_result} {screenshot_path}"
)


async def parse_workflow_nl(description: str) -> dict:
    """Use AI to parse a natural language workflow description into a structured dict."""
    from core.ai import get_ai
    ai = get_ai()
    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(
        None,
        lambda: ai.call(_PARSE_SYSTEM, description, 1024),
    )
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return json.loads(raw.strip())


# ─── Variable substitution ────────────────────────────────────────────────────

def _sub(value, context: dict):
    """Substitute {variable} placeholders from context recursively."""
    if isinstance(value, str):
        for k, v in context.items():
            value = value.replace(f"{{{k}}}", str(v))
        return value
    if isinstance(value, dict):
        return {k: _sub(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_sub(item, context) for item in value]
    return value


# ─── Execution engine ─────────────────────────────────────────────────────────

async def execute_workflow(wf: dict, context: dict,
                           bot_app=None, chat_id: int = 0):
    """Execute a workflow's action chain with the given context variables."""
    actions = (
        wf["actions"]
        if isinstance(wf["actions"], list)
        else json.loads(wf["actions"])
    )
    ctx = dict(context)

    for action in actions:
        atype = action.get("type", "")
        cfg   = _sub(action.get("config", {}), ctx)
        try:
            # ── Telegram notifications ───────────────────────────────────────
            if atype in ("notify", "send_telegram"):
                if bot_app and chat_id:
                    msg    = cfg.get("message", "Workflow triggered")
                    prefix = "🚨 *PRIORITY*: " if cfg.get("priority") == "high" else ""
                    await bot_app.bot.send_message(
                        chat_id, f"{prefix}{msg}", parse_mode="Markdown"
                    )

            # ── WhatsApp ─────────────────────────────────────────────────────
            elif atype == "send_whatsapp":
                from modules.whatsapp import send_message
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: send_message(cfg.get("to", ""), cfg.get("message", "")),
                )

            # ── Email ────────────────────────────────────────────────────────
            elif atype == "send_email":
                from modules.email_handler import send_email
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: send_email(
                        cfg.get("to", ""),
                        cfg.get("subject", "GhostDesk Workflow"),
                        cfg.get("body", ""),
                    ),
                )

            # ── AI processing ────────────────────────────────────────────────
            elif atype == "ai_process":
                from core.ai import get_ai
                ai          = get_ai()
                prompt_text = cfg.get("prompt", f"Summarize: {ctx.get('content', '')}")
                loop        = asyncio.get_event_loop()
                result_text = await loop.run_in_executor(
                    None,
                    lambda: ai.call("You are a helpful assistant.", prompt_text, 1024),
                )
                store_as           = cfg.get("store_as", "ai_result")
                ctx[store_as]      = result_text
                ctx["ai_result"]   = result_text
                if bot_app and chat_id:
                    await bot_app.bot.send_message(
                        chat_id,
                        f"🤖 *AI result:*\n{result_text[:2000]}",
                        parse_mode="Markdown",
                    )

            # ── Screenshot ───────────────────────────────────────────────────
            elif atype == "screenshot":
                from modules.pc_control import screenshot
                loop   = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, screenshot)
                if result.get("success"):
                    path               = result["file_path"]
                    ctx["screenshot_path"] = path
                    if bot_app and chat_id and path:
                        with open(path, "rb") as f:
                            await bot_app.bot.send_photo(chat_id, f)

            # ── Run command via agent ────────────────────────────────────────
            elif atype == "run_command":
                cmd = cfg.get("command", "")
                if cmd and bot_app and chat_id:
                    from core.agent import GhostAgent

                    async def _send(text):
                        await bot_app.bot.send_message(chat_id, text)

                    async def _send_file(fp, caption=""):
                        if fp:
                            with open(fp, "rb") as f:
                                await bot_app.bot.send_photo(chat_id, f)

                    agent = GhostAgent(_send, _send_file)
                    await agent.handle(cmd)

            # ── External service API ─────────────────────────────────────────
            elif atype == "call_service":
                from modules.api_connector import run_service_action
                loop   = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: run_service_action(
                        cfg.get("service", ""),
                        cfg.get("action", ""),
                        cfg.get("params"),
                    ),
                )
                ctx["service_result"] = result.get("text", "")
                if bot_app and chat_id and result.get("text"):
                    await bot_app.bot.send_message(
                        chat_id, result["text"][:3000], parse_mode="Markdown"
                    )

        except Exception as e:
            logger.error(f"Workflow action '{atype}' failed: {e}")
            if bot_app and chat_id:
                try:
                    await bot_app.bot.send_message(
                        chat_id, f"⚠️ Workflow step `{atype}` failed: {e}"
                    )
                except Exception:
                    pass


# ─── Event trigger hook ───────────────────────────────────────────────────────

async def trigger_workflows(trigger_type: str, context: dict,
                            bot_app=None, chat_id: int = 0):
    """
    Called when an external event occurs.
    Finds all enabled workflows that match trigger_type + conditions, then runs them.
    """
    for wf in list_workflows():
        if wf["trigger_type"] != trigger_type or not wf["enabled"]:
            continue

        cfg = (
            json.loads(wf["trigger_config"])
            if isinstance(wf["trigger_config"], str)
            else wf["trigger_config"]
        )

        # ── Condition filtering ──────────────────────────────────────────────
        if trigger_type == "email_received":
            fc = cfg.get("from_contains", "").lower()
            sc = cfg.get("subject_contains", "").lower()
            if fc and fc not in context.get("sender", "").lower():
                continue
            if sc and sc not in context.get("subject", "").lower():
                continue

        elif trigger_type == "whatsapp_received":
            fc = cfg.get("from_contains", "").lower()
            cn = cfg.get("contact_name", "").lower()
            if fc and fc not in context.get("sender", "").lower():
                continue
            if cn and cn not in context.get("contact_name", "").lower():
                continue

        elif trigger_type == "screen_event":
            et = cfg.get("event_type", "")
            if et and et != context.get("event_type", ""):
                continue

        try:
            await execute_workflow(wf, context, bot_app=bot_app, chat_id=chat_id)
        except Exception as e:
            logger.error(f"Workflow #{wf['id']} execution error: {e}")


# ─── Schedule registration ────────────────────────────────────────────────────

def register_scheduled_workflows(bot_app, chat_id: int, scheduler=None):
    """
    Register all enabled schedule-triggered workflows with APScheduler.
    If scheduler is None a new AsyncIOScheduler is created and started.
    Returns the scheduler used (caller may need to start it).
    """
    global _bot_app, _chat_id
    _bot_app = bot_app
    _chat_id = chat_id
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduled = [
        w for w in list_workflows()
        if w["trigger_type"] == "schedule" and w["enabled"]
    ]
    if not scheduled:
        return scheduler

    created_own = False
    if scheduler is None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler    = AsyncIOScheduler()
        created_own  = True

    for wf in scheduled:
        cfg = (
            json.loads(wf["trigger_config"])
            if isinstance(wf["trigger_config"], str)
            else wf["trigger_config"]
        )
        try:
            if "cron" in cfg:
                parts = cfg["cron"].split()
                if len(parts) != 5:
                    continue
                trigger = CronTrigger(
                    minute=parts[0], hour=parts[1],
                    day=parts[2], month=parts[3],
                    day_of_week=parts[4],
                )
            elif "interval_minutes" in cfg:
                trigger = IntervalTrigger(minutes=int(cfg["interval_minutes"]))
            else:
                continue

            # Capture wf by value
            wf_id  = wf["id"]
            wf_snap = dict(wf)

            async def _job(w=wf_snap, b=bot_app, c=chat_id):
                fresh = get_workflow(w["id"])
                if fresh and fresh["enabled"]:
                    await execute_workflow(fresh, {}, bot_app=b, chat_id=c)

            scheduler.add_job(
                _job, trigger,
                id=f"workflow_{wf_id}",
                replace_existing=True,
            )
            logger.info(f"Workflow #{wf_id} '{wf['name']}' registered in scheduler.")
        except Exception as e:
            logger.warning(f"Could not schedule workflow #{wf['id']}: {e}")

    if created_own:
        scheduler.start()

    return scheduler


# ─── Telegram display ─────────────────────────────────────────────────────────

def format_workflow_list():
    """Return (text, InlineKeyboardMarkup | None) for /workflows command."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    workflows = list_workflows()
    if not workflows:
        return (
            "📋 *No workflows yet.*\n\n"
            "Create one by saying:\n"
            "`create workflow: every day at 9am take a screenshot`\n"
            "`create workflow: when email from boss, alert me urgently`",
            None,
        )

    active_count = sum(1 for w in workflows if w["enabled"])
    lines    = [f"📋 *Workflows ({active_count} active, {len(workflows)-active_count} paused)*\n"]
    keyboard = []

    for wf in workflows:
        status = "✅" if wf["enabled"] else "⏸"
        tc     = (
            json.loads(wf["trigger_config"])
            if isinstance(wf["trigger_config"], str)
            else wf["trigger_config"]
        )
        tt = wf["trigger_type"]
        if tt == "schedule":
            cron = tc.get("cron", "")
            mins = tc.get("interval_minutes")
            trigger_label = f"schedule `{cron}`" if cron else f"every {mins} min"
        elif tt == "email_received":
            trigger_label = f"email from: `{tc.get('from_contains', 'any')}`"
        elif tt == "whatsapp_received":
            who = tc.get("contact_name") or tc.get("from_contains") or "any"
            trigger_label = f"WhatsApp from: `{who}`"
        elif tt == "screen_event":
            trigger_label = f"screen: `{tc.get('event_type', 'any')}`"
        elif tt == "manual":
            trigger_label = "manual"
        else:
            trigger_label = tt

        lines.append(f"#{wf['id']} {status} *{wf['name']}* — {trigger_label}")

        toggle_label = "⏸ Disable" if wf["enabled"] else "▶ Enable"
        keyboard.append([
            InlineKeyboardButton(
                f"▶ Run #{wf['id']}",
                callback_data=f"wf_run:{wf['id']}",
            ),
            InlineKeyboardButton(
                toggle_label,
                callback_data=f"wf_toggle:{wf['id']}:{wf['enabled']}",
            ),
            InlineKeyboardButton(
                "🗑 Delete",
                callback_data=f"wf_delete:{wf['id']}",
            ),
        ])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ─── Agent-callable async wrappers ────────────────────────────────────────────

async def create_workflow_from_description(description: str) -> dict:
    """Parse a natural language description and save the workflow. Returns confirmation text."""
    try:
        parsed = await parse_workflow_nl(description)
    except Exception as e:
        return {"success": False, "text": f"❌ Could not parse workflow: {e}"}

    trigger = parsed.get("trigger", {})
    actions = parsed.get("actions", [])
    name    = parsed.get("name", "Unnamed Workflow")

    wf_id = create_workflow(
        name=name,
        trigger_type=trigger.get("type", "manual"),
        trigger_config=trigger.get("config", {}),
        actions=actions,
    )

    # Build human-readable trigger description
    tt  = trigger.get("type", "manual")
    tc  = trigger.get("config", {})
    if tt == "schedule":
        cron = tc.get("cron", "")
        mins = tc.get("interval_minutes")
        trigger_desc = f"schedule `{cron}`" if cron else f"every `{mins}` minutes"
    elif tt == "email_received":
        trigger_desc = f"Email received (from contains: `{tc.get('from_contains', 'any')}`)"
    elif tt == "whatsapp_received":
        who = tc.get("contact_name") or tc.get("from_contains") or "any"
        trigger_desc = f"WhatsApp from: `{who}`"
    elif tt == "screen_event":
        trigger_desc = f"Screen event: `{tc.get('event_type', 'any')}`"
    else:
        trigger_desc = tt

    action_summary = " → ".join(a.get("type", "?") for a in actions)
    text = (
        f"✅ Workflow #{wf_id} created: *{name}*\n"
        f"Trigger: {trigger_desc}\n"
        f"Actions: {action_summary}\n\n"
        f"Say `/workflows` to see all your workflows."
    )

    warnings = check_workflow_setup(actions)
    if warnings:
        text += "\n\n⚠️ Setup needed:\n" + "\n".join(f"• {w}" for w in warnings)

    return {"success": True, "text": text}


def list_workflows_text() -> dict:
    """Return formatted workflow list (for agent dispatch)."""
    text, _ = format_workflow_list()
    return {"success": True, "text": text}


def delete_workflow_by_id(id: int) -> dict:
    wf = get_workflow(int(id))
    if not wf:
        return {"success": False, "text": f"❌ Workflow #{id} not found."}
    delete_workflow(int(id))
    return {"success": True, "text": f"✅ Workflow #{id} '{wf['name']}' deleted."}


async def run_workflow_now(id: int) -> dict:
    """Execute a workflow immediately with empty context."""
    wf = get_workflow(int(id))
    if not wf:
        return {"success": False, "text": f"❌ Workflow #{id} not found."}
    await execute_workflow(wf, {}, bot_app=_bot_app, chat_id=_chat_id)
    return {"success": True, "text": f"▶ Workflow #{id} '{wf['name']}' triggered."}
