from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import ai_client
import database as db
import keyboards
from formatters import split_message
from prompts.templates import (
    BRAND_TEMPLATE,
    POST_IDEA_TEMPLATE,
    WEEKLY_CONTENT_TEMPLATE,
)

# ── /post_idea ────────────────────────────────────────────────────────────────

POST_PLATFORM, POST_CONTEXT = range(700, 702)


async def post_idea_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    await msg.reply_text(
        "✍️ <b>Ідея посту</b>\n\nДля якої платформи?",
        parse_mode="HTML",
        reply_markup=keyboards.platform_keyboard(),
    )
    return POST_PLATFORM


async def post_idea_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["post_platform"] = update.callback_query.data.replace("platform_", "")
    await update.callback_query.message.reply_text(
        "Є конкретна тема або контекст? (або пропусти — згенерую сам)",
        reply_markup=keyboards.skip_keyboard(),
    )
    return POST_CONTEXT


async def post_idea_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _generate_post(update, context, extra=update.message.text)


async def post_idea_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _generate_post(update.callback_query, context, extra="")


async def _generate_post(update_or_query, context, extra: str) -> int:
    platform = context.user_data.pop("post_platform", "linkedin")
    if hasattr(update_or_query, "message"):
        msg = update_or_query.message
    else:
        msg = update_or_query.message

    ctx = await db.build_context_snapshot()
    prompt = POST_IDEA_TEMPLATE.format(
        platform=platform,
        extra_context=f"Додатковий контекст: {extra}" if extra else "",
    )
    answer = await ai_client.ask_long(prompt, ctx)

    title_line = answer.split("\n")[0][:80]
    await db.add_content_idea(platform=platform, title=title_line, body=answer)

    for part in split_message(answer):
        await msg.reply_text(part)
    return ConversationHandler.END


async def post_idea_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def post_idea_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("post_idea", post_idea_start),
            CallbackQueryHandler(post_idea_start, pattern="^cmd_post_idea$"),
        ],
        states={
            POST_PLATFORM: [CallbackQueryHandler(post_idea_platform, pattern="^platform_")],
            POST_CONTEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_idea_context),
                CallbackQueryHandler(post_idea_skip, pattern="^skip$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", post_idea_cancel)],
    )


# ── /weekly_plan ──────────────────────────────────────────────────────────────

async def weekly_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Генерую план на тиждень…")
    ctx = await db.build_context_snapshot()
    from prompts.system import build_context_block
    prompt = WEEKLY_CONTENT_TEMPLATE.format(
        context_block=build_context_block(ctx),
    )
    answer = await ai_client.ask_long(prompt, ctx)
    for part in split_message(answer):
        await update.message.reply_text(part)


# ── /brand ────────────────────────────────────────────────────────────────────

async def brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = await db.build_context_snapshot()
    from prompts.system import build_context_block
    prompt = BRAND_TEMPLATE.format(context_block=build_context_block(ctx))
    answer = await ai_client.ask_long(prompt, ctx)
    for part in split_message(answer):
        await update.message.reply_text(part)
