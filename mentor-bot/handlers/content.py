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

POST_PLATFORM, POST_CASES = range(700, 702)


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
        "Є кейс, завершений проект або тема, про яку хочеш написати?\n\n"
        "Наприклад: <i>«зробив презентацію для партнерської програми»</i> або "
        "<i>«хочу написати про помилки при редизайні»</i>\n\n"
        "Якщо немає — пропусти, придумаю сам.",
        parse_mode="HTML",
        reply_markup=keyboards.skip_keyboard(),
    )
    return POST_CASES


async def post_idea_cases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _generate_post(update, context, extra=update.message.text)


async def post_idea_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _generate_post(update.callback_query, context, extra="")


async def _generate_post(update_or_query, context, extra: str) -> int:
    platform = context.user_data.pop("post_platform", "linkedin")
    msg = update_or_query.message

    ctx = await db.build_context_snapshot()
    prompt = POST_IDEA_TEMPLATE.format(
        platform=platform,
        extra_context=f"Контекст від користувача: {extra}" if extra else "",
    )
    answer = await ai_client.ask_long(prompt, ctx, bot=msg.get_bot(), chat_id=msg.chat_id)

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
            POST_CASES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_idea_cases),
                CallbackQueryHandler(post_idea_skip, pattern="^skip$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", post_idea_cancel)],
    )


# ── /weekly_plan ──────────────────────────────────────────────────────────────

WP_PLATFORMS, WP_CASES, WP_IDEAS = range(730, 733)

_PLATFORM_LABELS = {
    "wplat_li_ig": "LinkedIn, Instagram",
    "wplat_li_be": "LinkedIn, Behance",
    "wplat_all": "LinkedIn, Instagram, Behance, Telegram",
}


async def weekly_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    await msg.reply_text(
        "📊 <b>Контент-план на тиждень</b>\n\n"
        "Для яких платформ робимо план?",
        parse_mode="HTML",
        reply_markup=keyboards.weekly_platforms_keyboard(),
    )
    return WP_PLATFORMS


async def weekly_plan_platforms_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["wp_platforms"] = _PLATFORM_LABELS[update.callback_query.data]
    return await _ask_cases(update.callback_query.message)


async def weekly_plan_platforms_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["wp_platforms"] = update.message.text.strip()
    return await _ask_cases(update.message)


async def _ask_cases(msg) -> int:
    await msg.reply_text(
        "Є кейси або завершені роботи, які хочеш включити в план?\n\n"
        "<i>Наприклад: «презентація для партнерки», «редизайн сайту для кафе»</i>\n\n"
        "Якщо немає — пропусти.",
        parse_mode="HTML",
        reply_markup=keyboards.skip_keyboard(),
    )
    return WP_CASES


async def weekly_plan_cases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["wp_cases"] = update.message.text.strip()
    return await _ask_ideas(update.message)


async def weekly_plan_cases_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["wp_cases"] = ""
    return await _ask_ideas(update.callback_query.message)


async def _ask_ideas(msg) -> int:
    await msg.reply_text(
        "Є конкретні теми або ідеї для постів?\n\n"
        "<i>Наприклад: «написати про ціноутворення», «пост про помилки клієнтів»</i>\n\n"
        "Якщо немає — пропусти, підберу теми під твій контекст.",
        parse_mode="HTML",
        reply_markup=keyboards.skip_keyboard(),
    )
    return WP_IDEAS


async def weekly_plan_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["wp_ideas"] = update.message.text.strip()
    return await _generate_weekly(update.message, context)


async def weekly_plan_ideas_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["wp_ideas"] = ""
    return await _generate_weekly(update.callback_query.message, context)


async def _generate_weekly(msg, context) -> int:
    platforms = context.user_data.pop("wp_platforms", "LinkedIn, Instagram")
    cases = context.user_data.pop("wp_cases", "")
    ideas = context.user_data.pop("wp_ideas", "")

    cases_block = f"\nКейси для публікації:\n{cases}\n" if cases else ""
    ideas_block = f"\nІдеї від користувача:\n{ideas}\n" if ideas else ""

    await msg.reply_text("⏳ Генерую план на тиждень…")
    ctx = await db.build_context_snapshot()
    from prompts.system import build_context_block
    prompt = WEEKLY_CONTENT_TEMPLATE.format(
        platforms=platforms,
        cases_block=cases_block,
        ideas_block=ideas_block,
        context_block=build_context_block(ctx),
    )
    answer = await ai_client.ask_long(prompt, ctx, bot=msg.get_bot(), chat_id=msg.chat_id)
    # Remember the plan so follow-up free-text messages revise THIS plan
    # instead of being misread as edits to today's task list.
    context.user_data["last_content_plan"] = answer
    for part in split_message(answer):
        await msg.reply_text(part)
    return ConversationHandler.END


async def weekly_plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def weekly_plan_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("weekly_plan", weekly_plan_start)],
        states={
            WP_PLATFORMS: [
                CallbackQueryHandler(weekly_plan_platforms_cb, pattern="^wplat_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_plan_platforms_text),
            ],
            WP_CASES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_plan_cases),
                CallbackQueryHandler(weekly_plan_cases_skip, pattern="^skip$"),
            ],
            WP_IDEAS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_plan_ideas),
                CallbackQueryHandler(weekly_plan_ideas_skip, pattern="^skip$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", weekly_plan_cancel)],
    )


# ── /brand ────────────────────────────────────────────────────────────────────

async def brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = await db.build_context_snapshot()
    from prompts.system import build_context_block
    prompt = BRAND_TEMPLATE.format(context_block=build_context_block(ctx))
    answer = await ai_client.ask_long(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    for part in split_message(answer):
        await update.message.reply_text(part)
