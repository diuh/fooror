import json
from datetime import date

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
from formatters import income_bar
from prompts.templates import MORNING_TEMPLATE, EVENING_TEMPLATE

MORNING_PLAN, MORNING_BLOCKER = range(2)
EVENING_REVIEW, EVENING_NUMBERS, EVENING_MOOD = range(3, 6)


def today() -> str:
    return date.today().isoformat()


async def _send_or_reply(update: Update, text: str, **kwargs):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, **kwargs)
    elif update.message:
        await update.message.reply_text(text, **kwargs)


# ── Morning ───────────────────────────────────────────────────────────────────

async def morning_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ctx = await db.build_context_snapshot()
    overdue = ctx.get("overdue_leads", [])
    overdue_note = ""
    if overdue:
        names = ", ".join(l["name"] for l in overdue[:3])
        overdue_note = f"\n\n⚠️ Прострочені follow-up: {names}"

    bar = income_bar(ctx["month_income"], ctx["goal"])
    prompt = MORNING_TEMPLATE.format(
        time="ранок",
        context_block=f"Прогрес: {bar}{overdue_note}",
    )
    ai_msg = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    full_msg = f"🌅 <b>Ранковий check-in</b>\n\n{ai_msg}\n\nЩо плануєш зробити сьогодні?"
    await _send_or_reply(update, full_msg, parse_mode="HTML")
    return MORNING_PLAN


async def morning_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["morning_plan"] = update.message.text
    await update.message.reply_text("Що може тебе сьогодні загальмувати? (або напиши «нічого»)")
    return MORNING_BLOCKER


async def morning_blocker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    plan = context.user_data.pop("morning_plan", "")
    blocker = update.message.text
    ctx = await db.build_context_snapshot()
    ai_response = await ai_client.ask(
        f"Планує сьогодні: {plan}\nМожливий блокер: {blocker}\n\nДай коротку фокус-рекомендацію на день.",
        ctx,
        bot=context.bot, chat_id=update.effective_chat.id,
    )
    await db.upsert_daily_log(
        log_date=today(),
        log_type="morning",
        raw_input=plan,
        tasks_planned=json.dumps([plan]),
        ai_response=ai_response,
    )
    await update.message.reply_text(f"✅ {ai_response}")
    return ConversationHandler.END


async def morning_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Check-in скасовано.")
    return ConversationHandler.END


# ── Evening ───────────────────────────────────────────────────────────────────

async def evening_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_income"], ctx["goal"])
    prompt = EVENING_TEMPLATE.format(
        context_block=f"Прогрес місяця: {bar}",
    )
    ai_msg = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    full_msg = f"🌆 <b>Вечірній check-in</b>\n\n{ai_msg}\n\nЩо вдалось зробити сьогодні?"
    await _send_or_reply(update, full_msg, parse_mode="HTML")
    return EVENING_REVIEW


async def evening_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["evening_review"] = update.message.text
    await update.message.reply_text(
        "Скільки лідів contacted і пропозицій відправив сьогодні?\n"
        "Напиши у форматі: <b>2 ліди, 1 пропозиція</b> (або 0 і 0)",
        parse_mode="HTML",
    )
    return EVENING_NUMBERS


async def evening_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import re
    text = update.message.text
    context.user_data["evening_numbers"] = text
    leads_n = 0
    proposals_n = 0
    m = re.search(r"(\d+)\s*лід", text, re.IGNORECASE)
    if m:
        leads_n = int(m.group(1))
    m = re.search(r"(\d+)\s*пропозиц", text, re.IGNORECASE)
    if m:
        proposals_n = int(m.group(1))
    context.user_data["leads_contacted"] = leads_n
    context.user_data["proposals_sent"] = proposals_n
    await update.message.reply_text(
        "Як твій настрій / самопочуття сьогодні?",
        reply_markup=keyboards.mood_keyboard(),
    )
    return EVENING_MOOD


async def evening_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    mood = int(query.data.split("_")[1])
    review = context.user_data.pop("evening_review", "")
    leads_n = context.user_data.pop("leads_contacted", 0)
    proposals_n = context.user_data.pop("proposals_sent", 0)
    context.user_data.pop("evening_numbers", None)

    ctx = await db.build_context_snapshot()
    ai_response = await ai_client.ask(
        f"Підсумок дня:\n- Що зробив: {review}\n- Contacted: {leads_n} лідів, {proposals_n} пропозицій\n- Настрій: {mood}/5\n\nДай підсумок дня і одну пораду на завтра.",
        ctx,
        bot=context.bot, chat_id=query.message.chat_id,
    )
    await db.upsert_daily_log(
        log_date=today(),
        log_type="evening",
        raw_input=review,
        tasks_done=json.dumps([review]),
        leads_contacted=leads_n,
        proposals_sent=proposals_n,
        mood_score=mood,
        ai_response=ai_response,
    )
    streak = await db.get_streak()
    streak_str = f"\n\n🔥 Streak: {streak} дн." if streak > 1 else ""
    await query.message.reply_text(f"🌙 {ai_response}{streak_str}")
    return ConversationHandler.END


async def evening_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Check-in скасовано.")
    return ConversationHandler.END


# ── Scheduled job callbacks ───────────────────────────────────────────────────

async def morning_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    ctx = await db.build_context_snapshot()
    overdue = ctx.get("overdue_leads", [])
    overdue_note = ""
    if overdue:
        names = ", ".join(l["name"] for l in overdue[:3])
        overdue_note = f"\n\n⚠️ Прострочені follow-up: {names}"
    bar = income_bar(ctx["month_income"], ctx["goal"])
    prompt = MORNING_TEMPLATE.format(
        time="ранок",
        context_block=f"Прогрес: {bar}{overdue_note}",
    )
    ai_msg = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=int(chat_id))
    await context.bot.send_message(
        chat_id=int(chat_id),
        text=f"🌅 <b>Доброго ранку!</b>\n\n{ai_msg}",
        parse_mode="HTML",
    )

    # Auto-generate today's task plan if not already set, and show it
    import keyboards
    from handlers.tasks import generate_daily_tasks, format_tasks_text, today as today_str
    existing = await db.get_tasks(today_str())
    if not existing:
        proposed = await generate_daily_tasks(ctx, bot=context.bot, chat_id=int(chat_id))
        if proposed:
            await db.add_tasks(today_str(), proposed, source="ai")
    tasks = await db.get_tasks(today_str())
    if tasks:
        await context.bot.send_message(
            chat_id=int(chat_id),
            text=format_tasks_text(tasks),
            parse_mode="HTML",
            reply_markup=keyboards.tasks_keyboard(tasks),
        )


async def evening_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_income"], ctx["goal"])
    ai_msg = await ai_client.ask(
        f"Нагадай про вечірній check-in. Прогрес: {bar}. Скажи одну фразу.",
        ctx,
        bot=context.bot, chat_id=int(chat_id),
    )
    await context.bot.send_message(
        chat_id=int(chat_id),
        text=f"🌆 {ai_msg}\n\nВідправ /evening щоб підбити підсумок дня.",
        parse_mode="HTML",
    )


# ── ConversationHandlers ──────────────────────────────────────────────────────

def morning_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("morning", morning_start),
            CallbackQueryHandler(morning_start, pattern="^cmd_morning$"),
        ],
        states={
            MORNING_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, morning_plan)],
            MORNING_BLOCKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, morning_blocker)],
        },
        fallbacks=[CommandHandler("cancel", morning_cancel)],
        per_user=True,
        per_chat=True,
    )


def evening_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("evening", evening_start),
            CallbackQueryHandler(evening_start, pattern="^cmd_evening$"),
        ],
        states={
            EVENING_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, evening_review)],
            EVENING_NUMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, evening_numbers)],
            EVENING_MOOD: [CallbackQueryHandler(evening_mood, pattern="^mood_")],
        },
        fallbacks=[CommandHandler("cancel", evening_cancel)],
        per_user=True,
        per_chat=True,
    )
