import asyncio
import pandas as pd
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
from ai.agent import BudgetAgent
from bot.telegram_handlers import (
    TelegramBotHandlers,
    SELECTING_CATEGORY,
    SELECTING_TYPE,
)
from analytics.daily_task_runner import DailyTaskRunner
from analytics.dashboard_updater import DashboardUpdater


# Setup logger for the bot runner specifically
logger.add(config.LOG_FILE)


async def _check_and_update_dashboard(app: Application):
    """
    Checks the dashboard sheet for last update date and updates its if necessary.
    """
    logger.info("Checking dashboard...")
    try:
        sheets = app.bot_data["sheets_service"]
        expenses = app.bot_data["expense_data_manager"]
        df = expenses.load_expenses_dataframe()

        latest_timestamp = df["Date"].max() if not df.empty else None
        stored_signature = sheets.get_cell_value(config.WORKSHEETS["budget"], "A20")
        stored_timestamp = (
            pd.to_datetime(stored_signature.split(": ", 1)[1])
            if stored_signature
            else None
        )

        if not stored_timestamp or latest_timestamp != stored_timestamp:
            logger.info("Updating dashboard...")
            updater = DashboardUpdater(
                sheets, expenses, app.bot_data["metrics_calculator"]
            )
            updater.update_dashboard()
            logger.success("Dashboard updated.")
        else:
            logger.info("Dashboard up-to-date.")

    except Exception as e:
        logger.critical(
            f"Failed to perform initial dashboard update on startup: {e}", exc_info=True
        )
        await app.bot_data["telegram_service"].send_message(
            "**Critical Error:** The bot started but failed to update the dashboard. Please check the logs."
        )


async def _setup_scheduler(app: Application):
    """
    Sets up the scheduler to run daily tasks
    """
    try:
        scheduler = AsyncIOScheduler(timezone="Europe/Warsaw")
        job_runner = app.bot_data.get("scheduled_jobs")

        if not job_runner:
            logger.error("Missing 'scheduled_jobs' in application context.")
            return

        scheduler.add_job(
            job_runner.run_daily_tasks,
            "cron",
            hour=22,
            minute=5,
            name="Daily Financial Check",
            args=[app],
        )
        scheduler.start()
        app.bot_data["scheduler"] = scheduler
        logger.info("Scheduler started for daily tasks.")
    except Exception as e:
        logger.critical(f"Failed to setup scheduler on startup: {e}")
        await app.bot_data["telegram_service"].send_message(
            "**Critical Error:** The bot started but failed to setup the scheduler. Please check the logs."
        )


async def post_init_tasks(app: Application):
    """Initialize scheduler and update dashboard."""
    await _check_and_update_dashboard(app)
    await _setup_scheduler(app)


async def post_shutdown_tasks(application: Application):
    """Shuts down the scheduler when the bot stops."""
    if scheduler := application.bot_data.get("scheduler"):
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped.")


def main():
    """Starts the bot, initializes all services, and runs the scheduler."""
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
        app_context["budget_agent"] = BudgetAgent(app_context)
        app_context["scheduled_jobs"] = DailyTaskRunner(app_context)

        # Start telegram app
        application = (
            Application.builder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .context_types(
                ContextTypes(context=CallbackContext, chat_data=dict, user_data=dict)
            )
            .post_init(post_init_tasks)
            .post_shutdown(post_shutdown_tasks)
            .build()
        )

        app_context["application"] = application

        application.bot_data.update(app_context)

    except Exception as e:
        logger.critical(f"CRITICAL FAILURE during initial setup: {e}")
        asyncio.run(TelegramService().send_message(f"🔥 Bot failed to start: {e}"))
        return

    # --- Bot handlers setup ---
    bot_handlers = TelegramBotHandlers(
        sheets_service=app_context["sheets_service"],
        telegram_service=app_context["telegram_service"],
        expense_data_manager=app_context["expense_data_manager"],
        metrics_calculator=app_context["metrics_calculator"],
        budget_agent=app_context["budget_agent"],
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
        # Add a fallback for the cancel button and the /cancel command
        fallbacks=[
            CommandHandler("cancel", bot_handlers.cancel_conversation),
            CallbackQueryHandler(
                bot_handlers.cancel_conversation, pattern="^cat_cancel$"
            ),
        ],
        # Optional: Add a timeout
        conversation_timeout=120,  # 2 minutes
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

    logger.success("Bot is now polling for messages...")
    application.run_polling()


if __name__ == "__main__":
    main()
