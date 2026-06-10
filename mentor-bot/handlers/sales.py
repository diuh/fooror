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
from formatters import md_to_html, split_message
from prompts.templates import (
    OBJECTION_TEMPLATE,
    OUTREACH_TEMPLATE,
    PRICE_CALC_TEMPLATE,
    PRICE_RANGES,
    PROPOSAL_TEMPLATE,
)

# ── /proposal wizard ──────────────────────────────────────────────────────────

PROP_TYPE, PROP_SCOPE, PROP_FEATURES, PROP_BUDGET, PROP_CONFIRM = range(400, 405)

TYPE_LABELS = {
    "ptype_landing": "Лендінг",
    "ptype_corporate": "Корпоративний сайт",
    "ptype_ecommerce": "Інтернет-магазин",
    "ptype_support": "Підтримка/обслуговування",
}


async def proposal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    await msg.reply_text(
        "📄 <b>Генерація пропозиції</b>\n\nТип проекту:",
        parse_mode="HTML",
        reply_markup=keyboards.proposal_type_keyboard(),
    )
    return PROP_TYPE


async def proposal_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["prop_type"] = TYPE_LABELS.get(update.callback_query.data, "")
    await update.callback_query.message.reply_text(
        "Опиши що хоче клієнт (2–5 речень про проект):"
    )
    return PROP_SCOPE


async def proposal_scope(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["prop_scope"] = update.message.text
    await update.message.reply_text(
        "Особливі функції або вимоги? (наприклад: мультимовність, CRM, онлайн-оплата)\n"
        "Або напиши «стандарт»",
        reply_markup=keyboards.skip_keyboard(),
    )
    return PROP_FEATURES


async def proposal_features(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["prop_features"] = update.message.text
    await update.message.reply_text(
        "Відомий бюджет клієнта? (або «невідомо»)",
        reply_markup=keyboards.skip_keyboard(),
    )
    return PROP_BUDGET


async def proposal_features_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["prop_features"] = "стандарт"
    await update.callback_query.message.reply_text(
        "Відомий бюджет клієнта? (або «невідомо»)",
        reply_markup=keyboards.skip_keyboard(),
    )
    return PROP_BUDGET


async def proposal_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    budget = update.message.text
    return await _generate_proposal(update, context, budget)


async def proposal_budget_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _generate_proposal(update.callback_query, context, "невідомо")


async def _generate_proposal(update_or_query, context, budget: str) -> int:
    proj_type = context.user_data.pop("prop_type", "")
    scope = context.user_data.pop("prop_scope", "")
    features = context.user_data.pop("prop_features", "стандарт")

    msg = update_or_query.message

    await msg.reply_text("⏳ Генерую пропозицію…")
    ctx = await db.build_context_snapshot()
    prompt = PROPOSAL_TEMPLATE.format(
        project_type=proj_type,
        scope=scope,
        features=features,
        budget=budget,
        price_ranges=PRICE_RANGES,
    )
    proposal_text = await ai_client.ask_long(prompt, ctx, bot=msg.get_bot(), chat_id=msg.chat_id)
    context.user_data["last_proposal"] = {
        "project_type": proj_type,
        "scope": scope,
        "proposal_text": proposal_text,
    }
    for part in split_message(proposal_text):
        await msg.reply_text(md_to_html(part), parse_mode="HTML")
    await msg.reply_text(
        "Зберегти пропозицію?",
        reply_markup=keyboards.save_cancel_keyboard("save_proposal"),
    )
    return PROP_CONFIRM


async def proposal_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    p = context.user_data.pop("last_proposal", {})
    if p:
        await db.add_proposal(
            project_type=p.get("project_type", ""),
            scope_summary=p.get("scope", ""),
            price_low=0,
            price_high=0,
            timeline_weeks=0,
            proposal_text=p.get("proposal_text", ""),
        )
        await update.callback_query.message.reply_text("✅ Збережено в /proposals")
    return ConversationHandler.END


async def proposal_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Не збережено.")
    else:
        await update.message.reply_text("Скасовано.")
    context.user_data.pop("last_proposal", None)
    return ConversationHandler.END


def proposal_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("proposal", proposal_start),
            CallbackQueryHandler(proposal_start, pattern="^cmd_proposal$"),
        ],
        states={
            PROP_TYPE: [CallbackQueryHandler(proposal_type, pattern="^ptype_")],
            PROP_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, proposal_scope)],
            PROP_FEATURES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, proposal_features),
                CallbackQueryHandler(proposal_features_skip, pattern="^skip$"),
            ],
            PROP_BUDGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, proposal_budget),
                CallbackQueryHandler(proposal_budget_skip, pattern="^skip$"),
            ],
            PROP_CONFIRM: [
                CallbackQueryHandler(proposal_save, pattern="^save_proposal$"),
                CallbackQueryHandler(proposal_cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", proposal_cancel)],
    )


# ── /price ────────────────────────────────────────────────────────────────────

PRICE_TYPE, PRICE_DESC = range(500, 502)


async def price_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    await msg.reply_text(
        "🧮 <b>Калькулятор ціни</b>\n\nТип проекту:",
        parse_mode="HTML",
        reply_markup=keyboards.proposal_type_keyboard(),
    )
    return PRICE_TYPE


async def price_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["price_type"] = TYPE_LABELS.get(update.callback_query.data, "")
    await update.callback_query.message.reply_text(
        "Опиши проект (що потрібно клієнту, особливості):"
    )
    return PRICE_DESC


async def price_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    proj_type = context.user_data.pop("price_type", "")
    description = update.message.text
    await update.message.reply_text("⏳ Розраховую…")
    ctx = await db.build_context_snapshot()
    prompt = PRICE_CALC_TEMPLATE.format(
        project_type=proj_type,
        description=description,
        price_ranges=PRICE_RANGES,
    )
    answer = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    for part in split_message(answer):
        await update.message.reply_text(md_to_html(part), parse_mode="HTML")
    return ConversationHandler.END


async def price_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def price_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("price", price_start),
            CallbackQueryHandler(price_start, pattern="^cmd_price$"),
        ],
        states={
            PRICE_TYPE: [CallbackQueryHandler(price_type, pattern="^ptype_")],
            PRICE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_desc)],
        },
        fallbacks=[CommandHandler("cancel", price_cancel)],
    )


# ── /outreach ─────────────────────────────────────────────────────────────────

OUTREACH_INFO, OUTREACH_PLATFORM = range(600, 602)


async def outreach_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📨 <b>Холодне повідомлення</b>\n\nОпиши клієнта/компанію (що вони роблять, яка у них проблема):",
        parse_mode="HTML",
    )
    return OUTREACH_INFO


async def outreach_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["outreach_info"] = update.message.text
    await update.message.reply_text(
        "Платформа для повідомлення:",
        reply_markup=keyboards.platform_keyboard(),
    )
    return OUTREACH_PLATFORM


async def outreach_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    platform = update.callback_query.data.replace("platform_", "")
    client_info = context.user_data.pop("outreach_info", "")
    ctx = await db.build_context_snapshot()
    prompt = OUTREACH_TEMPLATE.format(
        client_info=client_info,
        project_type="веб-дизайн/розробка",
        platform=platform,
        language="українська",
    )
    answer = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.callback_query.message.chat_id)
    await update.callback_query.message.reply_text(md_to_html(answer), parse_mode="HTML")
    return ConversationHandler.END


async def outreach_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def outreach_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("outreach", outreach_start)],
        states={
            OUTREACH_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, outreach_info)],
            OUTREACH_PLATFORM: [CallbackQueryHandler(outreach_platform, pattern="^platform_")],
        },
        fallbacks=[CommandHandler("cancel", outreach_cancel)],
    )


# ── /objection ────────────────────────────────────────────────────────────────

async def objection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Введи заперечення після команди:\n/objection дорого, можна дешевше"
        )
        return
    obj_text = " ".join(context.args)
    ctx = await db.build_context_snapshot()
    prompt = OBJECTION_TEMPLATE.format(
        objection=obj_text,
        context="веб-дизайн/розробка сайтів",
    )
    answer = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    await update.message.reply_text(md_to_html(answer), parse_mode="HTML")


# ── /pitch ────────────────────────────────────────────────────────────────────

async def pitch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    proj = " ".join(context.args) if context.args else "лендінг"
    ctx = await db.build_context_snapshot()
    answer = await ai_client.ask(
        f"Напиши 3-речення elevator pitch для проекту: {proj}. Мова: українська.",
        ctx,
        bot=context.bot, chat_id=update.effective_chat.id,
    )
    await update.message.reply_text(md_to_html(answer), parse_mode="HTML")
