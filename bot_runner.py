import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    CallbackContext,
)

import config
from auth.google_auth import GoogleAuthenticator
from services.google_sheets import GoogleSheetsService
from services.telegram_api import TelegramService
from data_processing.expense_data import ExpenseDataManager
from analytics.dashboard_metrics import DashboardMetricsCalculator
from ai.gemini_ai import GeminiAI
from bot.telegram_handlers import (
    TelegramBotHandlers,
    SELECTING_CATEGORY,
    SELECTING_TYPE,
)
from analytics.daily_task_runner import DailyTaskRunner


# Setup logger for the bot runner specifically
logger.add(config.LOG_FILE)


async def post_init_tasks(application: Application):
    """Starts the scheduler for daily tasks after bot initialization."""
    scheduler = AsyncIOScheduler(timezone="Europe/Warsaw")
    job_runner = application.bot_data.get("scheduled_jobs")

    if not job_runner:
        logger.error("Missing 'scheduled_jobs' in application context.")
        return

    scheduler.add_job(
        job_runner.run_daily_tasks,
        "cron",
        hour=10,
        minute=3,
        name="Daily Financial Check",
    )
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info("Scheduler started.")


async def post_shutdown_tasks(application: Application):
    """Shuts down the scheduler when the bot stops."""
    if scheduler := application.bot_data.get("scheduler"):
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped.")


def main():
    """Starts the bot, initializes all services, and runs the scheduler."""
    logger.info("Starting Budget Bot application...")

    app_context = {}

    # --- Initialize all services and context ONCE ---
    try:
        authenticator = GoogleAuthenticator()
        gspread_client = authenticator.get_gspread_client()
        if not gspread_client:
            raise ConnectionError("Failed to initialize gspread client.")

        sheets_service = GoogleSheetsService(gspread_client)
        sheets_service.open_spreadsheet(config.SPREADSHEET_NAME)

        # Populate app context with shared services
        app_context["sheets_service"] = sheets_service
        app_context["expense_data_manager"] = ExpenseDataManager(sheets_service)
        app_context["metrics_calculator"] = DashboardMetricsCalculator(sheets_service)
        app_context["telegram_service"] = TelegramService()
        app_context["gemini_ai"] = GeminiAI(app_context)
        app_context["scheduled_jobs"] = DailyTaskRunner(app_context)

        # Start telegram app
        application = (
            Application.builder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .context_types(
                ContextTypes(context=CallbackContext, chat_data=dict, user_data=dict)
            )  # Explicitly define context types
            .post_init(post_init_tasks)
            .post_shutdown(post_shutdown_tasks)
            .build()
        )
        application.bot_data.update(app_context)

    except Exception as e:
        print("EXCEPTION", e)
        logger.critical(f"CRITICAL FAILURE during initial setup: {e}")
        # Attempt to send a startup failure message
        asyncio.run(TelegramService().send_message(f"🔥 Bot failed to start: {e}"))
        return

    # --- Bot handlers setup (remains the same) ---
    bot_handlers = TelegramBotHandlers(
        sheets_service=app_context["sheets_service"],
        telegram_service=app_context["telegram_service"],
        expense_data_manager=app_context["expense_data_manager"],
        metrics_calculator=app_context["metrics_calculator"],
        gemini_ai=app_context["gemini_ai"],
    )

    # --- Setup ConversationHandler for categorization ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("categorize", bot_handlers.start_categorization)],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(
                    bot_handlers.receive_category_choice, pattern="^cat_"
                )
            ],
            SELECTING_TYPE: [
                CallbackQueryHandler(bot_handlers.receive_type_choice, pattern="^type_")
            ],
        },
        fallbacks=[CommandHandler("cancel", bot_handlers.cancel_conversation)],
    )

    # --- Register all handlers ---
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(
        CommandHandler("help", bot_handlers.start_command)
    )  # help command also uses start_command
    application.add_handler(CommandHandler("summary", bot_handlers.summary_command))
    application.add_handler(CommandHandler("top5", bot_handlers.top5_command))
    application.add_handler(CommandHandler("newchat", bot_handlers.new_chat_command))
    application.add_handler(conv_handler)  # Add the conversation handler
    # Add a handler for all text messages that are NOT commands
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.handle_text_query)
    )

    logger.info("Bot is now polling for messages...")
    application.run_polling()


if __name__ == "__main__":
    main()
