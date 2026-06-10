"""Natural-language agent: the bot's primary interface.

Free text goes through Claude with a set of tools that map to the bot's
actions (tasks, finances, leads, meetings). Safe/reversible actions run
immediately; money/external actions (income, meetings, closing a lead) are
staged as a pending confirmation with buttons before they take effect.
"""

import logging
import pytz
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

import ai_client
import database as db
import gcal_client
import keyboards
from config import config
from formatters import income_bar, income_breakdown, md_to_html, split_message
from handlers.tasks import format_tasks_text, month_key, today, week_key
from handlers import meetings

logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Kyiv")
UTC = pytz.utc

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
        "name": "toggle_task_done",
        "description": "Відмітити задачу як виконану або відкрити за частковим збігом назви.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title_query": {"type": "string", "description": "частина назви задачі"},
                "horizon": {"type": "string", "enum": ["day", "week", "month"], "description": "горизонт, за замовчуванням day"},
            },
            "required": ["title_query"],
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
        "name": "update_brand_profile",
        "description": "Оновити поля бренд-профілю (ніша, ідеальний клієнт, POV, голос, рубрики). Передавай лише ті поля, які треба змінити.",
        "input_schema": {
            "type": "object",
            "properties": {
                "niche": {"type": "string"},
                "ideal_client": {"type": "string"},
                "pov": {"type": "string", "description": "сильна думка/контрар'ян"},
                "voice": {"type": "string", "description": "голос/тон"},
                "pillars": {"type": "array", "items": {"type": "string"}, "description": "контент-рубрики"},
            },
        },
    },
    {
        "name": "get_overview",
        "description": "Отримати поточний дашборд: чистий прибуток, задачі, зустрічі, прострочені ліди.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_leads",
        "description": "Отримати список лідів з CRM. Використовуй, коли питають про ліди, воронку, follow-up.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Фільтр: new/negotiation/proposal/closed/rejected. Без фільтру — всі активні."},
            },
        },
    },
    {
        "name": "get_finances",
        "description": "Отримати дохід, витрати та чистий прибуток за місяць.",
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "YYYY-MM, за замовчуванням поточний місяць"},
            },
        },
    },
    {
        "name": "list_meetings",
        "description": "Показати найближчі заплановані зустрічі.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Кількість зустрічей, за замовчуванням 5"},
            },
        },
    },
    {
        "name": "list_tasks",
        "description": "Отримати список задач для вказаного горизонту планування.",
        "input_schema": {
            "type": "object",
            "properties": {
                "horizon": {"type": "string", "enum": ["day", "week", "month"]},
            },
            "required": ["horizon"],
        },
    },
    {
        "name": "cancel_meeting",
        "description": "Скасувати заплановану зустріч за частковим збігом назви.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title_query": {"type": "string", "description": "частина назви зустрічі"},
            },
            "required": ["title_query"],
        },
    },
    {
        "name": "reschedule_meeting",
        "description": "Перенести зустріч на інший час.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title_query": {"type": "string", "description": "частина назви зустрічі"},
                "new_start": {"type": "string", "description": "Новий місцевий час Києва, формат YYYY-MM-DDTHH:MM"},
            },
            "required": ["title_query", "new_start"],
        },
    },
    {
        "name": "check_calendar",
        "description": "Прочитати події з Google Calendar за дату або діапазон. Використовуй, щоб перевірити наявність вільного часу або відповісти 'що є в четвер?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD або діапазон YYYY-MM-DD/YYYY-MM-DD"},
            },
            "required": ["date"],
        },
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


# ── Dialog memory (proper message history for Anthropic API) ──────────────────

_MAX_HISTORY_TURNS = 6  # 6 user+assistant pairs = 12 messages


def _remember(context: ContextTypes.DEFAULT_TYPE, role: str, text: str) -> None:
    dialog = context.user_data.setdefault("dialog_v2", [])
    dialog.append({"role": role, "content": text})
    if len(dialog) > _MAX_HISTORY_TURNS * 2:
        context.user_data["dialog_v2"] = dialog[-(_MAX_HISTORY_TURNS * 2):]


def _get_history(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    return list(context.user_data.get("dialog_v2", []))


def _norm_costs(raw) -> list[tuple[str, float]]:
    out = []
    for c in raw or []:
        try:
            out.append((str(c.get("category") or "інше"), float(c.get("amount") or 0)))
        except (ValueError, TypeError, AttributeError):
            continue
    return [(cat, amt) for cat, amt in out if amt > 0]


# ── Read-tool formatters ───────────────────────────────────────────────────────

def _fmt_leads(rows: list[dict]) -> str:
    if not rows:
        return "Активних лідів немає."
    lines = []
    for r in rows:
        val = f" / ~${r['estimated_value']:,.0f}" if r.get("estimated_value") else ""
        action = f" → {r['next_action']}" if r.get("next_action") else ""
        lines.append(f"• {r['name']} [{r['status']}]{val}{action}")
    return "\n".join(lines)


def _fmt_meetings_list(rows: list[dict]) -> str:
    if not rows:
        return "Найближчих зустрічей немає."
    lines = []
    for m in rows:
        from handlers.meetings import _fmt_kyiv
        when = _fmt_kyiv(m["start_utc"], m["end_utc"])
        icon = "🎥" if m["is_online"] else "📍"
        lines.append(f"{icon} {m['title']} — {when}")
    return "\n".join(lines)


def _fmt_tasks_list(rows: list[dict]) -> str:
    if not rows:
        return "Задач немає."
    lines = []
    for t in rows:
        mark = "✅" if t["done"] else "⬜"
        lines.append(f"{mark} {t['title']}")
    return "\n".join(lines)


def _fmt_event_time(start_str: str) -> str:
    if not start_str or "T" not in start_str:
        return start_str or "весь день"
    try:
        dt = datetime.fromisoformat(start_str)
        if dt.tzinfo is None:
            dt = UTC.localize(dt)
        return dt.astimezone(KYIV_TZ).strftime("%H:%M")
    except (ValueError, AttributeError):
        return start_str


# ── Task replacement safety check ─────────────────────────────────────────────

async def _safe_replace_tasks(
    name: str, pkey: str, horizon: str, items: list[str],
    msg, context: ContextTypes.DEFAULT_TYPE
) -> dict:
    """Replace tasks, but ask for confirmation if it would delete 3+ pending tasks."""
    existing = await db.get_pending_tasks(pkey, horizon)
    new_lower = {t.lower() for t in items}
    to_delete = [r for r in existing if r["title"].strip().lower() not in new_lower]

    if len(to_delete) >= 3:
        context.user_data["pending_action"] = {
            "type": "replace_tasks",
            "key": pkey,
            "horizon": horizon,
            "titles": items,
            "deleting": [r["title"] for r in to_delete],
        }
        lines = [f"⚠️ Буде видалено {len(to_delete)} незавершених задач:"]
        lines += [f"  — {r['title']}" for r in to_delete[:6]]
        if len(to_delete) > 6:
            lines.append(f"  … ще {len(to_delete) - 6}")
        lines.append("Підтвердити заміну?")
        await msg.reply_text("\n".join(lines), reply_markup=keyboards.action_confirm_keyboard())
        context.user_data["_card_sent"] = True
        return {"result": "Очікую підтвердження заміни задач.", "stop": True}

    await db.replace_tasks(pkey, items, horizon=horizon)
    saved = await db.get_tasks(pkey, horizon)
    if saved:
        await msg.reply_text(
            format_tasks_text(saved, horizon), parse_mode="HTML",
            reply_markup=keyboards.tasks_keyboard(saved, horizon),
        )
        context.user_data["_card_sent"] = True
    return {"result": f"Оновлено ({len(items)} пунктів).", "stop": False}


# ── Tool execution ────────────────────────────────────────────────────────────

async def _execute_tool(name: str, args: dict, update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    msg = update.message
    try:
        return await _execute_tool_inner(name, args, msg, update, context)
    except Exception as e:
        logger.exception("Tool %s failed with args %s", name, args)
        return {"result": f"Помилка інструменту «{name}»: {e}", "stop": False}


async def _execute_tool_inner(
    name: str, args: dict, msg, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> dict:

    # ── task planning ──
    if name in ("set_today_tasks", "set_week_priorities", "set_month_goals"):
        horizon, pkey, raw_items = {
            "set_today_tasks":    ("day",   today(),     args.get("tasks", [])),
            "set_week_priorities":("week",  week_key(),  args.get("items", [])),
            "set_month_goals":    ("month", month_key(), args.get("items", [])),
        }[name]
        items = [str(i).strip() for i in raw_items if str(i).strip()]
        return await _safe_replace_tasks(name, pkey, horizon, items, msg, context)

    if name == "toggle_task_done":
        horizon = args.get("horizon") or "day"
        pkey = {"day": today(), "week": week_key(), "month": month_key()}[horizon]
        rows = await db.get_tasks(pkey, horizon)
        query_lower = args["title_query"].lower()
        match = next((r for r in rows if query_lower in r["title"].lower()), None)
        if not match:
            return {"result": f"Задачу «{args['title_query']}» не знайшов серед задач на {horizon}.", "stop": False}
        new_state = await db.toggle_task(match["id"])
        label = "✅ Виконано" if new_state else "⬜ Відкрито"
        return {"result": f"{label}: «{match['title']}»", "stop": False}

    # ── finances ──
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

    # ── leads ──
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
        lead_list = await db.get_leads()
        match = next((l for l in lead_list if query in l["name"].lower()), None)
        if not match:
            return {"result": f"Ліда «{args.get('lead_query')}» не знайдено серед активних.", "stop": False}
        await db.update_lead(match["id"], status=status)
        return {"result": f"Статус ліда «{match['name']}» → {status}.", "stop": False}

    # ── content ──
    if name == "update_content_plan":
        await db.set_config("content_plan", str(args.get("text") or ""))
        context.user_data["last_content_plan"] = str(args.get("text") or "")
        return {"result": "Контент-план оновлено.", "stop": False}

    if name == "update_brand_profile":
        profile = await db.get_brand_profile() or {}
        for field in ("niche", "ideal_client", "pov", "voice"):
            if args.get(field):
                profile[field] = str(args[field]).strip()
        if args.get("pillars"):
            profile["pillars"] = [str(p).strip() for p in args["pillars"] if str(p).strip()]
        await db.set_brand_profile(profile)
        changed = ", ".join(k for k in ("niche", "ideal_client", "pov", "voice", "pillars") if args.get(k))
        return {"result": f"Бренд-профіль оновлено ({changed}).", "stop": False}

    # ── read / overview ──
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

    if name == "list_leads":
        rows = await db.get_leads(status=args.get("status") or None)
        return {"result": _fmt_leads(rows), "stop": False}

    if name == "get_finances":
        ctx_snap = await db.build_context_snapshot()
        month = args.get("month") or ctx_snap["month"]
        income = await db.get_month_income(month)
        expenses = await db.get_month_expenses(month)
        subs = await db.get_subscriptions_total() if month == ctx_snap["month"] else 0.0
        net = income - expenses - subs
        return {"result": (
            f"Місяць {month}: дохід ${income:,.0f}, витрати ${expenses:,.0f}, "
            f"підписки ~${subs:,.0f}/міс, чистий ${net:,.0f}."
        ), "stop": False}

    if name == "list_meetings":
        limit = int(args.get("limit") or 5)
        rows = await db.get_upcoming_meetings(limit)
        return {"result": _fmt_meetings_list(rows), "stop": False}

    if name == "list_tasks":
        horizon = args["horizon"]
        pkey = {"day": today(), "week": week_key(), "month": month_key()}[horizon]
        rows = await db.get_tasks(pkey, horizon)
        return {"result": _fmt_tasks_list(rows), "stop": False}

    # ── meeting management ──
    if name == "cancel_meeting":
        query = str(args.get("title_query") or "").lower()
        rows = await db.get_upcoming_meetings(20)
        match = next((m for m in rows if query in m["title"].lower()), None)
        if not match:
            return {"result": f"Зустріч «{args.get('title_query')}» не знайдено.", "stop": False}
        row = await db.cancel_meeting(match["id"])
        if row and row.get("gcal_event_id"):
            try:
                await gcal_client.delete_event(row["gcal_event_id"])
            except Exception:
                logger.exception("Failed to delete gcal event for cancelled meeting")
        return {"result": f"Зустріч «{match['title']}» скасовано.", "stop": False}

    if name == "reschedule_meeting":
        if not config.google_enabled:
            return {"result": "Google Calendar не підключено — не можу оновити час у Calendar.", "stop": False}
        query = str(args.get("title_query") or "").lower()
        rows = await db.get_upcoming_meetings(20)
        match = next((m for m in rows if query in m["title"].lower()), None)
        if not match:
            return {"result": f"Зустріч «{args.get('title_query')}» не знайдено.", "stop": False}
        try:
            naive_new = datetime.strptime(args["new_start"], "%Y-%m-%dT%H:%M")
        except (ValueError, KeyError):
            return {"result": "Невірний формат часу. Використовуй YYYY-MM-DDTHH:MM.", "stop": False}
        old_start = datetime.fromisoformat(match["start_utc"])
        old_end = datetime.fromisoformat(match["end_utc"])
        duration = old_end - old_start
        new_start_utc = KYIV_TZ.localize(naive_new).astimezone(UTC).replace(tzinfo=None)
        new_end_utc = new_start_utc + duration
        new_start_local = naive_new.strftime("%Y-%m-%dT%H:%M:%S")
        new_end_local = (naive_new + duration).strftime("%Y-%m-%dT%H:%M:%S")
        await db.update_meeting(
            match["id"],
            start_utc=new_start_utc.isoformat(),
            end_utc=new_end_utc.isoformat(),
            reminded_1h=0,
            reminded_5m=0,
        )
        if match.get("gcal_event_id"):
            try:
                await gcal_client.update_event(match["gcal_event_id"], new_start_local, new_end_local, "Europe/Kyiv")
            except Exception:
                logger.exception("Failed to update gcal event for rescheduled meeting")
        return {"result": f"Зустріч «{match['title']}» перенесено на {naive_new.strftime('%d.%m %H:%M')}.", "stop": False}

    if name == "check_calendar":
        if not config.google_enabled:
            return {"result": "Google Calendar не підключено.", "stop": False}
        date_str = str(args.get("date") or "")
        if "/" in date_str:
            start_d, end_d = date_str.split("/", 1)
        else:
            start_d = end_d = date_str
        try:
            start_utc = KYIV_TZ.localize(datetime.strptime(start_d.strip(), "%Y-%m-%d")).astimezone(UTC)
            end_utc = KYIV_TZ.localize(
                datetime.strptime(end_d.strip(), "%Y-%m-%d") + timedelta(days=1)
            ).astimezone(UTC)
        except ValueError:
            return {"result": "Невірний формат дати. Використовуй YYYY-MM-DD.", "stop": False}
        time_min = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        events = await gcal_client.list_events(time_min, time_max)
        if not events:
            return {"result": f"На {date_str} у Google Calendar немає подій.", "stop": False}
        lines = [f"📅 Календар на {date_str}:"]
        for ev in events:
            start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
            lines.append(f"• {ev.get('summary', '?')} — {_fmt_event_time(start)}")
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
        lead_list = await db.get_leads()
        match = next((l for l in lead_list if query in l["name"].lower()), None)
        if not match:
            return {"result": f"Ліда «{args.get('lead_query')}» не знайдено серед активних.", "stop": False}
        context.user_data["pending_action"] = {
            "type": "close_lead", "lead_id": match["id"], "lead_name": match["name"],
            "lead_prev_status": match["status"],
            "amount": amount, "costs": costs,
        }
        card = (
            f"🤝 <b>Закрити угоду?</b>\n\nЛід: <b>{match['name']}</b>\n"
            + _income_card(amount, match["name"], costs, header=False)
        )
        await _send_action_card(msg, card)
        context.user_data["_card_sent"] = True
        return {"result": "Очікую підтвердження користувача.", "stop": True}

    if name == "create_meeting":
        if not config.google_enabled:
            return {
                "result": (
                    "Google Calendar не підключено. Додай GOOGLE_CLIENT_ID / "
                    "GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN у змінні середовища."
                ),
                "stop": False,
            }
        data = {
            "title": args.get("title"),
            "start": args.get("start"),
            "duration_min": args.get("duration_min"),
            "online": args.get("online"),
            "location": args.get("location"),
            "attendees": args.get("attendees"),
        }
        # Quick conflict check (best-effort, non-blocking)
        conflict_note = ""
        try:
            naive_start = datetime.strptime(data["start"], "%Y-%m-%dT%H:%M")
            duration = timedelta(minutes=int(data.get("duration_min") or 30))
            s_utc = KYIV_TZ.localize(naive_start).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            e_utc = KYIV_TZ.localize(naive_start + duration).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            conflicts = await gcal_client.list_events(s_utc, e_utc)
            if conflicts:
                names = ", ".join(ev.get("summary", "?") for ev in conflicts[:3])
                conflict_note = f"⚠️ Перетин з: {names}"
        except Exception:
            pass
        if conflict_note:
            data["_conflict_note"] = conflict_note
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

    if action["type"] == "replace_tasks":
        await db.replace_tasks(action["key"], action["titles"], action["horizon"])
        saved = await db.get_tasks(action["key"], action["horizon"])
        await query.edit_message_text(f"✅ Задачі оновлено ({len(action['titles'])} шт.)")
        if saved:
            await query.message.reply_text(
                format_tasks_text(saved, action["horizon"]), parse_mode="HTML",
                reply_markup=keyboards.tasks_keyboard(saved, action["horizon"]),
            )
        return

    expense_ids = []
    if action["type"] == "income":
        income_id = await db.add_income(action["amount"], action["description"])
        for cat, amt in action["costs"]:
            eid = await db.add_expense(amt, cat, description="з оплати", income_id=income_id, source="income")
            expense_ids.append(eid)
        context.user_data["last_undo"] = {
            "type": "income",
            "income_id": income_id,
            "expense_ids": expense_ids,
        }

    elif action["type"] == "close_lead":
        prev_status = action.get("lead_prev_status", "negotiation")
        await db.update_lead(action["lead_id"], status="closed", actual_value=action["amount"])
        income_id = await db.add_income(action["amount"], action["lead_name"], lead_id=action["lead_id"])
        for cat, amt in action["costs"]:
            eid = await db.add_expense(amt, cat, description="з оплати", income_id=income_id, source="income")
            expense_ids.append(eid)
        context.user_data["last_undo"] = {
            "type": "close_lead",
            "lead_id": action["lead_id"],
            "prev_status": prev_status,
            "income_id": income_id,
            "expense_ids": expense_ids,
        }

    ctx = await db.build_context_snapshot()
    bar = income_bar(ctx["month_net"], ctx["goal"])
    note = "✅ Угоду закрито." if action["type"] == "close_lead" else "✅ Оплату записано."
    await query.message.reply_text(
        f"{note}\n\n💰 Чистий прибуток: {bar}\n<i>{income_breakdown(ctx)}</i>",
        parse_mode="HTML",
        reply_markup=keyboards.undo_keyboard(),
    )


async def action_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_action", None)
    await query.edit_message_text("Скасовано.")


async def undo_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    undo = context.user_data.pop("last_undo", None)
    if not undo:
        await query.edit_message_text("Нічого скасовувати.")
        return

    if undo["type"] == "income":
        for eid in undo.get("expense_ids", []):
            await db.delete_expense(eid)
        await db.delete_income(undo["income_id"])
        await query.edit_message_text("↩️ Оплату скасовано.")

    elif undo["type"] == "close_lead":
        for eid in undo.get("expense_ids", []):
            await db.delete_expense(eid)
        await db.delete_income(undo["income_id"])
        await db.update_lead(
            undo["lead_id"],
            status=undo["prev_status"],
            actual_value=None,
            closed_at=None,
        )
        await query.edit_message_text("↩️ Закриття угоди скасовано, ліда відновлено.")


# ── Shared core: handles both text and voice ──────────────────────────────────

async def _handle_text(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_action", None)
    context.user_data["_card_sent"] = False

    ctx = await db.build_context_snapshot()
    history = _get_history(context)

    async def executor(name, args):
        return await _execute_tool(name, args, update, context)

    final = await ai_client.run_agent(
        text, ctx, tools=TOOLS, executor=executor,
        history=history,
        bot=context.bot, chat_id=update.effective_chat.id,
    )

    card_sent = context.user_data.pop("_card_sent", False)
    if card_sent:
        return

    _remember(context, "user", text)
    if final and final.strip():
        _remember(context, "assistant", final)
        for part in split_message(final):
            await update.message.reply_text(md_to_html(part), parse_mode="HTML")
    else:
        await update.message.reply_text("Готово ✅")


# ── Main entry: global free-text handler ──────────────────────────────────────

async def agent_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_text(update.message.text.strip(), update, context)
