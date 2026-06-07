import asyncio
import contextlib

import anthropic
from telegram.constants import ChatAction

from config import config
from prompts.system import STATIC_PERSONA, build_context_block

# Sonnet for short, frequent tasks (check-ins, reminders, quick questions);
# Opus for heavy generations (proposals, monthly analysis, channels, goal-setting).
MODEL_FAST = "claude-sonnet-4-6"
MODEL_SMART = "claude-opus-4-8"

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


async def _generate(user_message: str, context_data: dict | None, max_tokens: int, model: str) -> str:
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
            model=model,
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
        return await _generate(user_message, context_data, max_tokens=1024, model=MODEL_FAST)


async def ask_long(
    user_message: str,
    context_data: dict | None = None,
    *,
    bot=None,
    chat_id=None,
) -> str:
    async with _typing(bot, chat_id):
        return await _generate(user_message, context_data, max_tokens=2048, model=MODEL_SMART)


AGENT_INSTRUCTION = """Ти також керуєш ботом через інструменти (tools).
Коли користувач просить ВИКОНАТИ дію (додати оплату/витрату/підписку, лід, задачі,
запланувати зустріч, змінити статус ліда, спитати статус/огляд) — виклич відповідний
інструмент із розпізнаними аргументами. Якщо це просто питання, сумнів, порада чи
розмова — НЕ викликай інструментів, відповідай як ментор (2–4 речення).
Не вигадуй дій, яких користувач не просив. Якщо бракує критичних даних (напр. суми) —
коротко перепитай замість виклику інструмента. Відповідай мовою користувача."""


def _text_from(content) -> str:
    return "".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


async def run_agent(
    user_message: str,
    context_data: dict | None = None,
    *,
    tools: list[dict],
    executor,
    history: list[dict] | None = None,
    bot=None,
    chat_id=None,
    max_turns: int = 6,
) -> str:
    """Tool-use loop. `executor(name, input)` is an async callable returning
    {"result": str, "stop": bool}. When stop=True the loop ends immediately
    (e.g. an action needs user confirmation). Returns the model's final text
    (may be empty if it only called tools)."""
    system_blocks: list[dict] = [
        {"type": "text", "text": STATIC_PERSONA, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": AGENT_INSTRUCTION},
    ]
    if context_data:
        system_blocks.append({"type": "text", "text": build_context_block(context_data)})

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": user_message})

    # Mark the last tool schema for prompt caching — the tools array is static
    # across calls so Anthropic can cache it and skip re-tokenising each turn.
    if tools:
        cached_tools = [t.copy() for t in tools]
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}
    else:
        cached_tools = tools

    client = get_client()
    async with _typing(bot, chat_id):
        for _ in range(max_turns):
            try:
                resp = await client.messages.create(
                    model=MODEL_FAST,
                    max_tokens=1500,
                    system=system_blocks,
                    tools=cached_tools,
                    messages=messages,
                )
            except (anthropic.APIStatusError, anthropic.APITimeoutError):
                return "Ментор зараз недоступний, спробуй за хвилину."

            if resp.stop_reason != "tool_use":
                return _text_from(resp.content)

            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            stop_now = False
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                outcome = await executor(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": outcome.get("result", "ok"),
                })
                if outcome.get("stop"):
                    stop_now = True
            messages.append({"role": "user", "content": tool_results})
            if stop_now:
                return ""
    return ""
