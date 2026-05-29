import asyncio
import contextlib

import anthropic
from telegram.constants import ChatAction

from config import config
from prompts.system import STATIC_PERSONA, build_context_block

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    return _client


@contextlib.asynccontextmanager
async def _typing(bot, chat_id):
    """Show the native Telegram 'typing…' status until the block exits.

    Telegram clears the status after ~5s, so it is re-sent every 4s to keep
    it visible during longer AI generations. A no-op if bot/chat_id missing.
    """
    if bot is None or chat_id is None:
        yield
        return

    async def loop():
        try:
            while True:
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _generate(user_message: str, context_data: dict | None, max_tokens: int) -> str:
    system_blocks: list[dict] = [
        {
            "type": "text",
            "text": STATIC_PERSONA,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if context_data:
        system_blocks.append(
            {"type": "text", "text": build_context_block(context_data)}
        )

    try:
        response = await get_client().messages.create(
            model="claude-sonnet-4-5",
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except (anthropic.APIStatusError, anthropic.APITimeoutError):
        return "Ментор зараз недоступний, спробуй за хвилину."


async def ask(
    user_message: str,
    context_data: dict | None = None,
    *,
    bot=None,
    chat_id=None,
) -> str:
    async with _typing(bot, chat_id):
        return await _generate(user_message, context_data, max_tokens=1024)


async def ask_long(
    user_message: str,
    context_data: dict | None = None,
    *,
    bot=None,
    chat_id=None,
) -> str:
    async with _typing(bot, chat_id):
        return await _generate(user_message, context_data, max_tokens=2048)
