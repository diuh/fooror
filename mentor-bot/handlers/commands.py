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
from formatters import (
    format_checkin_history,
    format_income_history,
    format_lead,
    format_leads_list,
    format_pipeline,
    income_bar,
    income_breakdown,
    split_message,
)

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_user.id)
    existing = await db.get_config("user_telegram_id")
    if not existing:
        await db.set_config("user_telegram_id", chat_id)

    name = update.effective_user.first_name or "друже"
    await update.message.reply_text(
        f"Привіт, {name}! 👋\n\n"
        "Я твій AI-ментор на шляху до <b>$10 000/місяць</b> від веб-дизайну та розробки.\n\n"
        "Що я можу:\n"
        "• Щоденні check-in о 10:00 і 20:00\n"
        "• Трекінг доходів та піпелайн лідів\n"
        "• Допомога з пропозиціями та цінами\n"
        "• Ідеї контенту для LinkedIn/Behance\n\n"
        "Починаємо! 👇",
        parse_mode="HTML",
        reply_markup=keyboards.main_menu(),
    )


# ── /menu ─────────────────────────────────────────────────────────────────────

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Обери дію:", reply_markup=keyboards.main_menu())


# ── /status ───────────────────────────────────────────────────────────────────

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    pipeline = ctx["pipeline"]
    active = sum(
        pipeline.get(s, {}).get("n", 0) for s in ("new", "negotiation", "proposal")
    )
    active_val = sum(
        pipeline.get(s, {}).get("value", 0) for s in ("new", "negotiation", "proposal")
    )
    overdue = ctx.get("overdue_leads", [])
    streak = ctx.get("streak", 0)

    text = (
        f"📊 <b>Поточний статус</b>\n\n"
        f"💰 Чистий: {bar}\n"
        f"<i>{income_breakdown(ctx)}</i>\n"
        f"📅 Залишилось {ctx['days_left']} дн. | темп ${ctx['daily_pace']:,.0f}/день чистими\n\n"
        f"🔗 Активних лідів: {active} (≈${active_val:,.0f})\n"
        f"🔥 Streak: {streak} дн.\n"
    )
    if overdue:
        names = ", ".join(l["name"] for l in overdue[:3])
        text += f"\n⚠️ Прострочені follow-up: {names}"

    await update.message.reply_text(text, parse_mode="HTML")


# ── /help ─────────────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📋 <b>Команди:</b>\n\n"
        "<b>Навігація</b>\n"
        "/menu — головне меню\n"
        "/status — швидкий огляд\n\n"
        "<b>Дохід і витрати</b>\n"
        "/income — чистий прибуток місяця\n"
        "/income_add — додати оплату (+ витрати з неї)\n"
        "/income_history — історія по місяцях\n"
        "/expense_add — додати разову витрату\n"
        "/expenses — витрати місяця\n"
        "/subscriptions — підписки (додати/видалити)\n"
        "/sub_add — додати підписку\n"
        "/goal — переглянути/змінити ціль\n\n"
        "<b>Ліди</b>\n"
        "/leads — список лідів\n"
        "/lead_add — додати ліда\n"
        "/lead_update — змінити статус ліда\n"
        "/pipeline — воронка продажів\n"
        "/follow_up — прострочені follow-up\n\n"
        "<b>Продажі</b>\n"
        "/proposal — генерація пропозиції\n"
        "/price — калькулятор ціни\n"
        "/outreach — холодне повідомлення\n"
        "/objection — відпрацювання заперечення\n"
        "/pitch — elevator pitch\n\n"
        "<b>Планування</b>\n"
        "/plan_day — план задач на день\n"
        "/tasks — задачі на сьогодні\n"
        "/setgoal — поставити ціль на місяць\n"
        "/month_review — аналіз місяця\n"
        "/channels — підбір каналів залучення\n\n"
        "<b>Check-in</b>\n"
        "/morning — ранковий check-in\n"
        "/evening — вечірній review\n"
        "/checkin_history — останні 7 днів\n"
        "/streak — серія check-in\n\n"
        "<b>Контент</b>\n"
        "/post_idea — ідея посту\n"
        "/weekly_plan — план на тиждень\n"
        "/brand — порада по бренду\n"
        "/content_list — збережені ідеї\n\n"
        "<b>Ментор</b>\n"
        "/ask — вільне питання\n"
        "/review_week — тижневий ретроспектив\n"
        "/motivate — мотивація на основі цифр"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ── /income ───────────────────────────────────────────────────────────────────

async def income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    text = (
        f"💰 <b>Дохід {ctx['month']} (чистий прибуток)</b>\n\n"
        f"{bar}\n\n"
        f"Оборот: ${ctx['month_income']:,.0f}\n"
        f"Разові витрати: ${ctx['month_oneoff_expenses']:,.0f}\n"
        f"Підписки: ${ctx['subscriptions_total']:,.0f}\n"
        f"<b>Чистий прибуток: ${ctx['month_net']:,.0f}</b>\n\n"
        f"Залишилось до цілі: ${ctx['goal'] - ctx['month_net']:,.0f}\n"
        f"Днів: {ctx['days_left']} | Темп: ${ctx['daily_pace']:,.0f}/день чистими"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ── /income_add ───────────────────────────────────────────────────────────────

INCOME_AMOUNT, INCOME_DESC, INCOME_DATE, INCOME_COSTS = range(100, 104)

_NO_COST_WORDS = {"нема", "немає", "ні", "нi", "no", "0", "-", "—", "жодних"}


def parse_cost_lines(text: str) -> list[tuple[str, float]]:
    """Parse "дизайнер 200, розробник 300" → [("дизайнер",200),("розробник",300)].
    A bare number → ("інше", number). Returns [] for "нема"/empty."""
    if text.strip().lower() in _NO_COST_WORDS:
        return []
    result: list[tuple[str, float]] = []
    # Split on ; newline, or a comma that is NOT between digits (so "$1,200"
    # stays intact while "дизайнер 200, розробник 300" splits into two).
    for chunk in re.split(r"[;\n]+|,(?!\d)", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.search(r"(\d[\d\s.,]*)", chunk)
        if not m:
            continue
        try:
            amount = float(m.group(1).replace(" ", "").replace(",", ""))
        except ValueError:
            continue
        if amount <= 0:
            continue
        category = (chunk[: m.start()] + chunk[m.end():]).strip(" $:-—")
        result.append((category or "інше", amount))
    return result


async def income_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "💵 Скільки отримав? Введи суму в USD (наприклад: <b>1500</b>)",
        parse_mode="HTML",
    )
    return INCOME_AMOUNT


async def income_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(",", "").replace("$", "").strip())
    except ValueError:
        await update.message.reply_text("Введи число, наприклад: 1500")
        return INCOME_AMOUNT
    context.user_data["income_amount"] = amount
    await update.message.reply_text("Короткий опис (клієнт, проект):")
    return INCOME_DESC


async def income_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["income_desc"] = update.message.text
    await update.message.reply_text(
        "Дата оплати? (YYYY-MM-DD або 'сьогодні')",
        reply_markup=keyboards.skip_keyboard(),
    )
    return INCOME_DATE


async def _save_income_ask_costs(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_date: str, reply) -> int:
    amount = context.user_data.pop("income_amount")
    desc = context.user_data.pop("income_desc")
    income_id = await db.add_income(amount, desc, payment_date)
    context.user_data["income_id"] = income_id
    context.user_data["income_payment_date"] = payment_date
    context.user_data["income_amount_saved"] = amount
    await reply(
        f"✅ Оплата збережена: <b>${amount:,.0f}</b> — {desc}\n\n"
        "💸 Скільки з цієї оплати пішло на витрати і куди?\n"
        "Напиши, напр.: <code>дизайнер 200, розробник 300</code> "
        "(або «нема»)",
        parse_mode="HTML",
        reply_markup=keyboards.skip_keyboard(),
    )
    return INCOME_COSTS


async def income_add_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    payment_date = date.today().isoformat() if text.lower() in ("сьогодні", "today", "") else text
    return await _save_income_ask_costs(update, context, payment_date, update.message.reply_text)


async def income_add_skip_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _save_income_ask_costs(
        update, context, date.today().isoformat(), update.callback_query.message.reply_text
    )


async def _finish_income(reply, context: ContextTypes.DEFAULT_TYPE, costs_note: str) -> int:
    context.user_data.pop("income_id", None)
    context.user_data.pop("income_payment_date", None)
    context.user_data.pop("income_amount_saved", None)
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    await reply(
        f"{costs_note}💰 Чистий прибуток: {bar}\n<i>{income_breakdown(ctx)}</i>",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def income_add_costs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    costs = parse_cost_lines(update.message.text)
    income_id = context.user_data.get("income_id")
    payment_date = context.user_data.get("income_payment_date")
    if costs:
        for category, amount in costs:
            await db.add_expense(
                amount, category, description="з оплати",
                expense_date=payment_date, income_id=income_id, source="income",
            )
        total = sum(a for _, a in costs)
        breakdown = ", ".join(f"{c} ${a:,.0f}" for c, a in costs)
        note = f"✅ Витрати додано (${total:,.0f}): {breakdown}\n\n"
    else:
        note = "✅ Без витрат.\n\n"
    return await _finish_income(update.message.reply_text, context, note)


async def income_add_costs_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _finish_income(update.callback_query.message.reply_text, context, "✅ Без витрат.\n\n")


async def income_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def income_add_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("income_add", income_add_start)],
        states={
            INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_add_amount)],
            INCOME_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_add_desc)],
            INCOME_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, income_add_date),
                CallbackQueryHandler(income_add_skip_date, pattern="^skip$"),
            ],
            INCOME_COSTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, income_add_costs),
                CallbackQueryHandler(income_add_costs_skip, pattern="^skip$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", income_add_cancel)],
    )


# ── /income_history ───────────────────────────────────────────────────────────

async def income_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = await db.get_income_history()
    expenses_by_month = await db.get_expenses_by_month()
    await update.message.reply_text(
        format_income_history(rows, expenses_by_month), parse_mode="HTML"
    )


# ── /expense_add · /expenses ──────────────────────────────────────────────────

EXPENSE_AMOUNT, EXPENSE_DESC = range(104, 106)


async def expense_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(
        "💸 Скільки склала витрата? Введи суму в USD (наприклад: <b>60</b>)",
        parse_mode="HTML",
    )
    return EXPENSE_AMOUNT


async def expense_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(",", "").replace("$", "").strip())
    except ValueError:
        await update.message.reply_text("Введи число, наприклад: 60")
        return EXPENSE_AMOUNT
    context.user_data["expense_amount"] = amount
    await update.message.reply_text("На що? (категорія/опис, напр. «Figma» або «реклама»)")
    return EXPENSE_DESC


async def expense_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = context.user_data.pop("expense_amount")
    category = update.message.text.strip()
    await db.add_expense(amount, category, source="manual")
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    await update.message.reply_text(
        f"✅ Витрата додана: <b>${amount:,.0f}</b> — {category}\n\n"
        f"💰 Чистий прибуток: {bar}\n<i>{income_breakdown(ctx)}</i>",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def expense_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def expense_add_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("expense_add", expense_add_start),
            CallbackQueryHandler(expense_add_start, pattern="^cmd_expense_add$"),
        ],
        states={
            EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_add_amount)],
            EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_add_desc)],
        },
        fallbacks=[CommandHandler("cancel", expense_add_cancel)],
    )


async def expenses_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    ctx = await db.build_context_snapshot()
    rows = await db.get_month_expense_rows()
    subs = await db.get_subscriptions()

    lines = [f"💸 <b>Витрати {ctx['month']}</b>\n"]
    if rows:
        lines.append("<b>Разові:</b>")
        for r in rows:
            tag = " (з оплати)" if r["source"] == "income" else ""
            lines.append(f"  • {r['category'] or 'інше'}: ${r['amount']:,.0f}{tag}")
    else:
        lines.append("Разових витрат цього місяця немає.")
    lines.append("")
    if subs:
        lines.append("<b>Підписки (щомісяця):</b>")
        for s in subs:
            lines.append(f"  🔁 {s['name']}: ${s['amount']:,.0f}")
    else:
        lines.append("Підписок немає. Додай: /sub_add")
    lines.append(
        f"\n<b>Підсумок:</b>\nОборот ${ctx['month_income']:,.0f} − разові "
        f"${ctx['month_oneoff_expenses']:,.0f} − підписки ${ctx['subscriptions_total']:,.0f} "
        f"= <b>${ctx['month_net']:,.0f}</b> чистими"
    )
    await target.reply_text("\n".join(lines), parse_mode="HTML")


# ── /subscriptions · /sub_add ─────────────────────────────────────────────────

SUB_NAME, SUB_AMOUNT = range(106, 108)


async def subscriptions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    subs = await db.get_subscriptions()
    if not subs:
        await target.reply_text(
            "🔁 Підписок ще немає.\n\nДодай свою першу: /sub_add"
        )
        return
    total = sum(s["amount"] for s in subs)
    lines = ["🔁 <b>Активні підписки</b>\n"]
    for s in subs:
        lines.append(f"  • {s['name']}: ${s['amount']:,.0f}/міс")
    lines.append(f"\n<b>Разом: ${total:,.0f}/міс</b>\n\nДодати: /sub_add")
    await target.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboards.subscriptions_keyboard(subs),
    )


async def sub_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    sub_id = int(query.data.split("_")[1])
    await db.delete_subscription(sub_id)
    await query.answer("🗑 Видалено")
    subs = await db.get_subscriptions()
    if not subs:
        try:
            await query.edit_message_text("🔁 Підписок більше немає.\n\nДодати: /sub_add")
        except Exception:
            pass
        return
    total = sum(s["amount"] for s in subs)
    lines = ["🔁 <b>Активні підписки</b>\n"]
    for s in subs:
        lines.append(f"  • {s['name']}: ${s['amount']:,.0f}/міс")
    lines.append(f"\n<b>Разом: ${total:,.0f}/міс</b>\n\nДодати: /sub_add")
    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=keyboards.subscriptions_keyboard(subs),
        )
    except Exception:
        pass


async def sub_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text("🔁 Назва підписки (напр. «Adobe CC», «ChatGPT»):")
    return SUB_NAME


async def sub_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["sub_name"] = update.message.text.strip()
    await update.message.reply_text("Скільки коштує на місяць у USD? (напр. 60)")
    return SUB_AMOUNT


async def sub_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(",", "").replace("$", "").strip())
    except ValueError:
        await update.message.reply_text("Введи число, наприклад: 60")
        return SUB_AMOUNT
    name = context.user_data.pop("sub_name")
    await db.add_subscription(name, amount)
    total = await db.get_subscriptions_total()
    await update.message.reply_text(
        f"✅ Підписка додана: <b>{name}</b> — ${amount:,.0f}/міс\n\n"
        f"Усього підписок: ${total:,.0f}/міс",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def sub_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def sub_add_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("sub_add", sub_add_start),
            CallbackQueryHandler(sub_add_start, pattern="^cmd_sub_add$"),
        ],
        states={
            SUB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_add_name)],
            SUB_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_add_amount)],
        },
        fallbacks=[CommandHandler("cancel", sub_add_cancel)],
    )


# ── /goal ─────────────────────────────────────────────────────────────────────

async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = await db.get_config("monthly_goal") or "10000"
    if context.args:
        try:
            new_goal = float(context.args[0].replace(",", "").replace("$", ""))
            await db.set_config("monthly_goal", str(new_goal))
            await update.message.reply_text(f"✅ Ціль змінена: <b>${new_goal:,.0f}/місяць</b>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("Введи число: /goal 12000")
    else:
        await update.message.reply_text(
            f"🎯 Поточна ціль: <b>${float(current):,.0f}/місяць</b>\n\nЩоб змінити: /goal 12000",
            parse_mode="HTML",
        )


# ── /leads ────────────────────────────────────────────────────────────────────

async def leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    all_leads = await db.get_leads()
    text = f"🔗 <b>Активні ліди ({len(all_leads)}):</b>\n\n{format_leads_list(all_leads)}"
    for part in split_message(text):
        await update.message.reply_text(part, parse_mode="HTML")


# ── /lead_add ─────────────────────────────────────────────────────────────────

LEAD_NAME, LEAD_TYPE_CB, LEAD_VALUE, LEAD_SOURCE, LEAD_NOTES_OPT = range(200, 205)


async def lead_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ім'я клієнта або назва компанії:")
    return LEAD_NAME


async def lead_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["lead_name"] = update.message.text
    await update.message.reply_text(
        "Тип проекту:",
        reply_markup=keyboards.proposal_type_keyboard(),
    )
    return LEAD_TYPE_CB


async def lead_add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    type_map = {
        "ptype_landing": "Лендінг",
        "ptype_corporate": "Корпоративний",
        "ptype_ecommerce": "Інтернет-магазин",
        "ptype_support": "Підтримка",
    }
    context.user_data["lead_type"] = type_map.get(update.callback_query.data, "")
    await update.callback_query.message.reply_text(
        "Очікувана вартість проекту в USD (або 0 якщо невідомо):"
    )
    return LEAD_VALUE


async def lead_add_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = float(update.message.text.replace(",", "").replace("$", "").strip())
    except ValueError:
        value = 0
    context.user_data["lead_value"] = value
    await update.message.reply_text(
        "Звідки ліда? (referral / linkedin / behance / cold / inbound / other)",
        reply_markup=keyboards.skip_keyboard(),
    )
    return LEAD_SOURCE


async def lead_add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["lead_source"] = update.message.text
    await update.message.reply_text(
        "Нотатки або наступна дія? (або пропусти)",
        reply_markup=keyboards.skip_keyboard(),
    )
    return LEAD_NOTES_OPT


async def lead_add_source_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["lead_source"] = ""
    await update.callback_query.message.reply_text(
        "Нотатки або наступна дія? (або пропусти)",
        reply_markup=keyboards.skip_keyboard(),
    )
    return LEAD_NOTES_OPT


async def lead_add_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    notes = update.message.text
    lead_id = await db.add_lead(
        name=context.user_data.pop("lead_name"),
        project_type=context.user_data.pop("lead_type", ""),
        estimated_value=context.user_data.pop("lead_value", 0),
        source=context.user_data.pop("lead_source", ""),
        notes=notes,
    )
    lead = await db.get_lead(lead_id)
    await update.message.reply_text(
        f"✅ Ліда додано!\n\n{format_lead(lead)}",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def lead_add_notes_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    lead_id = await db.add_lead(
        name=context.user_data.pop("lead_name"),
        project_type=context.user_data.pop("lead_type", ""),
        estimated_value=context.user_data.pop("lead_value", 0),
        source=context.user_data.pop("lead_source", ""),
    )
    lead = await db.get_lead(lead_id)
    await update.callback_query.message.reply_text(
        f"✅ Ліда додано!\n\n{format_lead(lead)}",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def lead_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def lead_add_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("lead_add", lead_add_start)],
        states={
            LEAD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_add_name)],
            LEAD_TYPE_CB: [CallbackQueryHandler(lead_add_type, pattern="^ptype_")],
            LEAD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_add_value)],
            LEAD_SOURCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_add_source),
                CallbackQueryHandler(lead_add_source_skip, pattern="^skip$"),
            ],
            LEAD_NOTES_OPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_add_notes),
                CallbackQueryHandler(lead_add_notes_skip, pattern="^skip$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", lead_add_cancel)],
    )


# ── /lead_update ──────────────────────────────────────────────────────────────

async def lead_update_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    all_leads = await db.get_leads()
    if not all_leads:
        await update.message.reply_text("Активних лідів немає. Додай через /lead_add")
        return
    lines = ["Обери ліда для оновлення:\n"]
    for l in all_leads:
        lines.append(f"/lead_update_{l['id']} — {l['name']} [{l['status']}]")
    await update.message.reply_text("\n".join(lines))


async def lead_update_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        lead_id = int(context.matches[0].group(1))
    except (IndexError, ValueError):
        return
    lead = await db.get_lead(lead_id)
    if not lead:
        await update.message.reply_text("Ліда не знайдено.")
        return
    await update.message.reply_text(
        f"{format_lead(lead)}\n\nЗмінити статус:",
        parse_mode="HTML",
        reply_markup=keyboards.lead_status_keyboard(lead_id),
    )


async def lead_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, lead_id_str, new_status = query.data.split("_", 2)
    lead_id = int(lead_id_str)
    await db.update_lead(lead_id, status=new_status)
    lead = await db.get_lead(lead_id)
    await query.message.reply_text(
        f"✅ Статус оновлено\n\n{format_lead(lead)}",
        parse_mode="HTML",
    )


# ── Close lead → log income (sync) ────────────────────────────────────────────

CLOSE_AMOUNT, CLOSE_COSTS = range(108, 110)


async def close_lead_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lead_id = int(query.data.split("_")[1])
    lead = await db.get_lead(lead_id)
    context.user_data["close_lead_id"] = lead_id
    context.user_data["close_lead_name"] = lead["name"] if lead else "лід"
    await query.message.reply_text(
        f"🤝 Закриваємо угоду з <b>{context.user_data['close_lead_name']}</b>.\n\n"
        "💰 Яку суму отримано? (введи число або 0, якщо без оплати)",
        parse_mode="HTML",
    )
    return CLOSE_AMOUNT


async def close_lead_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(",", "").replace("$", "").strip())
    except ValueError:
        await update.message.reply_text("Введи число, наприклад: 1800 (або 0)")
        return CLOSE_AMOUNT
    context.user_data["close_amount"] = amount
    if amount <= 0:
        return await _finalize_close(update.message.reply_text, context, [])
    await update.message.reply_text(
        "Скільки з цієї суми пішло на витрати і куди?\n"
        "Напр.: <code>дизайнер 200, розробник 300</code> (або «нема»)",
        parse_mode="HTML",
        reply_markup=keyboards.skip_keyboard(),
    )
    return CLOSE_COSTS


async def close_lead_costs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    costs = parse_cost_lines(update.message.text)
    return await _finalize_close(update.message.reply_text, context, costs)


async def close_lead_costs_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _finalize_close(update.callback_query.message.reply_text, context, [])


async def _finalize_close(reply, context: ContextTypes.DEFAULT_TYPE, costs: list) -> int:
    lead_id = context.user_data.pop("close_lead_id")
    name = context.user_data.pop("close_lead_name", "лід")
    amount = context.user_data.pop("close_amount", 0)
    await db.update_lead(lead_id, status="closed", actual_value=amount)
    if amount > 0:
        income_id = await db.add_income(amount, name, lead_id=lead_id)
        for category, c_amount in costs:
            await db.add_expense(
                c_amount, category, description="з оплати",
                income_id=income_id, source="income",
            )
    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    note = f"✅ Угоду з <b>{name}</b> закрито"
    note += f" (+${amount:,.0f})." if amount > 0 else " без оплати."
    await reply(
        f"{note}\n\n💰 Чистий прибуток: {bar}\n<i>{income_breakdown(ctx)}</i>",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def close_lead_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def close_lead_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(close_lead_start, pattern=r"^lstatus_\d+_closed$")],
        states={
            CLOSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, close_lead_amount)],
            CLOSE_COSTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, close_lead_costs),
                CallbackQueryHandler(close_lead_costs_skip, pattern="^skip$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", close_lead_cancel)],
    )


# ── /pipeline ─────────────────────────────────────────────────────────────────

async def pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    summary = await db.get_pipeline_summary()
    text = f"📊 <b>Pipeline:</b>\n\n{format_pipeline(summary)}"
    await update.message.reply_text(text, parse_mode="HTML")


# ── /follow_up ────────────────────────────────────────────────────────────────

async def follow_up(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    overdue = await db.get_overdue_leads()
    if not overdue:
        await update.message.reply_text("✅ Прострочених follow-up немає!")
        return
    text = f"⚠️ <b>Прострочені follow-up ({len(overdue)}):</b>\n\n{format_leads_list(overdue)}"
    await update.message.reply_text(text, parse_mode="HTML")


# ── /streak ───────────────────────────────────────────────────────────────────

async def streak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = await db.get_streak()
    if s == 0:
        await update.message.reply_text("Стрік поки 0. Зроби вечірній check-in щоб почати! /evening")
    elif s == 1:
        await update.message.reply_text("🔥 Стрік: 1 день. Продовжуй!")
    else:
        await update.message.reply_text(f"🔥 Стрік: <b>{s} днів поспіль!</b>", parse_mode="HTML")


# ── /checkin_history ──────────────────────────────────────────────────────────

async def checkin_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logs = await db.get_checkin_history(7)
    text = f"📋 <b>Останні check-in:</b>\n\n{format_checkin_history(logs)}"
    await update.message.reply_text(text, parse_mode="HTML")


# ── /ask ──────────────────────────────────────────────────────────────────────

ASK_STATE = 300


async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Запитай ментора:")
    else:
        if context.args:
            question = " ".join(context.args)
            ctx = await db.build_context_snapshot()
            answer = await ai_client.ask(question, ctx, bot=context.bot, chat_id=update.effective_chat.id)
            for part in split_message(answer):
                await update.message.reply_text(part)
            return ConversationHandler.END
        await update.message.reply_text("Запитай ментора:")
    return ASK_STATE


async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ctx = await db.build_context_snapshot()
    answer = await ai_client.ask(update.message.text, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    for part in split_message(answer):
        await update.message.reply_text(part)
    return ConversationHandler.END


async def ask_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


def ask_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("ask", ask_start),
            CallbackQueryHandler(ask_start, pattern="^cmd_ask$"),
        ],
        states={
            ASK_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        },
        fallbacks=[CommandHandler("cancel", ask_cancel)],
    )


# ── /review_week ──────────────────────────────────────────────────────────────

async def review_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from prompts.templates import REVIEW_WEEK_TEMPLATE
    ctx = await db.build_context_snapshot()
    logs = await db.get_checkin_history(7)
    checkin_summary = format_checkin_history(logs) if logs else "Немає check-in за тиждень."
    prompt = REVIEW_WEEK_TEMPLATE.format(
        context_block="(дивись у системному контексті)",
        checkin_summary=checkin_summary,
    )
    answer = await ai_client.ask_long(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    for part in split_message(answer):
        await update.message.reply_text(part)


# ── /motivate ─────────────────────────────────────────────────────────────────

async def motivate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from prompts.templates import MOTIVATE_TEMPLATE
    ctx = await db.build_context_snapshot()
    prompt = MOTIVATE_TEMPLATE.format(context_block="(дивись у системному контексті)")
    answer = await ai_client.ask(prompt, ctx, bot=context.bot, chat_id=update.effective_chat.id)
    await update.message.reply_text(answer)


# ── /content_list ─────────────────────────────────────────────────────────────

async def content_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ideas = await db.get_content_ideas()
    if not ideas:
        await update.message.reply_text("Збережених ідей немає. Спробуй /post_idea")
        return
    lines = [f"📝 <b>Ідеї контенту ({len(ideas)}):</b>\n"]
    for idea in ideas[:15]:
        icon = {"linkedin": "💼", "behance": "🎨", "telegram": "✈️", "instagram": "📸"}.get(idea["platform"], "•")
        lines.append(f"{icon} [{idea['status']}] <b>{idea['title']}</b>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── Callback query dispatcher ─────────────────────────────────────────────────

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    cmd = query.data
    cmd_map = {
        "cmd_income": income,
        "cmd_leads": leads,
        "cmd_pipeline": pipeline,
        "cmd_expenses": expenses_cmd,
        "cmd_subscriptions": subscriptions_cmd,
    }
    if cmd in cmd_map:
        await cmd_map[cmd](update, context)
    elif cmd == "cancel":
        await query.message.reply_text("Скасовано.")
