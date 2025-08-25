import asyncio
import datetime
from loguru import logger

import config
from auth.google_auth import GoogleAuthenticator
from data_processing.transaction_parser import TransactionParser
from services.gmail_api import GmailService
from analytics.dashboard_updater import DashboardUpdater
from analytics.monthly_archiving import MonthlyArchiver
from analytics.anomaly_detection import AnomalyDetector


class DailyTaskRunner:
    def __init__(self, app_context: dict):
        self.app_context = app_context
        self.sheets_service = app_context["sheets_service"]
        self.expense_data_manager = app_context["expense_data_manager"]
        self.telegram_service = app_context["telegram_service"]
        self.gemini_ai = app_context["gemini_ai"]
        # Initialize services used only for the daily run
        try:
            authenticator = GoogleAuthenticator()
            gmail_api_client = authenticator.get_gmail_service()
            if not gmail_api_client:
                raise ConnectionError("Failed to get Gmail client.")
            self.gmail_service = GmailService(gmail_api_client)
            self.transaction_parser = TransactionParser()
            self.dashboard_updater = DashboardUpdater(
                self.sheets_service,
                self.expense_data_manager,
                app_context["metrics_calculator"],
            )
            self.anomaly_detector = AnomalyDetector(self.expense_data_manager)
            self.monthly_archiver = MonthlyArchiver(
                self.sheets_service, self.expense_data_manager
            )
            logger.success("Scheduled jobs coordinator initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize services for scheduled jobs: {e}")
            raise

    async def run_daily_tasks(self):
        """The main scheduled workflow of the budget tracker application."""
        try:
            logger.info("--- Starting Daily Scheduled Run ---")
            await self._check_and_fix_expenses_header()
            await self._run_monthly_archive()
            await self._process_daily_emails()
            await self._run_anomaly_detection_and_dashboard_update()
            await self._run_ai_weekly_digest()
            logger.success("✅ Daily run finished successfully.")
        except Exception as e:
            logger.critical(
                f"A critical error occurred in the daily run: {e}", exc_info=True
            )
            await self.telegram_service.send_message(
                "🔥 *Critical Script Error*\nThe daily budget script failed. Please check the logs."
            )

    async def _check_and_fix_expenses_header(self):
        """Ensures the expenses worksheet has the correct header."""
        try:
            expenses_ws = self.sheets_service.get_worksheet(
                config.EXPENSES_WORKSHEET_NAME
            )
            header = expenses_ws.row_values(1)
            if header != config.EXPECTED_EXPENSE_HEADER:
                logger.warning("Expenses sheet header is incorrect. Fixing...")
                expenses_ws.clear()
                self.sheets_service.append_row(
                    expenses_ws, config.EXPECTED_EXPENSE_HEADER
                )
            else:
                logger.info("Expenses sheet header is correct.")
        except Exception as e:
            logger.error(f"Failed to check or fix expenses header: {e}", exc_info=True)

    async def _run_monthly_archive(self):
        """Handles monthly archiving if applicable."""
        today = datetime.datetime.now()
        if today.day <= 4:  # Days 1-4 of the month for archiving
            logger.info("Checking for monthly summary archiving...")
            monthly_archiver = MonthlyArchiver(
                self.sheets_service, self.expense_data_manager
            )
            archived_data = monthly_archiver.archive_monthly_summary()
            if archived_data:
                summary_message = self.telegram_service.format_summary_for_telegram(
                    archived_data
                )
                await self.telegram_service.send_message(summary_message)

    async def _process_daily_emails(self):
        """Fetches and processes daily expense emails."""
        logger.info("Processing daily emails...")

        expenses_ws = self.sheets_service.get_worksheet(config.EXPENSES_WORKSHEET_NAME)
        categories_ws = self.sheets_service.get_worksheet(
            config.CATEGORIES_WORKSHEET_NAME
        )

        existing_dates = set(
            self.sheets_service.get_col_values(config.EXPENSES_WORKSHEET_NAME, 6)[1:]
        )
        categories = self.sheets_service.get_all_records(
            config.CATEGORIES_WORKSHEET_NAME
        )
        existing_keywords = {
            cat["Keyword"].lower() for cat in categories if cat.get("Keyword")
        }

        new_rows, new_keywords = [], set()
        for email_id in reversed(self.gmail_service.get_email_ids_for_current_month()):
            attachment_path = self.gmail_service.save_attachments_from_message(email_id)
            if not attachment_path:
                logger.warning(f"No attachment for email {email_id}. Skipping.")
                continue

            expenses = self.transaction_parser.parse_expenses_from_html(attachment_path)
            rows, keywords = (
                self.transaction_parser.extract_and_categorize_transaction_details(
                    expenses, attachment_path, existing_dates, categories
                )
            )
            new_rows.extend(rows)
            new_keywords.update(keywords)

        if new_rows:
            logger.info(f"Adding {len(new_rows)} new transactions...")
            self.sheets_service.append_rows(expenses_ws, new_rows[::-1])
            await self.telegram_service.send_message(
                f"✅ {len(new_rows)} new transactions saved."
            )

        truly_new_keywords = [
            kw for kw in new_keywords if kw.lower() not in existing_keywords
        ]
        if truly_new_keywords:
            logger.info(f"Adding {len(truly_new_keywords)} new keywords...")
            self.sheets_service.append_rows(
                categories_ws, [[kw, "", ""] for kw in truly_new_keywords]
            )
            await self.telegram_service.send_message(
                f"🤔 New Keywords Found\nPlease categorize:\n- "
                + "\n- ".join(truly_new_keywords)
                + "\n\nUse /categorize in the bot."
            )

        logger.info("Daily email processing complete.")

    async def _run_anomaly_detection_and_dashboard_update(self):
        """Runs anomaly detection and updates the budget dashboard."""
        logger.info("Running anomaly detection and dashboard update...")

        # Run anomaly detection
        anomaly_messages = self.anomaly_detector.check_for_spending_anomalies()
        for msg in anomaly_messages or []:
            await self.telegram_service.send_message(msg, parse_mode="Markdown")
        logger.info(
            f"Sent {len(anomaly_messages)} anomaly alerts."
            if anomaly_messages
            else "No anomalies detected."
        )

        # Update dashboard
        logger.info("Updating dashboard...")
        dashboard_data = self.dashboard_updater.update_dashboard()
        remaining = dashboard_data.get("remaining_weekly", 0) if dashboard_data else 0
        safe_to_spend = (
            dashboard_data.get("safe_to_spend_today", 0) if dashboard_data else 0
        )

        message = (
            (
                f"🏁 *Script Finished*\nDashboard updated.\n\n"
                f"💰 Weekly remaining: *{remaining:,.2f} PLN*\n"
                f"💡 Safe to spend today: *{safe_to_spend:,.2f} PLN*"
            )
            if dashboard_data
            else "🏁 *Script Finished*\nDashboard updated, but summary data unavailable."
        )

        await self.telegram_service.send_message(message, parse_mode="Markdown")
        logger.info("Dashboard update complete.")

    async def _run_ai_weekly_digest(self):
        """Generates and sends weekly financial digest on Mondays, updating main chat context."""
        if datetime.datetime.now().weekday() != 0:  # 0 is Monday
            return

        logger.info("Generating weekly digest...")

        try:
            # Create temporary session for digest
            temp_session = self.gemini_ai.start_new_chat()
            if not temp_session:
                logger.error("Failed to start AI session for digest.")
                return

            # Generate digest
            digest_text = (
                await asyncio.to_thread(
                    temp_session.send_message,
                    "Generate weekly financial digest based on last week's data.",
                )
            ).text

            # Send digest to user
            await self.telegram_service.send_message(digest_text, parse_mode="Markdown")

            # Update main chat session
            chat_id = int(config.TELEGRAM_CHAT_ID)
            main_session = (
                self.application.chat_data[chat_id].get("ai_chat_session")
                or self.gemini_ai.start_new_chat()
            )
            main_session.history = temp_session.history
            self.application.chat_data[chat_id]["ai_chat_session"] = main_session

            logger.info("Weekly digest sent and chat context updated.")

        except Exception as e:
            logger.error(f"Failed to generate digest: {e}")
