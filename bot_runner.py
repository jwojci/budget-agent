import asyncio
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


# Setup logger for the bot runner specifically
logger.add(config.LOG_FILE)


def main():
    """Starts the bot to listen for commands and messages."""
    logger.info("🤖 Starting Telegram bot with AI capabilities...")

    # Initialize services
    # Note: GoogleAuthenticator handles its own token management for Gmail/gspread
    # The gspread.oauth() approach uses the user's default browser for auth
    # For a production bot, a service account (gspread.service_account) is often preferred for gspread
    # You might want to pass the gspread client from GoogleAuthenticator if you only want one auth method
    # For now, let's keep gspread.oauth() as per your original code for simplicity,
    # but be aware it's a separate authentication flow from gmail_api_client.
    authenticator = GoogleAuthenticator()
    # The gspread client requires a file-based auth (oauth or service_account)
    # If using service_account, set config.GSPREAD_SERVICE_ACCOUNT_FILE
    # If using oauth, it will look for token.json or prompt for browser auth.
    gspread_client = authenticator.get_gspread_client()
    if not gspread_client:
        logger.critical("Failed to initialize gspread client. Exiting bot.")
        return

    sheets_service = GoogleSheetsService(gspread_client)

    try:
        sheets_service.open_spreadsheet(config.SPREADSHEET_NAME)
    except Exception as e:
        logger.critical(
            f"🔥 Could not open the Google Sheet '{config.SPREADSHEET_NAME}' for the bot. Halting. Error: {e}"
        )
        telegram_service = TelegramService()  # Initialize just to send error message
        asyncio.run(
            telegram_service.send_message(
                f"🔥 *Bot Startup Error*\nCould not open the Google Sheet: {config.SPREADSHEET_NAME}. Please check permissions and spelling.",
                parse_mode="Markdown",
            )
        )
        return

    telegram_service = TelegramService()  # Telegram bot token is from config
    gemini_ai = GeminiAI()  # Gemini API key is from config

    # Initialize data processing and analytics components
    expense_data_manager = ExpenseDataManager(sheets_service)
    metrics_calculator = DashboardMetricsCalculator(
        sheets_service
    )  # Metrics depends on sheet income
    transaction_parser = (
        TransactionParser()
    )  # Doesn't directly need sheets_service here

    # Initialize Telegram Handlers with all necessary dependencies
    bot_handlers = TelegramBotHandlers(
        sheets_service=sheets_service,
        telegram_service=telegram_service,
        expense_data_manager=expense_data_manager,
        metrics_calculator=metrics_calculator,
        gemini_ai=gemini_ai,
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

    logger.info("Bot is now polling for commands and messages...")
    application.run_polling()


if __name__ == "__main__":
    main()
