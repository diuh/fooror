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
    MONTH_PLAN_TEMPLATE,
    MONTHLY_GOAL_TEMPLATE,
    WEEK_PLAN_TEMPLATE,
)

# State ranges (kept distinct per feature for clarity)
PLAN_REVIEW, PLAN_ADD_TASK = range(800, 802)
GOAL_Q1, GOAL_Q2, GOAL_Q3, GOAL_CONFIRM, GOAL_MANUAL = range(810, 815)
CH_Q1, CH_Q2, CH_Q3 = range(820, 823)


def today() -> str:
    return date.today().isoformat()


def week_key(d: date | None = None) -> str:
    """ISO week key like '2026-W22' (Monday-based)."""
    d = d or date.today()
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_key(d: date | None = None) -> str:
    return (d or date.today()).strftime("%Y-%m")


# Metadata for the three planning horizons. `key` returns the current period
# key; the rest drives wording shown to the user.
HORIZON = {
    "day": {
        "key": today,
        "emoji": "📋",
        "list_title": "Задачі на сьогодні",
        "noun": "задачі на сьогодні",
        "cmd": "/plan_day",
        "hint": "Тапни задачу щоб відмітити виконаною.",
    },
    "week": {
        "key": week_key,
        "emoji": "🗓",
        "list_title": "Пріоритети тижня",
        "noun": "пріоритети на тиждень",
        "cmd": "/plan_week",
        "hint": "Тапни пункт щоб відмітити виконаним.",
    },
    "month": {
        "key": month_key,
        "emoji": "🎯",
        "list_title": "Цілі місяця",
        "noun": "цілі на місяць",
        "cmd": "/plan_month",
        "hint": "Тапни ціль щоб відмітити досягнутою.",
    },
}


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


def _items_block(header: str, items: list[dict] | None) -> str:
    if not items:
        return ""
    lines = "\n".join(f"- {it['title']}" for it in items)
    return f"\n{header}\n{lines}\n"


async def generate_plan_items(
    horizon: str,
    ctx: dict,
    bot=None,
    chat_id=None,
    content_plan: str | None = None,
    upper_items: list[dict] | None = None,
) -> list[str]:
    """Generate plan items for a horizon, cascading from the level above:
    day ← week ← month. Day uses the fast model; week/month use the smart one."""
    from prompts.system import build_context_block
    cb = build_context_block(ctx)
    cp_block = f"\nКОНТЕНТ-ПЛАН:\n{content_plan}\n" if content_plan else ""

    if horizon == "day":
        week_block = _items_block(
            "ПЛАН НА ТИЖДЕНЬ (задачі мають бути кроками до цих пріоритетів):", upper_items
        )
        prompt = DAILY_PLAN_TEMPLATE.format(
            context_block=cb, week_plan_block=week_block, content_plan_block=cp_block
        )
        answer = await ai_client.ask(prompt, ctx, bot=bot, chat_id=chat_id)
    elif horizon == "week":
        month_block = _items_block(
            "ЦІЛІ НА МІСЯЦЬ (пріоритети мають бути кроками до них):", upper_items
        )
        prompt = WEEK_PLAN_TEMPLATE.format(
            context_block=cb, month_plan_block=month_block, content_plan_block=cp_block
        )
        answer = await ai_client.ask_long(prompt, ctx, bot=bot, chat_id=chat_id)
    else:  # month
        goal = ctx.get("goal")
        goal_block = f"\nФІНАНСОВА ЦІЛЬ МІСЯЦЯ: ${goal:,.0f}\n" if goal else ""
        prompt = MONTH_PLAN_TEMPLATE.format(
            context_block=cb, month=ctx.get("month", ""), goal_block=goal_block
        )
        answer = await ai_client.ask_long(prompt, ctx, bot=bot, chat_id=chat_id)

    return parse_task_lines(answer)


async def _upper_items(horizon: str) -> list[dict] | None:
    """Fetch the level-above plan that the given horizon cascades from."""
    if horizon == "day":
        return await db.get_tasks(week_key(), "week")
    if horizon == "week":
        return await db.get_tasks(month_key(), "month")
    return None


async def generate_daily_tasks(
    ctx: dict, bot=None, chat_id=None, content_plan: str | None = None
) -> list[str]:
    """Backward-compatible day generator used by the morning job."""
    week_items = await db.get_tasks(week_key(), "week")
    return await generate_plan_items(
        "day", ctx, bot=bot, chat_id=chat_id, content_plan=content_plan, upper_items=week_items
    )


def format_tasks_text(tasks: list[dict], horizon: str = "day") -> str:
    meta = HORIZON[horizon]
    if not tasks:
        return f"{meta['emoji']} <b>{meta['list_title']}</b>\n\nПлан ще не складено. Натисни кнопку нижче."
    done = sum(1 for t in tasks if t["done"])
    lines = [f"{meta['emoji']} <b>{meta['list_title']}</b> ({done}/{len(tasks)})\n"]
    for t in tasks:
        mark = "✅" if t["done"] else "⬜️"
        lines.append(f"{mark} {t['title']}")
    lines.append(f"\n{meta['hint']}")
    return "\n".join(lines)


# ── /plan_day · /plan_week · /plan_month (unified) ────────────────────────────

async def _plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE, horizon: str) -> int:
    context.user_data["plan_horizon"] = horizon
    meta = HORIZON[horizon]
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    await msg.reply_text(f"⏳ Складаю {meta['noun']}…")
    ctx = await db.build_context_snapshot()
    content_plan = context.user_data.get("last_content_plan")
    upper = await _upper_items(horizon)
    items = await generate_plan_items(
        horizon, ctx, bot=msg.get_bot(), chat_id=msg.chat_id,
        content_plan=content_plan, upper_items=upper,
    )
    if not items:
        await msg.reply_text(f"Не вдалось згенерувати. Спробуй ще раз: {meta['cmd']}")
        return ConversationHandler.END
    context.user_data["proposed_tasks"] = items
    preview = "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    await msg.reply_text(
        f"{meta['emoji']} <b>Пропоную {meta['noun']}:</b>\n\n{preview}",
        parse_mode="HTML",
        reply_markup=keyboards.plan_confirm_keyboard(),
    )
    return PLAN_REVIEW


async def plan_day_start(update, context):
    return await _plan_start(update, context, "day")


async def plan_week_start(update, context):
    return await _plan_start(update, context, "week")


async def plan_month_start(update, context):
    return await _plan_start(update, context, "month")


def _current_horizon(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("plan_horizon", "day")


async def plan_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    horizon = _current_horizon(context)
    pkey = HORIZON[horizon]["key"]()
    items = context.user_data.pop("proposed_tasks", [])
    await db.delete_tasks_for_period(pkey, horizon=horizon, source="ai")
    if items:
        await db.add_tasks(pkey, items, source="ai", horizon=horizon)
    saved = await db.get_tasks(pkey, horizon)
    await update.callback_query.message.reply_text(
        format_tasks_text(saved, horizon),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(saved),
    )
    return ConversationHandler.END


async def plan_regen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer("Генерую новий варіант…")
    horizon = _current_horizon(context)
    meta = HORIZON[horizon]
    msg = update.callback_query.message
    ctx = await db.build_context_snapshot()
    content_plan = context.user_data.get("last_content_plan")
    upper = await _upper_items(horizon)
    items = await generate_plan_items(
        horizon, ctx, bot=msg.get_bot(), chat_id=msg.chat_id,
        content_plan=content_plan, upper_items=upper,
    )
    if not items:
        await msg.reply_text(f"Не вдалось. Спробуй {meta['cmd']}")
        return ConversationHandler.END
    context.user_data["proposed_tasks"] = items
    preview = "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    await msg.reply_text(
        f"{meta['emoji']} <b>Новий варіант:</b>\n\n{preview}",
        parse_mode="HTML",
        reply_markup=keyboards.plan_confirm_keyboard(),
    )
    return PLAN_REVIEW


async def plan_add_own(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    horizon = _current_horizon(context)
    await update.callback_query.message.reply_text(
        "Напиши свій пункт (один). Спочатку збережу запропонований план, потім додам твій."
    )
    pkey = HORIZON[horizon]["key"]()
    items = context.user_data.pop("proposed_tasks", [])
    await db.delete_tasks_for_period(pkey, horizon=horizon, source="ai")
    if items:
        await db.add_tasks(pkey, items, source="ai", horizon=horizon)
    return PLAN_ADD_TASK


async def plan_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    horizon = _current_horizon(context)
    pkey = HORIZON[horizon]["key"]()
    await db.add_task(pkey, update.message.text.strip(), source="user", horizon=horizon)
    saved = await db.get_tasks(pkey, horizon)
    await update.message.reply_text(
        format_tasks_text(saved, horizon),
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
            CommandHandler("plan_week", plan_week_start),
            CommandHandler("plan_month", plan_month_start),
            CallbackQueryHandler(plan_day_start, pattern="^cmd_plan_day$"),
            CallbackQueryHandler(plan_week_start, pattern="^cmd_plan_week$"),
            CallbackQueryHandler(plan_month_start, pattern="^cmd_plan_month$"),
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


# ── /tasks · /week · /month + toggle + /plan overview ─────────────────────────

async def _show_horizon(update: Update, context: ContextTypes.DEFAULT_TYPE, horizon: str) -> None:
    pkey = HORIZON[horizon]["key"]()
    tasks = await db.get_tasks(pkey, horizon)
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text(
        format_tasks_text(tasks, horizon),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(tasks, horizon),
    )


async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_horizon(update, context, "day")


async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_horizon(update, context, "week")


async def month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_horizon(update, context, "month")


async def plan_overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all three horizons stacked: month → week → day."""
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    parts = []
    for horizon in ("month", "week", "day"):
        pkey = HORIZON[horizon]["key"]()
        tasks = await db.get_tasks(pkey, horizon)
        parts.append(format_tasks_text(tasks, horizon))
    await target.reply_text("\n\n".join(parts), parse_mode="HTML")


async def task_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    task_id = int(query.data.split("_")[1])
    task = await db.get_task(task_id)
    new_done = await db.toggle_task(task_id)
    await query.answer("✅ Виконано!" if new_done else "↩️ Знято")
    if not task:
        return
    horizon = task.get("horizon", "day")
    tasks = await db.get_tasks(task["period_key"], horizon)
    try:
        await query.edit_message_text(
            format_tasks_text(tasks, horizon),
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
        f"✅ Ціль на місяць встановлена: <b>${goal:,.0f}</b>\n\nТепер склади цілі місяця: /month",
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
        f"✅ Ціль на місяць встановлена: <b>${goal:,.0f}</b>\n\nТепер склади цілі місяця: /month",
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
        month_expenses=ctx["month_expenses"],
        month_net=ctx["month_net"],
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
    tasks = await db.get_tasks(today(), "day")
    if not tasks:
        if is_weekend():
            return  # don't nag to make a plan on weekends
        await context.bot.send_message(
            chat_id=int(chat_id),
            text="🕒 Полудень. План на сьогодні ще не складено.",
            reply_markup=keyboards.tasks_keyboard([], "day"),
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
             + format_tasks_text(tasks, "day"),
        parse_mode="HTML",
        reply_markup=keyboards.tasks_keyboard(tasks, "day"),
    )


async def month_start_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs daily at 9:00 Kyiv; only acts on the 1st of the month."""
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id or date.today().day != 1:
        return
    mkey = month_key()
    month_tasks = await db.get_tasks(mkey, "month")
    if not month_tasks:
        await context.bot.send_message(
            chat_id=int(chat_id),
            parse_mode="HTML",
            text=(
                "📅 <b>Новий місяць — новий старт!</b>\n\n"
                "Щоб план тижня і дня мали сенс, спочатку:\n\n"
                "1️⃣ /setgoal — встанови фінансову ціль місяця\n"
                "2️⃣ /month — склади цілі місяця\n\n"
                "Після цього /week і /tasks будуть каскадно виводитись з них."
            ),
        )


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
