"""
GhostDesk Voice Module
- Transcribes Telegram voice messages via OpenAI Whisper
- Generates audio replies via OpenAI TTS (optional)

Requirements:
  pip install openai  (needed even if main AI provider is Claude)
  OPENAI_API_KEY must be set in ~/.ghostdesk/.env
"""

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def transcribe_voice(audio_path: str) -> dict:
    """
    Transcribe an audio file (OGG, MP3, WAV, WEBM, etc.) using OpenAI Whisper.

    Args:
        audio_path: Path to the audio file

    Returns:
        {"success": True, "text": str}  or  {"success": False, "error": str}
    """
    try:
        from config import OPENAI_API_KEY

        if not OPENAI_API_KEY:
            return {
                "success": False,
                "error": (
                    "OPENAI_API_KEY is required for voice transcription.\n"
                    "Add it to ~/.ghostdesk/.env even if your primary AI is Claude."
                ),
            }

        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )

        text = result.strip() if isinstance(result, str) else str(result).strip()
        logger.info(f"Voice transcribed ({len(text)} chars): {text[:80]}")
        return {"success": True, "text": text}

    except FileNotFoundError:
        return {"success": False, "error": f"Audio file not found: {audio_path}"}
    except ImportError:
        return {
            "success": False,
            "error": "openai package not installed. Run: pip install openai",
        }
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        return {"success": False, "error": str(e)}


def text_to_speech(
    text: str,
    output_path: Optional[str] = None,
    voice: str = "alloy",
) -> dict:
    """
    Convert text to an MP3 voice note using OpenAI TTS-1.

    Args:
        text: Text to synthesize (max 4096 chars)
        output_path: Where to save the MP3 (auto-generated if not provided)
        voice: OpenAI TTS voice — alloy, echo, fable, onyx, nova, shimmer

    Returns:
        {"success": True, "file_path": str}  or  {"success": False, "error": str}
    """
    try:
        from config import OPENAI_API_KEY, TEMP_DIR

        if not OPENAI_API_KEY:
            return {
                "success": False,
                "error": "OPENAI_API_KEY is required for text-to-speech.",
            }

        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        if not output_path:
            output_path = str(TEMP_DIR / f"tts_{int(time.time())}.mp3")

        # OpenAI TTS has a 4096-character limit
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text[:4096],
        )
        response.stream_to_file(output_path)

        logger.info(f"TTS saved: {output_path}")
        return {"success": True, "file_path": output_path, "text": text}

    except ImportError:
        return {
            "success": False,
            "error": "openai package not installed. Run: pip install openai",
        }
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return {"success": False, "error": str(e)}
