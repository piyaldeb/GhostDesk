"""
GhostPC Agent — The Central Brain
Receives every Telegram message, builds an action plan via AI,
executes actions sequentially, and returns results to the user.
"""

import asyncio
import json
import logging
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Pending WhatsApp export sessions awaiting a name (group chats)
# { agent_id: {"path": str, "senders": list} }
_pending_wa_exports: dict = {}


def _looks_like_whatsapp_export(file_path: str) -> bool:
    """
    Peek at the first few lines of a text file to check if it's a WhatsApp export.
    WhatsApp exports always start with a timestamp pattern.
    """
    import re
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            head = [f.readline() for _ in range(5)]
        pattern = re.compile(
            r"^\[?\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}"
            r"(?:,\s*|\s+)\d{1,2}:\d{2}",
        )
        matches = sum(1 for line in head if pattern.match(line.strip()))
        return matches >= 1
    except Exception:
        return False


def _get_pc_context() -> str:
    """Build a short PC context string for the AI."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        user = os.environ.get("USERNAME") or os.environ.get("USER", "user")
        home = str(Path.home())
        return (
            f"OS: Windows {platform.version()}\n"
            f"User: {user} | Home: {home}\n"
            f"CPU: {cpu}% | RAM: {ram.percent}% used\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Downloads: {home}\\Downloads | Desktop: {home}\\Desktop"
        )
    except Exception as e:
        return f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def _result_to_str(res: Any) -> str:
    """
    Convert an action result to a human-readable string for use as a string argument.
    Most module functions return dicts with a 'text' key — use that when available.
    """
    if res is None:
        return ""
    if isinstance(res, str):
        return res
    if isinstance(res, dict):
        # Prefer 'text', then 'content', then 'body', then str(dict)
        for key in ("text", "content", "body", "result", "output", "data"):
            if key in res and isinstance(res[key], str):
                return res[key]
        return str(res)
    return str(res)


def _resolve_arg(value: Any, results: list) -> Any:
    """
    Replace {result_of_action_N} placeholders in arg values with actual results.
    Handles strings, dicts, and lists recursively.

    When the ENTIRE arg value is a single placeholder (e.g. body="{result_of_action_0}"),
    we return the raw result so the callee gets a dict if it wants one.
    When the placeholder is EMBEDDED in a larger string, we stringify the result using
    _result_to_str() so dict results produce readable text rather than repr().
    """
    if isinstance(value, str):
        for i, res in enumerate(results):
            placeholder = f"{{result_of_action_{i}}}"
            if placeholder in value:
                if value.strip() == placeholder:
                    # Whole value is the placeholder — return raw result (could be dict)
                    return res
                # Embedded placeholder — stringify intelligently
                value = value.replace(placeholder, _result_to_str(res))
        return value
    elif isinstance(value, dict):
        return {k: _resolve_arg(v, results) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_arg(item, results) for item in value]
    return value


def _resolve_args(args: dict, results: list) -> dict:
    """Resolve all placeholders in an args dict, coercing dict results to str for string params."""
    resolved = {}
    for k, v in args.items():
        resolved_val = _resolve_arg(v, results)
        # If the arg value is still a dict but the original was a plain placeholder string,
        # coerce it to text for typical string-typed parameters (body, message, text, content, subject)
        if isinstance(resolved_val, dict) and isinstance(v, str) and v.strip().startswith("{result_of_action_"):
            _STRING_PARAMS = {"body", "message", "text", "content", "subject", "caption", "description"}
            if k in _STRING_PARAMS:
                resolved_val = _result_to_str(resolved_val)
        resolved[k] = resolved_val
    return resolved


# ─── Module Dispatch Table ────────────────────────────────────────────────────

def _get_module_function(module: str, function: str) -> Optional[Callable]:
    """Dynamically import and return the requested module function."""
    try:
        if module == "pc_control":
            from modules import pc_control as mod
        elif module == "file_system":
            from modules import file_system as mod
        elif module == "document":
            from modules import document as mod
        elif module == "browser":
            from modules import browser as mod
        elif module == "whatsapp":
            from modules import whatsapp as mod
        elif module == "email":
            from modules import email_handler as mod
        elif module == "media":
            from modules import media as mod
        elif module == "api_connector":
            from modules import api_connector as mod
        elif module == "scheduler":
            from core import scheduler as mod
        elif module == "memory":
            from core import memory as mod
        elif module == "voice":
            from modules import voice as mod
        elif module == "screen_watcher":
            from modules import screen_watcher as mod
        elif module == "personality":
            from modules import personality as mod
        elif module == "workflow":
            from modules import workflow_engine as mod
        elif module == "config_manager":
            from modules import config_manager as mod
        elif module == "google_services":
            from modules import google_services as mod
        elif module == "telegram":
            # telegram functions are handled specially by the caller
            return None
        else:
            logger.warning(f"Unknown module: {module}")
            return None

        func = getattr(mod, function, None)
        if func is None:
            logger.warning(f"Function {function} not found in module {module}")
        return func

    except ImportError as e:
        logger.error(f"Import error for module {module}: {e}")
        return None


# ─── Main Agent ───────────────────────────────────────────────────────────────

class GhostAgent:
    def __init__(self, telegram_send_fn: Callable, telegram_send_file_fn: Callable):
        """
        telegram_send_fn: async (text: str) -> None
        telegram_send_file_fn: async (file_path: str, caption: str) -> None
        """
        self.send = telegram_send_fn
        self.send_file = telegram_send_file_fn

        from core.ai import get_ai
        from core.memory import init_db, build_memory_context, log_command
        self.ai = get_ai()
        self.build_memory_context = build_memory_context
        self.log_command = log_command

    async def handle(self, user_input: str) -> None:
        """Process a user message end-to-end."""
        await self.send("⚙️ Processing...")

        # Build context
        pc_ctx = _get_pc_context()
        mem_ctx = self.build_memory_context(10)

        # Get AI action plan
        try:
            plan = self.ai.parse_action_plan(user_input, mem_ctx, pc_ctx)
        except Exception as e:
            logger.error(f"AI planning error: {e}")
            await self.send(f"❌ AI error: {e}")
            self.log_command(user_input, "", [], str(e), False)
            return

        thought = plan.get("thought", "")
        actions = plan.get("actions", [])

        if thought:
            await self.send(f"💭 {thought}")

        # Execute actions sequentially
        results = []
        overall_success = True

        for i, action in enumerate(actions):
            module = action.get("module", "")
            function = action.get("function", "")
            args = action.get("args", {})

            # Resolve placeholders from previous results
            resolved_args = _resolve_args(args, results)

            logger.info(f"Action {i}: {module}.{function}({resolved_args})")

            # Handle telegram module specially (async)
            if module == "telegram":
                result = await self._handle_telegram_action(function, resolved_args)
                results.append(result)
                continue

            # Check for destructive action confirmation flag
            # (Handled upstream in main.py before calling agent)

            # Get the function
            func = _get_module_function(module, function)
            if func is None:
                err = f"Module/function not available: {module}.{function}"
                await self.send(f"⚠️ {err}")
                results.append({"success": False, "error": err})
                overall_success = False
                continue

            # Execute (handle both sync and async functions)
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(**resolved_args)
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda f=func, a=resolved_args: f(**a)
                    )

                results.append(result)

                # If result contains a file path to send, send it automatically
                if isinstance(result, dict):
                    if result.get("success") is False:
                        err = result.get("error", "Unknown error")
                        recovery = self.ai.suggest_recovery(action, err)
                        await self.send(f"⚠️ Action {i+1} failed: {err}\n\n💡 Suggestion: {recovery}")
                        overall_success = False
                    elif result.get("file_path"):
                        # Auto-send file result if module produced one
                        fp = result["file_path"]
                        caption = result.get("caption", f"Result from {module}.{function}")
                        await self.send_file(fp, caption)

                    # stop_chain: True — this action requires user approval before proceeding.
                    # Abort any remaining actions in the plan (e.g. draft_reply must not
                    # be followed by an auto-send in the same plan).
                    if result.get("stop_chain"):
                        remaining = len(actions) - i - 1
                        if remaining > 0:
                            logger.info(f"stop_chain triggered after {module}.{function} — skipping {remaining} remaining action(s)")
                        break

            except Exception as e:
                logger.error(f"Action {i} error: {e}", exc_info=True)
                recovery = self.ai.suggest_recovery(action, str(e))
                await self.send(f"❌ Action {i+1} ({module}.{function}) crashed:\n{e}\n\n💡 {recovery}")
                results.append({"success": False, "error": str(e)})
                overall_success = False

        # Final result summary
        final_result = self._summarize_results(results)
        if final_result and final_result not in ("None", "{}"):
            await self._send_long(final_result)

        # Log to memory
        self.log_command(
            user_input,
            thought,
            actions,
            final_result,
            overall_success
        )

    async def _handle_telegram_action(self, function: str, args: dict) -> Any:
        """Handle telegram.send_message and telegram.send_file."""
        if function == "send_message":
            text = args.get("text", "")
            await self._send_long(text)
            return text

        elif function == "send_file":
            file_path = args.get("file_path", "")
            caption = args.get("caption", "")
            if file_path and Path(file_path).exists():
                await self.send_file(file_path, caption)
                return {"success": True, "sent": file_path}
            else:
                await self.send(f"⚠️ File not found: {file_path}")
                return {"success": False, "error": f"File not found: {file_path}"}

        return None

    def _summarize_results(self, results: list) -> str:
        """Build a readable summary of all action results."""
        parts = []
        for i, r in enumerate(results):
            if r is None:
                continue
            if isinstance(r, dict):
                if r.get("success") is False:
                    continue  # already reported
                if "file_path" in r:
                    continue  # already sent as file
                # Show text results
                text = r.get("text") or r.get("output") or r.get("result") or r.get("data")
                if text and str(text).strip():
                    parts.append(str(text)[:1000])
            elif isinstance(r, (str, int, float)) and str(r).strip():
                parts.append(str(r)[:500])

        return "\n\n".join(parts)

    async def _send_long(self, text: str):
        """Split and send text that might exceed Telegram's 4096 char limit."""
        if not text or not text.strip():
            return
        chunk_size = 4000
        text = str(text)
        for i in range(0, len(text), chunk_size):
            await self.send(text[i:i + chunk_size])

    async def handle_file_upload(self, file_path: str, filename: str) -> None:
        """Handle a file uploaded by the user to the Telegram bot."""
        # ── Auto-detect WhatsApp chat export ──────────────────────────────
        if filename.lower().endswith(".txt") and _looks_like_whatsapp_export(file_path):
            await self.send(
                "📱 This looks like a *WhatsApp chat export*!\n"
                "Analysing to learn your writing style..."
            )
            from modules.personality import learn_from_whatsapp_export
            result = await asyncio.get_event_loop().run_in_executor(
                None, learn_from_whatsapp_export, file_path, ""
            )
            if result.get("needs_name"):
                # Store path for follow-up
                _pending_wa_exports[id(self)] = {"path": file_path, "senders": result.get("senders", [])}
            await self.send(result.get("text", str(result)))
            return

        msg = f"📁 You uploaded: {filename}\nSaved to: {file_path}\n\nWhat would you like to do with this file?"
        await self.send(msg)

    async def handle_whatsapp_name_reply(self, your_name: str, file_path: str) -> None:
        """Called when user provides their name for a group WhatsApp export."""
        from modules.personality import learn_from_whatsapp_export
        result = await asyncio.get_event_loop().run_in_executor(
            None, learn_from_whatsapp_export, file_path, your_name
        )
        await self.send(result.get("text", str(result)))
