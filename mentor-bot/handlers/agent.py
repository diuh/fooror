"""Natural-language agent: the bot's primary interface.

Free text goes through Claude with a set of tools that map to the bot's
actions (tasks, finances, leads, meetings). Safe/reversible actions run
immediately; money/external actions (income, meetings, closing a lead) are
staged as a pending confirmation with buttons before they take effect.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import ai_client
import database as db
import keyboards
from formatters import income_bar, income_breakdown, split_message
from handlers.tasks import format_tasks_text, month_key, today, week_key
from handlers import meetings

logger = logging.getLogger(__name__)


# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "set_today_tasks",
        "description": "Замінити список задач на СЬОГОДНІ повним новим списком.",
        "input_schema": {
            "type": "object",
            "properties": {"tasks": {"type": "array", "items": {"type": "string"}}},
            "required": ["tasks"],
        },
    },
    {
        "name": "set_week_priorities",
        "description": "Замінити пріоритети на ТИЖДЕНЬ повним новим списком.",
        "input_schema": {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            "required": ["items"],
        },
    },
    {
        "name": "set_month_goals",
        "description": "Замінити цілі на МІСЯЦЬ повним новим списком.",
        "input_schema": {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            "required": ["items"],
        },
    },
    {
        "name": "add_expense",
        "description": "Додати разову витрату (підписку додавай через add_subscription).",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "category": {"type": "string", "description": "на що (Figma, реклама, тощо)"},
            },
            "required": ["amount", "category"],
        },
    },
    {
        "name": "add_subscription",
        "description": "Додати рекурентну щомісячну підписку.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "amount": {"type": "number"}},
            "required": ["name", "amount"],
        },
    },
    {
        "name": "add_lead",
        "description": "Додати нового ліда у CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "project_type": {"type": "string"},
                "estimated_value": {"type": "number"},
                "source": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_lead_status",
        "description": "Змінити статус ліда (НЕ для закриття угоди — для закриття використай close_lead).",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_query": {"type": "string", "description": "імʼя/назва ліда"},
                "status": {"type": "string", "enum": ["new", "negotiation", "proposal", "rejected"]},
            },
            "required": ["lead_query", "status"],
        },
    },
    {
        "name": "update_content_plan",
        "description": "Зберегти/оновити контент-план на тиждень (теми постів по платформах).",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "get_overview",
        "description": "Отримати поточний дашборд: чистий прибуток, задачі, зустрічі, прострочені ліди.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "log_income",
        "description": "Записати отриману оплату (дохід). Потребує підтвердження користувача.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "description": {"type": "string", "description": "клієнт/проект"},
                "costs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "amount": {"type": "number"},
                        },
                        "required": ["category", "amount"],
                    },
                    "description": "витрати з цієї оплати (субпідрядники тощо)",
                },
            },
            "required": ["amount", "description"],
        },
    },
    {
        "name": "close_lead",
        "description": "Закрити угоду з лідом і записати отриманий дохід. Потребує підтвердження.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_query": {"type": "string"},
                "amount": {"type": "number"},
                "costs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "amount": {"type": "number"},
                        },
                        "required": ["category", "amount"],
                    },
                },
            },
            "required": ["lead_query", "amount"],
        },
    },
    {
        "name": "create_meeting",
        "description": "Запланувати зустріч у Google Calendar. Потребує підтвердження.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string", "description": "локальний час Києва YYYY-MM-DDTHH:MM"},
                "duration_min": {"type": "integer"},
                "online": {"type": "boolean"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "start"],
        },
    },
]


# ── Dialog memory ─────────────────────────────────────────────────────────────

def _remember(context: ContextTypes.DEFAULT_TYPE, role: str, text: str) -> None:
    dialog = context.user_data.setdefault("dialog", [])
    dialog.append({"role": role, "text": text})
    del dialog[:-8]


def _format_dialog(context: ContextTypes.DEFAULT_TYPE) -> str:
    dialog = context.user_data.get("dialog", [])
    if not dialog:
        return ""
    label = {"user": "Користувач", "assistant": "Ментор"}
    return "\n".join(f"{label[d['role']]}: {d['text']}" for d in dialog)


def _norm_costs(raw) -> list[tuple[str, float]]:
    out = []
    for c in raw or []:
        try:
            out.append((str(c.get("category") or "інше"), float(c.get("amount") or 0)))
        except (ValueError, TypeError, AttributeError):
            continue
    return [(cat, amt) for cat, amt in out if amt > 0]


# ── Tool execution ────────────────────────────────────────────────────────────

async def _execute_tool(name: str, args: dict, update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    msg = update.message

    # ── immediate, reversible actions ──
    if name in ("set_today_tasks", "set_week_priorities", "set_month_goals"):
        horizon, pkey, items = {
            "set_today_tasks": ("day", today(), args.get("tasks", [])),
            "set_week_priorities": ("week", week_key(), args.get("items", [])),
            "set_month_goals": ("month", month_key(), args.get("items", [])),
        }[name]
        items = [str(i).strip() for i in items if str(i).strip()]
        await db.replace_tasks(pkey, items, horizon=horizon)
        saved = await db.get_tasks(pkey, horizon)
        if saved:
            await msg.reply_text(
                format_tasks_text(saved, horizon), parse_mode="HTML",
                reply_markup=keyboards.tasks_keyboard(saved, horizon),
            )
            context.user_data["_card_sent"] = True
        return {"result": f"Оновлено ({len(items)} пунктів).", "stop": False}

    if name == "add_expense":
        amount = float(args["amount"])
        category = str(args.get("category") or "інше")
        await db.add_expense(amount, category, source="manual")
        ctx = await db.build_context_snapshot()
        return {"result": f"Витрату ${amount:,.0f} ({category}) додано. Чистий за місяць: ${ctx['month_net']:,.0f}.", "stop": False}

    if name == "add_subscription":
        name_s = str(args["name"])
        amount = float(args["amount"])
        await db.add_subscription(name_s, amount)
        total = await db.get_subscriptions_total()
        return {"result": f"Підписку {name_s} ${amount:,.0f}/міс додано. Усього підписок: ${total:,.0f}/міс.", "stop": False}

    if name == "add_lead":
        lead_id = await db.add_lead(
            name=str(args["name"]),
            project_type=str(args.get("project_type") or ""),
            estimated_value=float(args.get("estimated_value") or 0),
            source=str(args.get("source") or ""),
            notes=str(args.get("notes") or ""),
        )
        return {"result": f"Ліда «{args['name']}» додано (id {lead_id}).", "stop": False}

    if name == "update_lead_status":
        query = str(args.get("lead_query") or "").lower()
        status = str(args.get("status"))
        leads = await db.get_leads()
        match = next((l for l in leads if query in l["name"].lower()), None)
        if not match:
            return {"result": f"Ліда «{args.get('lead_query')}» не знайдено серед активних.", "stop": False}
        await db.update_lead(match["id"], status=status)
        return {"result": f"Статус ліда «{match['name']}» → {status}.", "stop": False}

    if name == "update_content_plan":
        await db.set_config("content_plan", str(args.get("text") or ""))
        context.user_data["last_content_plan"] = str(args.get("text") or "")
        return {"result": "Контент-план оновлено.", "stop": False}

    if name == "get_overview":
        ctx = await db.build_context_snapshot()
        tasks = await db.get_tasks(today(), "day")
        done = sum(1 for t in tasks if t["done"])
        meetings_up = await db.get_upcoming_meetings(3)
        overdue = ", ".join(l["name"] for l in ctx.get("overdue_leads", [])) or "немає"
        lines = [
            f"Чистий прибуток: ${ctx['month_net']:,.0f} / ${ctx['goal']:,.0f} ({ctx['pct']:.0f}%)",
            f"Оборот ${ctx['month_income']:,.0f}, витрати ${ctx['month_oneoff_expenses']:,.0f}, підписки ${ctx['subscriptions_total']:,.0f}",
            f"Задачі сьогодні: {done}/{len(tasks)}",
            f"Прострочені follow-up: {overdue}",
            f"Streak: {ctx['streak']} дн.",
        ]
        if meetings_up:
            from handlers.meetings import _fmt_kyiv
            lines.append("Найближчі зустрічі: " + "; ".join(
                f"{m['title']} ({_fmt_kyiv(m['start_utc'])})" for m in meetings_up
            ))
        return {"result": "\n".join(lines), "stop": False}

    # ── confirmation-required actions ──
    if name == "log_income":
        amount = float(args["amount"])
        description = str(args.get("description") or "оплата")
        costs = _norm_costs(args.get("costs"))
        context.user_data["pending_action"] = {
            "type": "income", "amount": amount, "description": description, "costs": costs,
        }
        await _send_action_card(msg, _income_card(amount, description, costs))
        context.user_data["_card_sent"] = True
        return {"result": "Очікую підтвердження користувача.", "stop": True}

    if name == "close_lead":
        query = str(args.get("lead_query") or "").lower()
        amount = float(args["amount"])
        costs = _norm_costs(args.get("costs"))
        leads = await db.get_leads()
        match = next((l for l in leads if query in l["name"].lower()), None)
        if not match:
            return {"result": f"Ліда «{args.get('lead_query')}» не знайдено серед активних.", "stop": False}
        context.user_data["pending_action"] = {
            "type": "close_lead", "lead_id": match["id"], "lead_name": match["name"],
            "amount": amount, "costs": costs,
        }
        card = f"🤝 <b>Закрити угоду?</b>\n\nЛід: <b>{match['name']}</b>\n" + _income_card(amount, match["name"], costs, header=False)
        await _send_action_card(msg, card)
        context.user_data["_card_sent"] = True
        return {"result": "Очікую підтвердження користувача.", "stop": True}

    if name == "create_meeting":
        data = {
            "title": args.get("title"),
            "start": args.get("start"),
            "duration_min": args.get("duration_min"),
            "online": args.get("online"),
            "location": args.get("location"),
            "attendees": args.get("attendees"),
        }
        await meetings.prepare_meeting(msg, context, data)
        context.user_data["_card_sent"] = True
        return {"result": "Очікую підтвердження користувача щодо зустрічі.", "stop": True}

    return {"result": f"Невідомий інструмент: {name}", "stop": False}


def _income_card(amount: float, description: str, costs: list[tuple[str, float]], header: bool = True) -> str:
    lines = []
    if header:
        lines.append("💰 <b>Записати оплату?</b>\n")
    lines.append(f"Сума: <b>${amount:,.0f}</b>")
    lines.append(f"Опис: {description}")
    if costs:
        total = sum(a for _, a in costs)
        lines.append("Витрати: " + ", ".join(f"{c} ${a:,.0f}" for c, a in costs) + f" (разом ${total:,.0f})")
        lines.append(f"Чистими з цієї оплати: <b>${amount - total:,.0f}</b>")
    return "\n".join(lines)


async def _send_action_card(msg, text: str) -> None:
    await msg.reply_text(text, parse_mode="HTML", reply_markup=keyboards.action_confirm_keyboard())


# ── Confirmation callbacks ────────────────────────────────────────────────────

async def action_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = context.user_data.pop("pending_action", None)
    if not action:
        await query.edit_message_text("Дія застаріла — напиши запит ще раз.")
        return

    if action["type"] == "income":
        income_id = await db.add_income(action["amount"], action["description"])
        for cat, amt in action["costs"]:
            await db.add_expense(amt, cat, description="з оплати", income_id=income_id, source="income")
    elif action["type"] == "close_lead":
        await db.update_lead(action["lead_id"], status="closed", actual_value=action["amount"])
        income_id = await db.add_income(action["amount"], action["lead_name"], lead_id=action["lead_id"])
        for cat, amt in action["costs"]:
            await db.add_expense(amt, cat, description="з оплати", income_id=income_id, source="income")

    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    note = "✅ Угоду закрито." if action["type"] == "close_lead" else "✅ Оплату записано."
    await query.message.reply_text(
        f"{note}\n\n💰 Чистий прибуток: {bar}\n<i>{income_breakdown(ctx)}</i>",
        parse_mode="HTML",
    )


async def action_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_action", None)
    await query.edit_message_text("Скасовано.")


# ── Main entry: global free-text handler ──────────────────────────────────────

async def agent_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    context.user_data.pop("pending_action", None)  # drop any stale draft
    context.user_data["_card_sent"] = False

    ctx = await db.build_context_snapshot()
    dialog = _format_dialog(context)
    user_msg = text if not dialog else f"Контекст розмови:\n{dialog}\n\nНове повідомлення: {text}"

    async def executor(name, args):
        return await _execute_tool(name, args, update, context)

    final = await ai_client.run_agent(
        user_msg, ctx, tools=TOOLS, executor=executor,
        bot=context.bot, chat_id=update.effective_chat.id,
    )

    _remember(context, "user", text)
    card_sent = context.user_data.pop("_card_sent", False)
    if card_sent:
        return
    if final and final.strip():
        _remember(context, "assistant", final)
        for part in split_message(final):
            await update.message.reply_text(part)
    else:
        await update.message.reply_text("Готово ✅")
