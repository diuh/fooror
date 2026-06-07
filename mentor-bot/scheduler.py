import pytz
from datetime import time

from telegram.ext import Application

KYIV_TZ = pytz.timezone("Europe/Kyiv")


def register_jobs(app: Application) -> None:
    from handlers.checkin import morning_job, evening_job, followup_reminder_job
    from handlers.tasks import midday_reminder_job, month_end_job, month_start_job
    from handlers.meetings import meeting_reminder_job

    app.job_queue.run_repeating(
        callback=meeting_reminder_job,
        interval=60,
        first=30,
        name="meeting_reminders",
    )
    app.job_queue.run_daily(
        callback=month_start_job,
        time=time(9, 0, tzinfo=KYIV_TZ),
        name="month_start",
    )
    app.job_queue.run_daily(
        callback=morning_job,
        time=time(10, 0, tzinfo=KYIV_TZ),
        name="morning_checkin",
    )
    app.job_queue.run_daily(
        callback=followup_reminder_job,
        time=time(9, 30, tzinfo=KYIV_TZ),
        name="followup_reminder",
    )
    app.job_queue.run_daily(
        callback=midday_reminder_job,
        time=time(15, 0, tzinfo=KYIV_TZ),
        name="midday_reminder",
    )
    app.job_queue.run_daily(
        callback=evening_job,
        time=time(20, 0, tzinfo=KYIV_TZ),
        name="evening_checkin",
    )
    app.job_queue.run_daily(
        callback=month_end_job,
        time=time(19, 0, tzinfo=KYIV_TZ),
        name="month_end_review",
    )
    app.job_queue.run_daily(
        callback=weekly_content_reminder,
        time=time(9, 0, tzinfo=KYIV_TZ),
        days=(0,),
        name="weekly_content",
    )
    app.job_queue.run_daily(
        callback=weekly_review_nudge,
        time=time(19, 0, tzinfo=KYIV_TZ),
        days=(6,),
        name="weekly_review_nudge",
    )


async def weekly_content_reminder(context) -> None:
    import database as db
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    await context.bot.send_message(
        chat_id=int(chat_id),
        text="📅 Початок тижня! Час скласти контент-план.\n\nВідправ /weekly_plan",
    )


async def weekly_review_nudge(context) -> None:
    import database as db
    chat_id = await db.get_config("user_telegram_id")
    if not chat_id:
        return
    await context.bot.send_message(
        chat_id=int(chat_id),
        text="📊 Кінець тижня — час підвести підсумки.\n\n/review_week",
    )
