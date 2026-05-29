import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

import database as db
from config import config
from scheduler import register_jobs
from handlers.checkin import morning_conversation, evening_conversation
from handlers.commands import (
    ask_conversation,
    checkin_history,
    content_list,
    follow_up,
    goal,
    help_cmd,
    income,
    income_add_conversation,
    income_history,
    lead_add_conversation,
    lead_status_callback,
    lead_update_list,
    lead_update_show,
    leads,
    menu,
    menu_callback,
    motivate,
    pipeline,
    review_week,
    start,
    status,
    streak,
)
from handlers.sales import (
    objection,
    outreach_conversation,
    pitch,
    price_conversation,
    proposal_conversation,
)
from handlers.content import (
    brand,
    post_idea_conversation,
    weekly_plan,
)
from handlers.tasks import (
    channels_conversation,
    free_text_handler,
    month_review,
    plan_day_conversation,
    setgoal_conversation,
    task_toggle,
    tasks_cmd,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def restrict_to_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        raise ApplicationHandlerStop

    user_id = update.effective_user.id
    allowed_id = config.allowed_chat_id

    if allowed_id is None:
        stored = await db.get_config("user_telegram_id")
        if stored is None:
            await db.set_config("user_telegram_id", str(user_id))
            logger.info("First run: authorized chat_id=%s", user_id)
            config.allowed_chat_id = user_id
            return
        allowed_id = int(stored)
        config.allowed_chat_id = allowed_id

    if user_id != allowed_id:
        if update.message:
            await update.message.reply_text("Цей бот приватний.")
        raise ApplicationHandlerStop


async def post_init(application: Application) -> None:
    await db.init_db()
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота"),
        BotCommand("menu", "Головне меню"),
        BotCommand("status", "Поточний статус"),
        BotCommand("morning", "Ранковий check-in"),
        BotCommand("evening", "Вечірній review"),
        BotCommand("plan_day", "Скласти план задач на день"),
        BotCommand("tasks", "Задачі на сьогодні"),
        BotCommand("setgoal", "Поставити ціль на місяць"),
        BotCommand("month_review", "Аналіз місяця"),
        BotCommand("channels", "Підбір каналів залучення"),
        BotCommand("income", "Дохід місяця"),
        BotCommand("income_add", "Додати оплату"),
        BotCommand("income_history", "Історія доходів"),
        BotCommand("goal", "Переглянути/змінити ціль"),
        BotCommand("leads", "Список лідів"),
        BotCommand("lead_add", "Додати ліда"),
        BotCommand("lead_update", "Оновити статус ліда"),
        BotCommand("pipeline", "Воронка продажів"),
        BotCommand("follow_up", "Прострочені follow-up"),
        BotCommand("proposal", "Генерація пропозиції"),
        BotCommand("price", "Калькулятор ціни"),
        BotCommand("outreach", "Холодне повідомлення"),
        BotCommand("objection", "Відпрацювати заперечення"),
        BotCommand("pitch", "Elevator pitch"),
        BotCommand("post_idea", "Ідея для посту"),
        BotCommand("weekly_plan", "Контент-план на тиждень"),
        BotCommand("brand", "Порада по бренду"),
        BotCommand("content_list", "Збережені ідеї"),
        BotCommand("checkin_history", "Останні check-in"),
        BotCommand("streak", "Серія check-in"),
        BotCommand("ask", "Запитати ментора"),
        BotCommand("review_week", "Тижневий ретроспектив"),
        BotCommand("motivate", "Мотивація"),
        BotCommand("help", "Список команд"),
    ])
    logger.info("Bot initialized")


def main() -> None:
    app = (
        Application.builder()
        .token(config.telegram_token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(TypeHandler(Update, restrict_to_owner), group=-1)

    for conv in [
        morning_conversation(),
        evening_conversation(),
        income_add_conversation(),
        lead_add_conversation(),
        proposal_conversation(),
        price_conversation(),
        outreach_conversation(),
        ask_conversation(),
        post_idea_conversation(),
        plan_day_conversation(),
        setgoal_conversation(),
        channels_conversation(),
    ]:
        app.add_handler(conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("income", income))
    app.add_handler(CommandHandler("income_history", income_history))
    app.add_handler(CommandHandler("goal", goal))
    app.add_handler(CommandHandler("leads", leads))
    app.add_handler(CommandHandler("lead_update", lead_update_list))
    app.add_handler(CommandHandler("pipeline", pipeline))
    app.add_handler(CommandHandler("follow_up", follow_up))
    app.add_handler(CommandHandler("streak", streak))
    app.add_handler(CommandHandler("checkin_history", checkin_history))
    app.add_handler(CommandHandler("objection", objection))
    app.add_handler(CommandHandler("pitch", pitch))
    app.add_handler(CommandHandler("review_week", review_week))
    app.add_handler(CommandHandler("motivate", motivate))
    app.add_handler(CommandHandler("content_list", content_list))
    app.add_handler(CommandHandler("weekly_plan", weekly_plan))
    app.add_handler(CommandHandler("brand", brand))
    app.add_handler(CommandHandler("tasks", tasks_cmd))
    app.add_handler(CommandHandler("month_review", month_review))

    # Dynamic commands like /lead_update_5 arrive as messages. CommandHandler
    # only matches static command names, so we match the pattern with a regex
    # MessageHandler — this also populates context.matches used by the handler.
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^/lead_update_(\d+)$"),
            lead_update_show,
        )
    )

    app.add_handler(CallbackQueryHandler(lead_status_callback, pattern=r"^lstatus_"))
    app.add_handler(CallbackQueryHandler(task_toggle, pattern=r"^task_\d+$"))
    app.add_handler(CallbackQueryHandler(tasks_cmd, pattern=r"^cmd_tasks$"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(cmd_|cancel)"))

    # Lowest-priority catch-all: free-text not consumed by a command or an
    # active conversation is treated as a plan edit (or a question to the
    # mentor when no tasks exist for today). Must be registered last so all
    # ConversationHandlers and CommandHandlers get first claim on the message.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, free_text_handler)
    )

    register_jobs(app)

    logger.info("Starting bot (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
