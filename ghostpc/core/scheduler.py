"""
GhostPC Scheduler
APScheduler-based engine that loads schedules from SQLite and fires them
through the same agent pipeline as if the user typed them in Telegram.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_human_schedule(text: str) -> Optional[str]:
    """
    Convert human-readable schedule descriptions to cron expressions.
    Examples:
      "every day at 9am"        → "0 9 * * *"
      "every Monday at 8am"     → "0 8 * * 1"
      "every hour"              → "0 * * * *"
      "every 30 minutes"        → "*/30 * * * *"
      "every weekday at 6pm"    → "0 18 * * 1-5"
    Falls back to returning the text as-is (user may have supplied raw cron).
    """
    text = text.lower().strip()

    # Check if it's already a cron expression (5 space-separated fields)
    parts = text.split()
    if len(parts) == 5 and all(
        p.replace("*", "").replace("/", "").replace("-", "").replace(",", "").isdigit() or p == "*"
        for p in parts
    ):
        return text

    # Simple pattern matching
    import re

    # "every N minutes"
    m = re.search(r"every (\d+) minute", text)
    if m:
        return f"*/{m.group(1)} * * * *"

    # "every N hours"
    m = re.search(r"every (\d+) hour", text)
    if m:
        return f"0 */{m.group(1)} * * *"

    # "every hour"
    if "every hour" in text:
        return "0 * * * *"

    # "every day at Xam/pm"
    m = re.search(r"every day at (\d+)(?::(\d+))?\s*(am|pm)?", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        elif m.group(3) == "am" and hour == 12:
            hour = 0
        return f"{minute} {hour} * * *"

    # "every weekday at X"
    m = re.search(r"every weekday at (\d+)(?::(\d+))?\s*(am|pm)?", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        return f"{minute} {hour} * * 1-5"

    # Day of week mapping
    day_map = {
        "monday": 1, "tuesday": 2, "wednesday": 3,
        "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0,
    }

    for day_name, day_num in day_map.items():
        m = re.search(rf"every {day_name} at (\d+)(?::(\d+))?\s*(am|pm)?", text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            if m.group(3) == "pm" and hour != 12:
                hour += 12
            return f"{minute} {hour} * * {day_num}"

    # "every morning" → 8am
    if "every morning" in text:
        return "0 8 * * *"

    # "every night" → 10pm
    if "every night" in text:
        return "0 22 * * *"

    logger.warning(f"Could not parse schedule: '{text}', treating as raw cron")
    return text  # Assume raw cron, APScheduler will validate


def start_scheduler(bot_app):
    """
    Start the APScheduler and load all active schedules from SQLite.
    bot_app: the telegram.ext.Application instance
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        from core.memory import get_active_schedules, update_schedule_last_run
        from config import TELEGRAM_CHAT_ID

        scheduler = BackgroundScheduler(timezone="UTC")

        def make_job(schedule_id: int, command_text: str):
            """Factory to create schedule job closures."""
            def job():
                try:
                    update_schedule_last_run(schedule_id)
                    logger.info(f"Firing schedule {schedule_id}: {command_text}")

                    # Run through agent pipeline via Telegram bot
                    async def _run():
                        chat_id = int(TELEGRAM_CHAT_ID)

                        async def send(text: str):
                            await bot_app.bot.send_message(chat_id=chat_id, text=text)

                        async def send_file(fp: str, caption: str = ""):
                            with open(fp, "rb") as f:
                                await bot_app.bot.send_document(
                                    chat_id=chat_id, document=f, caption=caption
                                )

                        from core.agent import GhostAgent
                        agent = GhostAgent(send, send_file)
                        await agent.handle(f"[Scheduled] {command_text}")

                    # Run async code in scheduler thread
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(_run())
                    finally:
                        loop.close()

                except Exception as e:
                    logger.error(f"Schedule {schedule_id} error: {e}")

            return job

        # Load schedules from DB
        schedules = get_active_schedules()
        for s in schedules:
            try:
                cron = _parse_human_schedule(s["cron_expression"])
                trigger = CronTrigger.from_crontab(cron)
                scheduler.add_job(
                    make_job(s["id"], s["command_text"]),
                    trigger=trigger,
                    id=f"schedule_{s['id']}",
                    replace_existing=True,
                    misfire_grace_time=60,
                )
                logger.info(f"Loaded schedule {s['id']}: [{cron}] {s['command_text'][:60]}")
            except Exception as e:
                logger.warning(f"Could not load schedule {s['id']}: {e}")

        scheduler.start()
        logger.info(f"Scheduler started with {len(schedules)} job(s).")
        return scheduler

    except ImportError:
        logger.warning("APScheduler not installed. Scheduled tasks disabled.")
        return None
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        return None


def create_schedule(cron_expression: str, command_text: str) -> dict:
    """Create and save a new scheduled task."""
    try:
        from core.memory import save_schedule

        # Normalize the cron expression
        cron = _parse_human_schedule(cron_expression)

        # Validate by trying to create a CronTrigger
        try:
            from apscheduler.triggers.cron import CronTrigger
            CronTrigger.from_crontab(cron)
        except Exception as e:
            return {"success": False, "error": f"Invalid schedule: {cron_expression} → {e}"}

        schedule_id = save_schedule(cron, command_text)

        return {
            "success": True,
            "schedule_id": schedule_id,
            "cron": cron,
            "command": command_text,
            "text": (
                f"✅ Scheduled: [{cron}] \"{command_text}\"\n"
                f"(Restart GhostPC for new schedules to activate)"
            ),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def list_schedules() -> dict:
    """List all active schedules."""
    try:
        from core.memory import get_active_schedules
        schedules = get_active_schedules()

        if not schedules:
            return {"success": True, "schedules": [], "text": "No active schedules."}

        lines = [f"⏰ Active schedules ({len(schedules)}):\n"]
        for s in schedules:
            last = s["last_run"][:16].replace("T", " ") if s["last_run"] else "never"
            lines.append(
                f"[{s['id']}] `{s['cron_expression']}` → {s['command_text'][:50]}\n"
                f"    Last run: {last}"
            )

        return {"success": True, "schedules": schedules, "text": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_schedule(id: int) -> dict:
    """Delete a schedule by ID."""
    try:
        from core.memory import delete_schedule as _del
        _del(int(id))
        return {"success": True, "text": f"✅ Schedule {id} deleted."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_missed_schedules(lookback_hours: int = 24) -> list[dict]:
    """
    Return any schedules that should have fired while the PC was off.
    Compares each schedule's last_run against the cron's next expected fire time.
    Only looks back up to `lookback_hours` to avoid ancient missed-run spam.
    """
    missed = []
    try:
        from core.memory import get_active_schedules
        from apscheduler.triggers.cron import CronTrigger

        schedules = get_active_schedules()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=lookback_hours)

        for s in schedules:
            try:
                cron = _parse_human_schedule(s["cron_expression"])
                trigger = CronTrigger.from_crontab(cron, timezone="UTC")

                # Reference: the later of last_run and the lookback cutoff
                if s["last_run"]:
                    ref_naive = datetime.fromisoformat(s["last_run"])
                    ref = ref_naive.replace(tzinfo=timezone.utc) if ref_naive.tzinfo is None else ref_naive
                    ref = max(ref, cutoff)
                else:
                    ref = cutoff

                # Find the next fire time after ref; if it's already past, it was missed
                next_fire = trigger.get_next_fire_time(None, ref)
                if next_fire and next_fire < now:
                    missed.append({
                        "id": s["id"],
                        "cron": s["cron_expression"],
                        "command": s["command_text"],
                        "missed_at": next_fire.strftime("%Y-%m-%d %H:%M UTC"),
                    })
            except Exception as e:
                logger.warning(f"Could not check schedule {s['id']} for missed runs: {e}")

    except Exception as e:
        logger.warning(f"check_missed_schedules error: {e}")

    return missed
