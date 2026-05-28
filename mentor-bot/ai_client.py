import anthropic
from config import config
from prompts.system import STATIC_PERSONA, build_context_block

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    return _client


async def ask(user_message: str, context_data: dict | None = None) -> str:
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
            max_tokens=1024,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except (anthropic.APIStatusError, anthropic.APITimeoutError):
        return "Ментор зараз недоступний, спробуй за хвилину."


async def ask_long(user_message: str, context_data: dict | None = None) -> str:
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
            max_tokens=2048,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except (anthropic.APIStatusError, anthropic.APITimeoutError):
        return "Ментор зараз недоступний, спробуй за хвилину."
