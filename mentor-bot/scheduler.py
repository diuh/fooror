import pytz
from datetime import time

from telegram.ext import Application

KYIV_TZ = pytz.timezone("Europe/Kyiv")


def register_jobs(app: Application) -> None:
    from handlers.checkin import morning_job, evening_job

    app.job_queue.run_daily(
        callback=morning_job,
        time=time(10, 0, tzinfo=KYIV_TZ),
        name="morning_checkin",
    )
    app.job_queue.run_daily(
        callback=evening_job,
        time=time(20, 0, tzinfo=KYIV_TZ),
        name="evening_checkin",
    )
    app.job_queue.run_daily(
        callback=weekly_content_reminder,
        time=time(9, 0, tzinfo=KYIV_TZ),
        days=(0,),
        name="weekly_content",
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
