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
)

import config
from auth.google_auth import GoogleAuthenticator
from services.google_sheets import GoogleSheetsService
from services.gmail_api import GmailService
from services.telegram_api import TelegramService
from data_processing.expense_data import ExpenseDataManager
from data_processing.transaction_parser import (
    TransactionParser,
)  # Needed for process_daily_emails
from analytics.dashboard_metrics import DashboardMetricsCalculator
from analytics.monthly_archiving import MonthlyArchiver
from analytics.anomaly_detection import AnomalyDetector
from ai.gemini_ai import GeminiAI
from bot.telegram_handlers import (
    TelegramBotHandlers,
    SELECTING_CATEGORY,
    SELECTING_TYPE,
)  # Import states too
from analytics.scheduled_jobs import ScheduledJobs


# Setup logger for the bot runner specifically
logger.add(config.LOG_FILE)


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

        # --- NEW: Initialize the jobs coordinator with the context ---
        app_context["scheduled_jobs"] = ScheduledJobs(app_context)

    except Exception as e:
        logger.critical(f"CRITICAL FAILURE during initial setup: {e}", exc_info=True)
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

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

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

    # --- Setup the scheduler (now much cleaner) ---
    scheduler = AsyncIOScheduler(timezone="Europe/Warsaw")
    job_runner = app_context["scheduled_jobs"]  # Get the instance from the context

    scheduler.add_job(
        job_runner.run_daily_tasks,
        "cron",
        hour=10,
        minute=3,
        name="Daily Financial Check",
    )
    scheduler.start()
    logger.info("Scheduler started successfully.")

    logger.info("Bot is now polling for messages...")
    application.run_polling()


if __name__ == "__main__":
    main()
