"""Voice message transcription via Groq Whisper API (free tier).

Transcribes the audio and passes the result text to agent_text_handler so
voice messages are processed identically to typed messages.
"""

import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from config import config

logger = logging.getLogger(__name__)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.groq_api_key:
        await update.message.reply_text(
            "🎙 Щоб розпізнавати голосові, додай GROQ_API_KEY у змінні середовища.\n"
            "Безкоштовний ключ: console.groq.com"
        )
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await update.message.reply_text("🎙 Розпізнаю…")
    tmp_path = None
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        suffix = ".ogg" if update.message.voice else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)
        transcript = await _transcribe(tmp_path)
    except Exception as e:
        logger.exception("Voice transcription failed")
        await update.message.reply_text(f"❌ Не вдалось розпізнати: {e}")
        return
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not transcript or not transcript.strip():
        await update.message.reply_text("Не розпізнав нічого у голосовому повідомленні.")
        return

    await update.message.reply_text(f"🎙 <i>{transcript}</i>", parse_mode="HTML")

    from handlers.agent import _handle_text
    await _handle_text(transcript.strip(), update, context)


async def _transcribe(path: str) -> str:
    from groq import AsyncGroq
    client = AsyncGroq(api_key=config.groq_api_key)
    with open(path, "rb") as f:
        result = await client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            language="uk",
        )
    return result.text
