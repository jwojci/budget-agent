import asyncio
import datetime
from loguru import logger

import config
from auth.google_auth import GoogleAuthenticator
from services.google_sheets import GoogleSheetsService
from services.gmail_api import GmailService
from services.telegram_api import TelegramService
from data_processing.expense_data import ExpenseDataManager
from data_processing.transaction_parser import TransactionParser
from analytics.dashboard_metrics import DashboardMetricsCalculator
from analytics.monthly_archiving import MonthlyArchiver
from analytics.anomaly_detection import AnomalyDetector
from analytics.dashboard_updater import DashboardUpdater

from ai.gemini_ai import GeminiAI


logger.add(config.LOG_FILE)


async def _check_and_fix_expenses_header(sheets_service: GoogleSheetsService):
    """Ensures the expenses worksheet has the correct header."""
    try:
        expenses_ws = sheets_service.get_worksheet(config.EXPENSES_WORKSHEET_NAME)
        all_values = sheets_service.get_all_values(config.EXPENSES_WORKSHEET_NAME)

        if not all_values or all_values[0] != config.EXPECTED_EXPENSE_HEADER:
            logger.warning(
                f"Expenses sheet '{config.EXPENSES_WORKSHEET_NAME}' has incorrect or missing headers. Recreating header."
            )
            sheets_service.clear_worksheet(expenses_ws)
            sheets_service.append_row(expenses_ws, config.EXPECTED_EXPENSE_HEADER)
            logger.info("Expenses sheet header fixed.")
        else:
            logger.info("Expenses sheet header is correct.")
    except Exception as e:
        logger.error(f"Failed to check or fix expenses header: {e}", exc_info=True)


async def _run_monthly_archive(
    sheets_service: GoogleSheetsService,
    expense_data_manager: ExpenseDataManager,
    telegram_service: TelegramService,
):
    """Handles monthly archiving if applicable."""
    today = datetime.datetime.now()
    if today.day <= 4:  # Days 1-4 of the month for archiving
        logger.info("Checking for monthly summary archiving...")
        monthly_archiver = MonthlyArchiver(sheets_service, expense_data_manager)
        archived_data = monthly_archiver.archive_monthly_summary()
        if archived_data:
            summary_message = telegram_service.format_summary_for_telegram(
                archived_data
            )
            await telegram_service.send_message(summary_message)
            logger.info("Monthly summary archived and sent to Telegram.")
        else:
            logger.info("No monthly summary to archive or already archived.")
    else:
        logger.info("Not the archiving period for monthly summary (day > 4).")


async def _run_ai_weekly_digest(
    expense_data_manager: ExpenseDataManager,
    telegram_service: TelegramService,
    gemini_ai: GeminiAI,
):
    """Generates and sends the AI weekly digest on Mondays."""
    today = datetime.datetime.now()
    if today.weekday() == 0:  # Monday
        logger.info("It's Monday! Generating AI Weekly Digest.")
        df = expense_data_manager.load_expenses_dataframe()
        if not df.empty:
            start_of_last_week = today - datetime.timedelta(days=today.weekday() + 7)
            end_of_last_week = today - datetime.timedelta(days=today.weekday() + 1)
            last_week_df = df[
                (df["Date"] >= start_of_last_week) & (df["Date"] <= end_of_last_week)
            ].copy()

            digest_message = gemini_ai.get_ai_weekly_digest(last_week_df)
            await telegram_service.send_message(digest_message, parse_mode="Markdown")
            logger.success("AI Weekly Digest generated and sent.")
        else:
            logger.warning("No expense data available for AI Weekly Digest.")
    else:
        logger.info("Not Monday. Skipping AI Weekly Digest.")


async def _process_daily_emails(
    gmail_service: GmailService,
    sheets_service: GoogleSheetsService,
    transaction_parser: TransactionParser,
    telegram_service: TelegramService,
):
    """Fetches and processes daily expense emails."""
    logger.info("Starting daily email processing...")

    expenses_ws = sheets_service.get_worksheet(config.EXPENSES_WORKSHEET_NAME)
    categories_ws = sheets_service.get_worksheet(config.CATEGORIES_WORKSHEET_NAME)

    # Get existing dates from the sheet (column 6 is 'Date')
    existing_expense_dates = set(
        sheets_service.get_col_values(config.EXPENSES_WORKSHEET_NAME, 6)[1:]
    )  # Skip header

    # Get all category data including keywords, category, and type
    all_category_data_for_processing = sheets_service.get_all_records(
        config.CATEGORIES_WORKSHEET_NAME
    )
    existing_keywords_in_category_sheet = {
        cat.get("Keyword", "").lower()
        for cat in all_category_data_for_processing
        if cat.get("Keyword")
    }

    email_ids = gmail_service.get_email_ids_for_current_month()
    all_new_rows, all_new_keywords = [], set()

    if email_ids:
        email_ids.reverse()  # Process oldest first for correct insertion order
        logger.info(f"Found {len(email_ids)} emails to process.")
        for email_id in email_ids:
            attachment_path = gmail_service.save_attachments_from_message(email_id)
            if attachment_path:
                expenses_raw = transaction_parser.parse_expenses_from_html(
                    attachment_path
                )
                new_rows, new_keywords = (
                    transaction_parser.extract_and_categorize_transaction_details(
                        expenses_raw,
                        attachment_path,
                        existing_expense_dates,
                        all_category_data_for_processing,
                    )
                )
                if new_rows:
                    all_new_rows.extend(new_rows)
                if new_keywords:
                    all_new_keywords.update(new_keywords)
            else:
                logger.warning(
                    f"Could not save attachment for email ID: {email_id}. Skipping parsing."
                )

    if all_new_rows:
        logger.info(
            f"Inserting {len(all_new_rows)} new transaction rows into '{config.EXPENSES_WORKSHEET_NAME}'..."
        )
        sheets_service.append_rows(expenses_ws, all_new_rows[::-1])
        await telegram_service.send_message(
            f"✅ *{len(all_new_rows)} new transactions* have been saved."
        )
    else:
        logger.info("No new transactions found from emails to save.")

    truly_new_keywords = [
        kw
        for kw in all_new_keywords
        if kw.lower() not in existing_keywords_in_category_sheet
    ]
    if truly_new_keywords:
        logger.info(
            f"Found {len(truly_new_keywords)} new unique keywords to categorize..."
        )
        rows_to_add = [
            [kw, "", ""] for kw in truly_new_keywords
        ]  # Keyword, Category (empty), Type (empty)
        sheets_service.append_rows(categories_ws, rows_to_add)
        keywords_str = "\n- ".join(truly_new_keywords)
        await telegram_service.send_message(
            f"🤔 *New Keywords Found*\nPlease categorize the following:\n- {keywords_str}\n\nUse /categorize in the bot to do it interactively."
        )
    else:
        logger.info("No new unique keywords found to add to the Categories sheet.")
    logger.info("Daily email processing complete.")


async def _run_anomaly_detection_and_dashboard_update(
    anomaly_detector: AnomalyDetector,
    dashboard_updater: DashboardUpdater,
    telegram_service: TelegramService,
):
    """Runs anomaly detection and updates the main budget dashboard."""
    logger.info("Starting anomaly detection and dashboard update sequence...")

    # 1. Run Anomaly Detection
    anomaly_messages = anomaly_detector.check_for_spending_anomalies()
    if anomaly_messages:
        for msg in anomaly_messages:
            await telegram_service.send_message(msg, parse_mode="Markdown")
        logger.info(f"Sent {len(anomaly_messages)} spending anomaly alerts.")
    else:
        logger.info("No spending anomalies detected.")

    # 2. Update Dashboard
    logger.info("Updating the dashboard...")
    dashboard_data = dashboard_updater.update_dashboard()

    if dashboard_data:
        remaining = dashboard_data.get("remaining_weekly", 0)
        safe_to_spend = dashboard_data.get("safe_to_spend_today", 0)
        final_message = (
            f"🏁 *Script Finished*\nYour dashboard is up to date.\n\n"
            f"💰 Remaining this week: *{remaining:,.2f} PLN*\n"
            f"💡 Safe to spend today: *{safe_to_spend:,.2f} PLN*"
        )
        await telegram_service.send_message(final_message, parse_mode="Markdown")
    else:
        await telegram_service.send_message(
            "🏁 *Script Finished*\nDashboard updated, but summary data was not available."
        )
    logger.info("Dashboard update process complete.")


async def main_scheduled_run():
    """The main scheduled workflow of the budget tracker application."""
    # await telegram_service.send_message(
    #     "🚀 *Budget Script Started*\nRunning daily financial check..."
    # )

    try:
        # --- Authentication and Service Initialization ---
        authenticator = GoogleAuthenticator()
        gmail_api_client = authenticator.get_gmail_service()
        gspread_client = authenticator.get_gspread_client()

        if not gmail_api_client or not gspread_client:
            raise Exception("Failed to initialize Google services clients.")

        # Instantiate services/managers with their dependencies
        sheets_service = GoogleSheetsService(gspread_client)
        try:
            sheets_service.open_spreadsheet(config.SPREADSHEET_NAME)
        except Exception as e:
            logger.critical(
                f"🔥 Could not open the Google Sheet '{config.SPREADSHEET_NAME}'. Halting script. Error: {e}"
            )
            await telegram_service.send_message(
                f"🔥 *Critical Error*\nCould not open the Google Sheet: {config.SPREADSHEET_NAME}. Please check permissions and spelling."
            )
            return  # Stop execution if the sheet can't be opened
        gmail_service = GmailService(gmail_api_client)
        telegram_service = TelegramService()  # Global instance, can be passed around

        expense_data_manager = ExpenseDataManager(sheets_service)
        transaction_parser = TransactionParser()  # Doesn't need sheets_service directly
        metrics_calculator = DashboardMetricsCalculator(sheets_service)
        anomaly_detector = AnomalyDetector(expense_data_manager)
        dashboard_updater = DashboardUpdater(
            sheets_service, expense_data_manager, metrics_calculator
        )

        # --- Run Workflow Steps ---
        await _check_and_fix_expenses_header(sheets_service)
        await _run_monthly_archive(
            sheets_service, expense_data_manager, telegram_service
        )
        await _run_ai_weekly_digest(expense_data_manager, telegram_service, GeminiAI())
        await _process_daily_emails(
            gmail_service,
            sheets_service,
            transaction_parser,
            telegram_service,
        )
        await _run_anomaly_detection_and_dashboard_update(
            anomaly_detector,
            dashboard_updater,
            telegram_service,
        )

        logger.success("✅ Budget Tracker daily script finished successfully.")

    except Exception as e:
        logger.critical(
            f"🔥 A critical error occurred in main_scheduled_run: {e}", exc_info=True
        )
        await telegram_service.send_message(
            f"🔥 *Critical Script Error*\nThe daily budget script failed to run. Please check the logs."
        )


def run_sample_data_generator():
    """Helper to run the sample data generator."""
    try:
        # Authenticate and get gspread client
        authenticator = GoogleAuthenticator()
        gspread_client = authenticator.get_gspread_client()
        if not gspread_client:
            raise Exception("Failed to get gspread client for sample data generation.")

        sheets_service = GoogleSheetsService(gspread_client)
        expense_data_manager = ExpenseDataManager(sheets_service)

        expense_data_manager.generate_sample_data()
        # After generating sample data, update the dashboard to reflect it
        metrics_calculator = DashboardMetricsCalculator(sheets_service)
        dashboard_updater = DashboardUpdater(
            sheets_service, expense_data_manager, metrics_calculator
        )
        dashboard_updater.update_dashboard()

    except Exception as e:
        logger.error(
            f"An error occurred while running the sample data generator: {e}",
            exc_info=True,
        )


if __name__ == "__main__":
    # --- To run the normal daily script, use this: ---
    asyncio.run(main_scheduled_run())

    # --- To run the bot, you would run bot_runner.py separately.
    # --- To generate sample data for testing, uncomment the line below and comment out main_scheduled_run() ---
    # run_sample_data_generator()
