import re
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
from formatters import income_bar, split_message
from prompts.templates import (
    CHANNELS_TEMPLATE,
    DAILY_PLAN_TEMPLATE,
    MONTH_ANALYSIS_TEMPLATE,
    MONTHLY_GOAL_TEMPLATE,
    PLAN_EDIT_TEMPLATE,
)

# State ranges (kept distinct per feature for clarity)
PLAN_REVIEW, PLAN_ADD_TASK = range(800, 802)
GOAL_Q1, GOAL_Q2, GOAL_Q3, GOAL_CONFIRM, GOAL_MANUAL = range(810, 815)
CH_Q1, CH_Q2, CH_Q3 = range(820, 823)


def today() -> str:
    return date.today().isoformat()


def is_weekend() -> bool:
    # Monday=0 … Saturday=5, Sunday=6
    return date.today().weekday() >= 5


def parse_task_lines(text: str) -> list[str]:
    tasks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("- ", "• ", "* ")):
            tasks.append(line[2:].strip())
        elif re.match(r"^\d+[.)]\s+", line):
            tasks.append(re.sub(r"^\d+[.)]\s+", "", line).strip())
    return [t for t in tasks if t][:7]


def parse_goal(text: str) -> float | None:
    m = re.search(r"ЦІЛЬ:\s*\$?\s*([\d.,\s]+)", text)
    if not m:
        return None
    num = re.sub(r"[,\s]", "", m.group(1)).rstrip(".")
    try:
        return float(num)
    except ValueError:
        return None


async def generate_daily_tasks(ctx: dict, bot=None, chat_id=None) -> list[str]:
    from prompts.system import build_context_block
    prompt = DAILY_PLAN_TEMPLATE.format(context_block=build_context_block(ctx))
    answer = await ai_client.ask(prompt, ctx, bot=bot, chat_id=chat_id)
    return parse_task_lines(answer)


def format_tasks_text(tasks: list[dict]) -> str:
    if not tasks:
        return "Задач на сьогодні ще немає. Склади план: /plan_day"
    done = sum(1 for t in tasks if t["done"])
    lines = [f"📋 <b>Задачі на сьогодні</b> ({done}/{len(tasks)})\n"]
    for t in tasks:
        mark = "✅" if t["done"] else "⬜️"
        lines.append(f"{mark} {t['title']}")
    lines.append("\nТапни задачу щоб відмітити виконаною.")
    return "\n".join(lines)


# ── /plan_day ─────────────────────────────────────────────────────────────────

async def plan_day_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    await msg.reply_text("⏳ Складаю план на сьогодні…")
    ctx = await db.build_context_snapshot()
    tasks = await generate_daily_tasks(ctx, bot=msg.get_bot(), chat_id=msg.chat_id)
    if not tasks:
        await msg.reply_text("Не вдалось згенерувати план. Спробуй ще раз: /plan_day")
        return ConversationHandler.END
    context.user_data["proposed_tasks"] = tasks
    preview = "\n".join(f"{i}. {t}" for i, t in enumerate(tasks, 1))
    await msg.reply_text(
        f"🎯 <b>Пропоную план на сьогодні:</b>\n\n{preview}",
        parse_mode="HTML",
        reply_markup=keyboards.plan_confirm_keyboard(),
    )
    return PLAN_REVIEW


async def plan_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    tasks = context.user_data.pop("proposed_tasks", [])
    await db.delete_tasks_for_date(today(), source="ai")
    if tasks:
        await db.add_tasks(today(), tasks, source="ai")
    saved = await db.get_tasks(today())
    await update.callback_query.message.reply_text(
        format_tasks_text(saved),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(saved),
    )
    return ConversationHandler.END


async def plan_regen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer("Генерую новий варіант…")
    msg = update.callback_query.message
    ctx = await db.build_context_snapshot()
    tasks = await generate_daily_tasks(ctx, bot=msg.get_bot(), chat_id=msg.chat_id)
    if not tasks:
        await msg.reply_text("Не вдалось. Спробуй /plan_day")
        return ConversationHandler.END
    context.user_data["proposed_tasks"] = tasks
    preview = "\n".join(f"{i}. {t}" for i, t in enumerate(tasks, 1))
    await msg.reply_text(
        f"🎯 <b>Новий варіант плану:</b>\n\n{preview}",
        parse_mode="HTML",
        reply_markup=keyboards.plan_confirm_keyboard(),
    )
    return PLAN_REVIEW


async def plan_add_own(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Напиши свою задачу (одну). Спочатку збережу запропонований план, потім додам твою."
    )
    # Persist proposed plan first so it isn't lost
    tasks = context.user_data.pop("proposed_tasks", [])
    await db.delete_tasks_for_date(today(), source="ai")
    if tasks:
        await db.add_tasks(today(), tasks, source="ai")
    return PLAN_ADD_TASK


async def plan_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await db.add_task(today(), update.message.text.strip(), source="user")
    saved = await db.get_tasks(today())
    await update.message.reply_text(
        format_tasks_text(saved),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(saved),
    )
    return ConversationHandler.END


async def plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def plan_day_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("plan_day", plan_day_start),
            CallbackQueryHandler(plan_day_start, pattern="^cmd_plan_day$"),
        ],
        states={
            PLAN_REVIEW: [
                CallbackQueryHandler(plan_accept, pattern="^plan_accept$"),
                CallbackQueryHandler(plan_regen, pattern="^plan_regen$"),
                CallbackQueryHandler(plan_add_own, pattern="^plan_add_own$"),
            ],
            PLAN_ADD_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_add_task)],
        },
        fallbacks=[CommandHandler("cancel", plan_cancel)],
    )


# ── /tasks + toggle ───────────────────────────────────────────────────────────

async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tasks = await db.get_tasks(today())
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text(
        format_tasks_text(tasks),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(tasks) if tasks else None,
    )


async def task_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    task_id = int(query.data.split("_")[1])
    new_done = await db.toggle_task(task_id)
    await query.answer("✅ Виконано!" if new_done else "↩️ Знято")
    tasks = await db.get_tasks(today())
    try:
        await query.edit_message_text(
            format_tasks_text(tasks),
            parse_mode="HTML",
            reply_markup=keyboards.tasks_keyboard(tasks),
        )
    except Exception:
        pass


# ── /setgoal (monthly goal wizard) ────────────────────────────────────────────

async def setgoal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(
        "🎯 <b>Ставимо реалістичну ціль на місяць</b>\n\n"
        "Кілька питань для калібрування.\n\n"
        "<b>1/3</b> Скільки годин на день реально можеш приділяти роботі "
        "(проекти + залучення клієнтів)?",
        parse_mode="HTML",
    )
    return GOAL_Q1


async def setgoal_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["goal_hours"] = update.message.text
    await update.message.reply_text(
        "<b>2/3</b> Що найбільше стримує зараз? "
        "(мало лідів / низькі ціни / брак часу / навички продажів / інше)",
        parse_mode="HTML",
    )
    return GOAL_Q2


async def setgoal_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["goal_blocker"] = update.message.text
    await update.message.reply_text(
        "<b>3/3</b> Наскільки впевнений що закриєш поточні угоди в pipeline? (1–10)",
        parse_mode="HTML",
    )
    return GOAL_Q3


async def setgoal_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["goal_confidence"] = update.message.text
    await update.message.reply_text("⏳ Аналізую і рахую реалістичну ціль…")

    ctx = await db.build_context_snapshot()
    history_rows = await db.get_income_history(4)
    history = "\n".join(f"- {r['month']}: ${r['total']:,.0f}" for r in history_rows) or "- немає даних за попередні місяці"
    survey = (
        f"- Годин на день: {context.user_data.get('goal_hours')}\n"
        f"- Головний стоп-фактор: {context.user_data.get('goal_blocker')}\n"
        f"- Впевненість у закритті угод (1-10): {context.user_data.get('goal_confidence')}"
    )

    from prompts.system import build_context_block
    prompt = MONTHLY_GOAL_TEMPLATE.format(
        month=ctx["month"],
        history=history,
        survey=survey,
        context_block=build_context_block(ctx),
    )
    answer = await ai_client.ask_long(
        prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id
    )
    suggested = parse_goal(answer)
    context.user_data["goal_survey"] = survey
    context.user_data["goal_rationale"] = answer

    for part in split_message(answer):
        await update.message.reply_text(part)
    await update.message.reply_text(
        "Яку ціль ставимо?",
        reply_markup=keyboards.goal_confirm_keyboard(suggested),
    )
    return GOAL_CONFIRM


async def setgoal_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    goal = float(update.callback_query.data.split("_")[2])
    await _save_goal(goal, context)
    await update.callback_query.message.reply_text(
        f"✅ Ціль на місяць встановлена: <b>${goal:,.0f}</b>\n\nЩодня складай план: /plan_day",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def setgoal_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Введи свою ціль у USD (наприклад: 6000):")
    return GOAL_MANUAL


async def setgoal_manual_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        goal = float(update.message.text.replace(",", "").replace("$", "").strip())
    except ValueError:
        await update.message.reply_text("Введи число, наприклад: 6000")
        return GOAL_MANUAL
    await _save_goal(goal, context)
    await update.message.reply_text(
        f"✅ Ціль на місяць встановлена: <b>${goal:,.0f}</b>\n\nЩодня складай план: /plan_day",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def _save_goal(goal: float, context: ContextTypes.DEFAULT_TYPE) -> None:
    month = date.today().strftime("%Y-%m")
    await db.set_config("monthly_goal", str(goal))
    await db.save_monthly_plan(
        month, goal,
        rationale=context.user_data.pop("goal_rationale", ""),
        survey=context.user_data.pop("goal_survey", ""),
    )


async def setgoal_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def setgoal_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("setgoal", setgoal_start),
            CallbackQueryHandler(setgoal_start, pattern="^cmd_setgoal$"),
        ],
        states={
            GOAL_Q1: [MessageHandler(filters.TEXT & ~filters.COMMAND, setgoal_q1)],
            GOAL_Q2: [MessageHandler(filters.TEXT & ~filters.COMMAND, setgoal_q2)],
            GOAL_Q3: [MessageHandler(filters.TEXT & ~filters.COMMAND, setgoal_q3)],
            GOAL_CONFIRM: [
                CallbackQueryHandler(setgoal_accept, pattern="^goal_accept_"),
                CallbackQueryHandler(setgoal_manual, pattern="^goal_manual$"),
            ],
            GOAL_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, setgoal_manual_value)],
        },
        fallbacks=[CommandHandler("cancel", setgoal_cancel)],
    )


# ── /month_review (manual) + month-end job ────────────────────────────────────

async def _run_month_analysis(ctx: dict, month: str, bot, chat_id) -> str:
    pipeline = ctx.get("pipeline", {})
    closed_deals = pipeline.get("closed", {}).get("n", 0)
    stats = await db.get_month_task_stats(month)
    from prompts.system import build_context_block
    prompt = MONTH_ANALYSIS_TEMPLATE.format(
        month=month,
        context_block=build_context_block(ctx),
        month_income=ctx["month_income"],
        goal=ctx["goal"],
        pct=ctx["pct"],
        tasks_done=stats["done"],
        tasks_total=stats["total"],
        closed_deals=closed_deals,
        streak=ctx["streak"],
    )
    answer = await ai_client.ask_long(prompt, ctx, bot=bot, chat_id=chat_id)
    await db.save_month_analysis(month, answer)
    return answer


async def month_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Аналізую місяць…")
    ctx = await db.build_context_snapshot()
    answer = await _run_month_analysis(
        ctx, ctx["month"], bot=context.bot, chat_id=update.effective_chat.id
    )
    for part in split_message(answer):
        await update.message.reply_text(part)
    await update.message.reply_text("Готовий поставити ціль на наступний місяць? /setgoal")


# ── /channels (acquisition channels wizard) ───────────────────────────────────

async def channels_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(
        "📡 <b>Підбір каналів залучення клієнтів</b>\n\n"
        "<b>1/3</b> Опиши свою нішу/спеціалізацію "
        "(наприклад: лендінги для стартапів, сайти для ресторанів):",
        parse_mode="HTML",
    )
    return CH_Q1


async def channels_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ch_niche"] = update.message.text
    await update.message.reply_text(
        "<b>2/3</b> Скільки годин на тиждень готовий приділяти залученню клієнтів?",
        parse_mode="HTML",
    )
    return CH_Q2


async def channels_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ch_hours"] = update.message.text
    await update.message.reply_text(
        "<b>3/3</b> Твої сильні сторони? "
        "(портфоліо / нетворкінг / контент / холодні продажі / англійська / інше)",
        parse_mode="HTML",
    )
    return CH_Q3


async def channels_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ch_strengths"] = update.message.text
    await update.message.reply_text("⏳ Підбираю канали…")

    ctx = await db.build_context_snapshot()
    survey = (
        f"- Ніша: {context.user_data.pop('ch_niche', '')}\n"
        f"- Годин на тиждень на залучення: {context.user_data.pop('ch_hours', '')}\n"
        f"- Сильні сторони: {context.user_data.pop('ch_strengths', '')}"
    )
    from prompts.system import build_context_block
    prompt = CHANNELS_TEMPLATE.format(
        survey=survey,
        context_block=build_context_block(ctx),
    )
    answer = await ai_client.ask_long(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    for part in split_message(answer):
        await update.message.reply_text(part)
    return ConversationHandler.END


async def channels_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def channels_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("channels", channels_start),
            CallbackQueryHandler(channels_start, pattern="^cmd_channels$"),
        ],
        states={
            CH_Q1: [MessageHandler(filters.TEXT & ~filters.COMMAND, channels_q1)],
            CH_Q2: [MessageHandler(filters.TEXT & ~filters.COMMAND, channels_q2)],
            CH_Q3: [MessageHandler(filters.TEXT & ~filters.COMMAND, channels_q3)],
        },
        fallbacks=[CommandHandler("cancel", channels_cancel)],
    )


# ── Scheduled jobs ────────────────────────────────────────────────────────────

async def midday_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    tasks = await db.get_tasks(today())
    if not tasks:
        if is_weekend():
            return  # don't nag to make a plan on weekends
        await context.bot.send_message(
            chat_id=int(chat_id),
            text="🕒 Полудень. План на сьогодні ще не складено — давай зробимо: /plan_day",
        )
        return
    pending = [t for t in tasks if not t["done"]]
    if not pending:
        ctx = await db.build_context_snapshot()
        msg = await ai_client.ask(
            "Користувач уже виконав усі задачі на сьогодні до обіду. Похвали коротко і запропонуй один бонусний крок.",
            ctx, bot=context.bot, chat_id=int(chat_id),
        )
        await context.bot.send_message(chat_id=int(chat_id), text=f"🔥 {msg}")
        return
    await context.bot.send_message(
        chat_id=int(chat_id),
        text=f"🕒 <b>Нагадування</b>\nЗалишилось {len(pending)} задач(і) на сьогодні:\n\n"
             + format_tasks_text(tasks),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(tasks),
    )


async def free_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global fallback for free-text messages outside active conversations.

    If today's tasks exist, interprets the message as a potential plan edit.
    Otherwise forwards it to the AI mentor as a general question.
    """
    text = update.message.text.strip()
    tasks = await db.get_tasks(today())
    ctx = await db.build_context_snapshot()

    if not tasks:
        answer = await ai_client.ask(text, ctx, bot=context.bot, chat_id=update.effective_chat.id)
        for part in split_message(answer):
            await update.message.reply_text(part)
        return

    task_lines = "\n".join(
        f"{i}. {'[✅]' if t['done'] else '[ ]'} {t['title']}"
        for i, t in enumerate(tasks, 1)
    )
    prompt = PLAN_EDIT_TEMPLATE.format(
        current_tasks=task_lines,
        user_message=text,
    )
    answer = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)

    if "ОНОВЛЕНИЙ ПЛАН:" in answer:
        plan_part = answer.split("ОНОВЛЕНИЙ ПЛАН:", 1)[1]
        new_tasks = parse_task_lines(plan_part)
        if new_tasks:
            await db.delete_tasks_for_date(today())
            await db.add_tasks(today(), new_tasks, source="ai")
            saved = await db.get_tasks(today())
            await update.message.reply_text(
                "✏️ " + format_tasks_text(saved),
                parse_mode="HTML",
                reply_markup=keyboards.tasks_keyboard(saved),
            )
            return

    for part in split_message(answer):
        await update.message.reply_text(part)


async def month_end_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs daily at 19:00; only acts on the last day of the month."""
    import datetime as dt
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    today_d = date.today()
    tomorrow = today_d + dt.timedelta(days=1)
    if tomorrow.month == today_d.month:
        return  # not the last day of the month yet

    ctx = await db.build_context_snapshot()
    await context.bot.send_message(
        chat_id=int(chat_id),
        text="📅 <b>Місяць завершується!</b> Готую підсумок…",
        parse_mode="HTML",
    )
    answer = await _run_month_analysis(ctx, ctx["month"], bot=context.bot, chat_id=int(chat_id))
    for part in split_message(answer):
        await context.bot.send_message(chat_id=int(chat_id), text=part)
    await context.bot.send_message(
        chat_id=int(chat_id),
        text="Поставимо ціль на наступний місяць з урахуванням цих результатів? /setgoal",
    )
