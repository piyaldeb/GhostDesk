"""
GhostDesk Telegram User Client
Uses Pyrogram to listen to incoming personal Telegram DMs on behalf of the user.
This is separate from the GhostDesk bot — it acts as the USER's account.

Setup:
  1. Go to https://my.telegram.org → "API development tools"
  2. Create an app → copy api_id and api_hash
  3. Set TELEGRAM_API_ID and TELEGRAM_API_HASH in ~/.ghostdesk/.env
  4. First run: you will be prompted to enter your phone number and OTP
  5. Session saved to ~/.ghostdesk/telegram_session/ (never share this)
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_user_client_instance = None


class TelegramUserClient:
    """Pyrogram-based personal Telegram account listener."""

    def __init__(self, api_id: int, api_hash: str, session_dir: Path):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = str(session_dir / "ghostdesk_user")
        self._app = None
        self._bot_app = None  # telegram.ext.Application for forwarding to owner
        self._owner_chat_id: Optional[int] = None

    def attach_bot(self, bot_app, owner_chat_id: int):
        """Attach the GhostDesk bot so we can forward approval cards."""
        self._bot_app = bot_app
        self._owner_chat_id = owner_chat_id

    async def start(self):
        """Start the Pyrogram client and register message handler."""
        try:
            from pyrogram import Client, filters
            from pyrogram.handlers import MessageHandler

            self._app = Client(
                self.session_path,
                api_id=self.api_id,
                api_hash=self.api_hash,
            )

            @self._app.on_message(filters.private & ~filters.me)
            async def on_dm(client, message):
                await self._handle_incoming_dm(message)

            await self._app.start()
            me = await self._app.get_me()
            logger.info(f"Telegram user client started as: {me.first_name} (@{me.username})")

        except ImportError:
            logger.warning("pyrogram not installed. Telegram DM auto-response disabled. Run: pip install pyrogram tgcrypto")
        except Exception as e:
            logger.error(f"Telegram user client error: {e}")

    async def _handle_incoming_dm(self, message) -> None:
        """Process an incoming personal DM."""
        try:
            from config import AUTO_RESPOND_TELEGRAM, TELEGRAM_CHAT_ID
            if not AUTO_RESPOND_TELEGRAM:
                return

            contact = str(message.from_user.id)
            contact_name = message.from_user.first_name or ""
            if message.from_user.last_name:
                contact_name += f" {message.from_user.last_name}"
            username = message.from_user.username or ""
            if username:
                contact_name += f" (@{username})"

            text = message.text or message.caption or ""
            if not text:
                return  # skip media-only messages

            logger.info(f"Incoming Telegram DM from {contact_name}: {text[:60]}")

            from modules.auto_responder import process_incoming
            await process_incoming(
                contact=contact,
                contact_name=contact_name,
                incoming_message=text,
                source="telegram",
                bot=self._bot_app,
                chat_id=self._owner_chat_id or int(TELEGRAM_CHAT_ID),
            )

        except Exception as e:
            logger.error(f"DM handler error: {e}")

    async def send_reply(self, contact_id: str, message: str) -> None:
        """Send a DM reply via the user's Telegram account."""
        if not self._app:
            raise RuntimeError("Telegram user client not started")
        await self._app.send_message(int(contact_id), message)

    async def stop(self):
        if self._app:
            await self._app.stop()


# ─── Singleton management ─────────────────────────────────────────────────────

def get_user_client() -> Optional[TelegramUserClient]:
    """Return the initialized user client instance, or None if not set up."""
    return _user_client_instance


async def start_user_client(bot_app, owner_chat_id: int) -> Optional[TelegramUserClient]:
    """
    Initialize and start the Telegram user client.
    Called from main.py on startup if AUTO_RESPOND_TELEGRAM is enabled.
    """
    global _user_client_instance

    try:
        from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, AUTO_RESPOND_TELEGRAM, USER_DATA_DIR

        if not AUTO_RESPOND_TELEGRAM:
            return None

        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            logger.warning(
                "Telegram DM auto-response enabled but TELEGRAM_API_ID / TELEGRAM_API_HASH "
                "not set. Run ghostdesk-setup or add them to ~/.ghostdesk/.env"
            )
            return None

        session_dir = USER_DATA_DIR / "telegram_session"
        session_dir.mkdir(exist_ok=True)

        client = TelegramUserClient(
            api_id=int(TELEGRAM_API_ID),
            api_hash=TELEGRAM_API_HASH,
            session_dir=session_dir,
        )
        client.attach_bot(bot_app, owner_chat_id)
        await client.start()

        _user_client_instance = client
        return client

    except ImportError:
        logger.warning("pyrogram not installed — Telegram DM listening disabled.")
        return None
    except Exception as e:
        logger.error(f"Could not start Telegram user client: {e}")
        return None
