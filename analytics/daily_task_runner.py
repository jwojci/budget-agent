import asyncio
import datetime
from loguru import logger
from telegram.ext import Application
from langchain_core.messages import HumanMessage, AIMessage

import config
from auth.google_auth import GoogleAuthenticator
from data_processing.transaction_parser import get_parser
from services.gmail_api import GmailService
from analytics.dashboard_updater import DashboardUpdater
from analytics.monthly_archiving import MonthlyArchiver
from analytics.anomaly_detection import AnomalyDetector
from ai.agent import BudgetAgent


class DailyTaskRunner:
    def __init__(self, app_context: dict):
        self.app_context = app_context
        self.sheets_service = app_context["sheets_service"]
        self.expense_data_manager = app_context["expense_data_manager"]
        self.telegram_service = app_context["telegram_service"]
        self.budget_agent = app_context["budget_agent"]
        # Initialize services used only for the daily run
        try:
            authenticator = GoogleAuthenticator()
            gmail_api_client = authenticator.get_gmail_service()
            if not gmail_api_client:
                raise ConnectionError("Failed to get Gmail client.")
            self.gmail_service = GmailService(gmail_api_client)
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

    def _get_main_chat_agent(self, application: Application) -> BudgetAgent | None:
        """
        Gets the user's persistent BudgetAgent instance from chat_data.
        """
        chat_id = int(config.TELEGRAM_CHAT_ID)
        chat_data = application.chat_data.get(chat_id, {})

        if "budget_agent_instance" not in chat_data:
            logger.info("Main chat agent not found, creating one for weekly digest.")
            chat_data["budget_agent_instance"] = BudgetAgent(self.app_context)
            self.application.chat_data[chat_id] = chat_data

        return chat_data["budget_agent_instance"]

    async def run_daily_tasks(self, application: Application):
        """The main scheduled workflow of the budget tracker application."""
        try:
            logger.info("--- Starting Daily Scheduled Run ---")
            await self._check_and_fix_expenses_header()
            await self._run_monthly_archive()
            await self._process_daily_emails()
            await self._run_anomaly_detection_and_dashboard_update()
            await self._run_ai_weekly_digest(application)
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
                config.WORKSHEETS["expenses"]
            )
            header = expenses_ws.row_values(1)
            if header != config.EXPENSE_HEADER:
                logger.warning("Expenses sheet header is incorrect. Fixing...")
                expenses_ws.clear()
                self.sheets_service.append_row(expenses_ws, config.EXPENSE_HEADER)
            else:
                logger.info("Expenses sheet header is correct.")
        except Exception as e:
            logger.error(f"Failed to check or fix expenses header: {e}", exc_info=True)

    async def _run_monthly_archive(self):
        """Handles monthly archiving if applicable."""
        today = datetime.datetime.now()
        if today.day <= config.ARCHIVE_DAYS:  # Days 1-4 of the month for archiving
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
        """Fetches and processes daily expense emails using the parser factory."""
        logger.info("Processing daily emails...")

        # Get parser
        parser = get_parser(config.EMAIL_SENDER)
        if not parser:
            logger.error(f"No parser for '{config.EMAIL_SENDER}'.")
            await self.telegram_service.send_message(
                f"⚠️ Parser Error: No parser for '{config.EMAIL_SENDER}'."
            )
            return

        # Setup worksheets and data
        expenses_ws = self.sheets_service.get_worksheet(config.WORKSHEETS["expenses"])
        categories_ws = self.sheets_service.get_worksheet(
            config.WORKSHEETS["categories"]
        )
        existing_dates = set(
            self.sheets_service.get_col_values(config.WORKSHEETS["expenses"], 6)[1:]
        )
        category_records = self.sheets_service.get_all_records(
            config.WORKSHEETS["categories"]
        )
        existing_keywords = {
            rec.get("Keyword", "").lower()
            for rec in category_records
            if rec.get("Keyword")
        }

        new_rows, new_keywords = [], set()
        for email_id in reversed(
            self.gmail_service.get_email_ids_for_current_month() or []
        ):
            attachment_path = self.gmail_service.save_attachments_from_message(email_id)
            if not attachment_path:
                logger.warning(f"No attachment for email {email_id}.")
                continue

            # Parse and process transactions
            raw_transactions = parser.parse_html(attachment_path)
            rows, keywords = parser.process_transactions(
                raw_transactions, attachment_path, existing_dates, category_records
            )
            new_rows.extend(rows)
            new_keywords.update(keywords)

        # Update sheets
        if new_rows:
            logger.info(f"Adding {len(new_rows)} transactions...")
            self.sheets_service.append_rows(expenses_ws, new_rows)
            await self.telegram_service.send_message(
                f"✅ {len(new_rows)} transactions saved."
            )

        # Handle new keywords
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
                + "\n\nUse /categorize."
            )

        logger.info("Email processing complete.")

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

    async def _run_ai_weekly_digest(self, application: Application):
        """Generates, sends, and saves weekly digest to the main chat context."""
        if datetime.datetime.now().weekday() != 0:  # 0 is Monday
            return

        logger.info("Generating and contextualizing weekly AI digest...")
        try:
            main_agent = self._get_main_chat_agent(application)
            if not main_agent:
                return

            prompt = "Generate the weekly financial digest based on last week's spending data."
            digest_text = await asyncio.to_thread(main_agent.invoke, prompt)

            # send the message to the user
            await self.telegram_service.send_message(digest_text, parse_mode="Markdown")

            # this makes the agent "remember" this system-initiated conversation.
            main_agent.chat_history.append(HumanMessage(content=prompt))
            main_agent.chat_history.append(AIMessage(content=digest_text))

            logger.info(
                "Weekly AI digest sent and context updated in main chat session."
            )

        except Exception as e:
            logger.error(f"Failed to generate and contextualize AI weekly digest: {e}")
