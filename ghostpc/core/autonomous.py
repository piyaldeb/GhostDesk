"""
GhostDesk Autonomous Agent Mode
Breaks a complex natural language goal into ordered steps,
executes them through the existing GhostAgent, and reports
progress step-by-step on Telegram.

Activated by user commands like:
  "autonomously do X"
  "your goal is: X"
  "auto task: X"
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# ─── Planner Prompt ───────────────────────────────────────────────────────────

PLANNER_PROMPT = """You are GhostPC's autonomous task planner.
The user wants to achieve a goal. Break it into a minimal sequence of executable steps.

Goal: {goal}

Available GhostPC modules:
- pc_control: screenshot, open_app, close_app, get_system_stats, type_text, press_key
- file_system: find_file, read_file, move_file, delete_file, zip_folder, list_files
- document: read_excel, generate_report, create_pdf, read_pdf, fill_form
- browser: open_url, search_web, get_page_text, scrape_page, fill_form_on_web
- email: get_emails, send_email, reply_email
- whatsapp: get_messages, send_message
- api_connector: call_api, call_api_with_auth
- scheduler: create_schedule, list_schedules
- memory: save_note, search_memory, save_api_credential
- voice: text_to_speech

Rules:
1. Return ONLY valid JSON — no markdown, no extra text
2. Use 2–8 steps (keep it minimal and focused)
3. Express each step as a natural language "user_command" that GhostPC understands
4. Use {{result_of_step_N}} to pass output from step N into a later step
5. Mark "critical": true for steps that must succeed for the goal to make sense

Return:
{{
  "goal_summary": "one-line human-readable summary",
  "steps": [
    {{
      "step_number": 1,
      "description": "what this step does (for the progress display)",
      "user_command": "natural language command GhostPC understands",
      "critical": true
    }}
  ]
}}"""


# ─── Main Entry Point ─────────────────────────────────────────────────────────


async def run_goal(
    goal_text: str,
    send_fn: Callable[[str], Awaitable[None]],
    send_file_fn: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> dict:
    """
    Autonomously execute a complex goal.

    1. AI creates a step-by-step plan.
    2. Each step is expressed as natural language and run through GhostAgent.
    3. Results are reported to Telegram in real time.

    Args:
        goal_text: The user's natural language goal
        send_fn: Async function to send text to Telegram
        send_file_fn: Async function to send files to Telegram (optional)

    Returns:
        {"success": bool, "steps_completed": int, "steps_total": int}
    """
    from core.ai import get_ai
    from core.agent import GhostAgent

    await send_fn(
        f"🤖 *Autonomous Mode Activated*\n\n"
        f"Goal: _{goal_text}_\n\n"
        f"Planning steps..."
    )

    # ── Phase 1: Planning ────────────────────────────────────────────────────
    try:
        ai = get_ai()
        raw = ai.call(
            "You are an autonomous task planner for a PC control agent.",
            PLANNER_PROMPT.format(goal=goal_text),
            max_tokens=2048,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        await send_fn(f"❌ Planner returned invalid JSON: {e}\n\nTry rephrasing your goal.")
        return {"success": False, "steps_completed": 0, "steps_total": 0}
    except Exception as e:
        await send_fn(f"❌ Planning failed: {e}")
        return {"success": False, "steps_completed": 0, "steps_total": 0}

    steps = plan.get("steps", [])
    goal_summary = plan.get("goal_summary", goal_text)
    total = len(steps)

    if not steps:
        await send_fn("❌ No executable steps could be generated for this goal.")
        return {"success": False, "steps_completed": 0, "steps_total": 0}

    plan_lines = "\n".join([f"{s['step_number']}. {s['description']}" for s in steps])
    await send_fn(
        f"📋 *Plan: {goal_summary}*\n\n{plan_lines}\n\n▶️ Starting execution..."
    )

    # ── Phase 2: Step-by-step Execution ──────────────────────────────────────
    completed = 0
    step_outputs: list[str] = []

    for i, step in enumerate(steps):
        step_num = step.get("step_number", i + 1)
        desc = step.get("description", f"Step {step_num}")
        command = step.get("user_command", desc)
        is_critical = step.get("critical", True)

        # Resolve {result_of_step_N} placeholders from previous outputs
        for j, output in enumerate(step_outputs):
            command = command.replace(f"{{result_of_step_{j}}}", output)

        await send_fn(f"⚙️ *Step {step_num}/{total}:* {desc}")

        # Capture what the agent sends back
        captured: list[str] = []

        async def capture_send(text: str, _buf=captured):
            _buf.append(text)

        dummy_file_fn = send_file_fn or (lambda p, c="": asyncio.sleep(0))
        agent = GhostAgent(capture_send, dummy_file_fn)

        try:
            await agent.handle(command)
            result_text = " | ".join(captured) if captured else "Done."
            step_outputs.append(result_text)
            completed += 1

            preview = result_text[:200] + ("..." if len(result_text) > 200 else "")
            await send_fn(f"✅ Step {step_num}: {preview}")

        except Exception as e:
            err_msg = str(e)
            step_outputs.append(f"FAILED: {err_msg}")
            await send_fn(f"❌ Step {step_num} failed: {err_msg}")

            if is_critical:
                await send_fn(
                    f"🛑 Critical step failed — stopping here.\n"
                    f"Completed {completed}/{total} steps."
                )
                return {
                    "success": False,
                    "steps_completed": completed,
                    "steps_total": total,
                }

    # ── Phase 3: Final Summary ────────────────────────────────────────────────
    if completed == total:
        await send_fn(
            f"🎯 *Goal Complete!*\n\n_{goal_summary}_\n\n✅ All {total} steps executed successfully."
        )
    else:
        await send_fn(
            f"🏁 Finished: {completed}/{total} steps completed.\n_{goal_summary}_"
        )

    return {
        "success": completed == total,
        "steps_completed": completed,
        "steps_total": total,
    }
