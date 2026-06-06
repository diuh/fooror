"""Meeting scheduling via free text → Google Calendar, plus Telegram reminders.

Flow: the AI agent calls the create_meeting tool, which routes to
prepare_meeting and shows a confirmation card. On confirm we create the Google
Calendar event (Meet link + email invites for online) and store it. A repeating
job sends Telegram reminders (online: 5 min before; offline: 1 h and 5 min before).
"""

import json
import logging
from datetime import datetime, timedelta

import pytz
from telegram import Update
from telegram.ext import ContextTypes

import database as db
import gcal_client
import keyboards
from config import config

logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Kyiv")
UTC = pytz.utc
DEFAULT_DURATION_MIN = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_kyiv(start_utc_naive: str, end_utc_naive: str | None = None) -> str:
    """Render a stored naive-UTC ISO range as a friendly Kyiv-time string."""
    start = UTC.localize(datetime.fromisoformat(start_utc_naive)).astimezone(KYIV_TZ)
    out = start.strftime("%d.%m.%Y %H:%M")
    if end_utc_naive:
        end = UTC.localize(datetime.fromisoformat(end_utc_naive)).astimezone(KYIV_TZ)
        out += end.strftime("–%H:%M")
    return out


def _parse_meeting_json(answer: str) -> dict | None:
    block = answer.split("[ЗУСТРІЧ]", 1)[1]
    lo, hi = block.find("{"), block.rfind("}")
    if lo == -1 or hi == -1 or hi < lo:
        return None
    try:
        return json.loads(block[lo : hi + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _valid_emails(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [e.strip() for e in raw if isinstance(e, str) and "@" in e and "." in e]


# ── Intent → confirmation card ────────────────────────────────────────────────

async def handle_meeting_intent(
    update: Update, context: ContextTypes.DEFAULT_TYPE, answer: str
) -> None:
    data = _parse_meeting_json(answer)
    if not data or not data.get("start"):
        await update.message.reply_text(
            "Не зрозумів деталі зустрічі. Напиши коли і з ким, наприклад:\n"
            "«зустріч з john@acme.com завтра о 15:00 онлайн на годину»"
        )
        return
    await prepare_meeting(update.message, context, data)


async def prepare_meeting(message, context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    """Validate a structured meeting dict, stash it as a pending confirmation
    and show the confirmation card. Reused by both the agent tool and the
    legacy text-intent path. `message` is the Telegram Message to reply to."""
    if not config.google_enabled:
        await message.reply_text(
            "📅 Google Calendar ще не підключено. Щоб планувати зустрічі, додай "
            "змінні GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN "
            "(запусти gcal_auth.py локально)."
        )
        return

    try:
        naive_start = datetime.strptime(data["start"], "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError, KeyError):
        await message.reply_text(
            "Не вдалось розпізнати час. Уточни дату й час, наприклад «завтра о 15:00»."
        )
        return

    duration = int(data.get("duration_min") or DEFAULT_DURATION_MIN)
    naive_end = naive_start + timedelta(minutes=duration)
    is_online = bool(data.get("online"))
    location = (data.get("location") or "").strip()
    attendees = _valid_emails(data.get("attendees"))
    title = (data.get("title") or "Зустріч").strip()

    # Local (Kyiv) ISO for the Calendar API; naive-UTC ISO for our DB.
    start_local_iso = naive_start.strftime("%Y-%m-%dT%H:%M:%S")
    end_local_iso = naive_end.strftime("%Y-%m-%dT%H:%M:%S")
    start_utc = KYIV_TZ.localize(naive_start).astimezone(UTC).replace(tzinfo=None).isoformat()
    end_utc = KYIV_TZ.localize(naive_end).astimezone(UTC).replace(tzinfo=None).isoformat()

    context.user_data["pending_meeting"] = {
        "title": title,
        "start_local_iso": start_local_iso,
        "end_local_iso": end_local_iso,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "is_online": is_online,
        "location": location,
        "attendees": attendees,
    }

    when = _fmt_kyiv(start_utc, end_utc)
    kind = "🎥 Онлайн (Google Meet)" if is_online else "📍 Офлайн"
    lines = [
        "📅 <b>Запланувати зустріч?</b>\n",
        f"<b>{title}</b>",
        f"🕒 {when}",
        kind,
    ]
    if not is_online and location:
        lines.append(f"Адреса: {location}")
    if attendees:
        lines.append(f"👥 Учасники: {', '.join(attendees)}")
    reminder = "нагадаю за 5 хв" if is_online else "нагадаю за годину і за 5 хв"
    lines.append(f"\n⏰ {reminder}.")

    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboards.meeting_confirm_keyboard(),
    )


# ── Confirm / cancel ──────────────────────────────────────────────────────────

async def meeting_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    pending = context.user_data.pop("pending_meeting", None)
    if not pending:
        await query.edit_message_text("Зустріч застаріла — напиши запит ще раз.")
        return

    await query.edit_message_text("⏳ Створюю зустріч у Google Calendar…")
    try:
        result = await gcal_client.create_event(
            title=pending["title"],
            start_iso=pending["start_local_iso"],
            end_iso=pending["end_local_iso"],
            tz="Europe/Kyiv",
            is_online=pending["is_online"],
            location=pending["location"],
            attendees=pending["attendees"],
        )
    except Exception as e:  # google API / network errors
        logger.exception("Calendar event creation failed")
        await query.message.reply_text(
            f"❌ Не вдалось створити зустріч: {e}\nСпробуй ще раз пізніше."
        )
        return

    await db.add_meeting(
        title=pending["title"],
        start_utc=pending["start_utc"],
        end_utc=pending["end_utc"],
        is_online=pending["is_online"],
        location=pending["location"],
        meet_link=result.get("meet_link", ""),
        attendees=",".join(pending["attendees"]),
        html_link=result.get("html_link", ""),
        gcal_event_id=result.get("event_id", ""),
    )

    when = _fmt_kyiv(pending["start_utc"], pending["end_utc"])
    lines = [f"✅ <b>Зустріч створено</b>\n", f"<b>{pending['title']}</b>", f"🕒 {when}"]
    if pending["is_online"] and result.get("meet_link"):
        lines.append(f"🎥 {result['meet_link']}")
    elif not pending["is_online"] and pending["location"]:
        lines.append(f"📍 {pending['location']}")
    if pending["attendees"]:
        lines.append(f"👥 Запрошення надіслано: {', '.join(pending['attendees'])}")
    if result.get("html_link"):
        lines.append(f"\n🔗 {result['html_link']}")
    await query.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


async def meeting_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_meeting", None)
    await query.edit_message_text("Скасовано. Зустріч не створено.")


# ── /meetings list + delete ───────────────────────────────────────────────────

async def meetings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    meetings = await db.get_upcoming_meetings()
    if not meetings:
        await target.reply_text(
            "📅 Найближчих зустрічей немає.\n\n"
            "Напиши текстом, щоб запланувати — наприклад:\n"
            "«зустріч з john@acme.com завтра о 15:00 онлайн»"
        )
        return
    lines = ["📅 <b>Найближчі зустрічі</b>\n"]
    for m in meetings:
        when = _fmt_kyiv(m["start_utc"], m["end_utc"])
        icon = "🎥" if m["is_online"] else "📍"
        lines.append(f"{icon} <b>{m['title']}</b>\n   {when}")
    await target.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboards.meetings_keyboard(meetings),
    )


async def meeting_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meeting_id = int(query.data.split("_")[1])
    row = await db.cancel_meeting(meeting_id)
    if not row:
        await query.answer("Вже видалено")
        return
    await query.answer("🗑 Скасовано")
    if row.get("gcal_event_id"):
        try:
            await gcal_client.delete_event(row["gcal_event_id"])
        except Exception:
            logger.exception("Calendar event deletion failed")
    meetings = await db.get_upcoming_meetings()
    if not meetings:
        try:
            await query.edit_message_text("📅 Найближчих зустрічей немає.")
        except Exception:
            pass
        return
    lines = ["📅 <b>Найближчі зустрічі</b>\n"]
    for m in meetings:
        when = _fmt_kyiv(m["start_utc"], m["end_utc"])
        icon = "🎥" if m["is_online"] else "📍"
        lines.append(f"{icon} <b>{m['title']}</b>\n   {when}")
    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=keyboards.meetings_keyboard(meetings),
        )
    except Exception:
        pass


# ── Reminder job (run_repeating every 60s) ────────────────────────────────────

async def meeting_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    now = datetime.utcnow()
    for m in await db.get_meetings_for_reminder():
        start = datetime.fromisoformat(m["start_utc"])
        minutes = (start - now).total_seconds() / 60
        when = _fmt_kyiv(m["start_utc"], m["end_utc"])

        # Offline: 1-hour heads-up
        if not m["reminded_1h"] and not m["is_online"]:
            if minutes <= 0:
                await db.mark_reminded(m["id"], "1h")  # missed window, don't spam
            elif minutes <= 60:
                text = f"🔔 <b>Через годину зустріч</b>\n\n<b>{m['title']}</b>\n🕒 {when}"
                if m.get("location"):
                    text += f"\n📍 {m['location']}"
                await context.bot.send_message(int(chat_id), text, parse_mode="HTML")
                await db.mark_reminded(m["id"], "1h")

        # Any: 5-minute heads-up
        if not m["reminded_5m"]:
            if minutes <= 0:
                await db.mark_reminded(m["id"], "5m")
            elif minutes <= 5:
                text = f"🔔 <b>Через 5 хвилин зустріч</b>\n\n<b>{m['title']}</b>\n🕒 {when}"
                if m["is_online"] and m.get("meet_link"):
                    text += f"\n🎥 {m['meet_link']}"
                elif not m["is_online"] and m.get("location"):
                    text += f"\n📍 {m['location']}"
                await context.bot.send_message(
                    int(chat_id), text, parse_mode="HTML", disable_web_page_preview=True
                )
                await db.mark_reminded(m["id"], "5m")
