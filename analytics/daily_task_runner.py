import asyncio
import datetime
from loguru import logger
from telegram.ext import Application

import config
from analytics.dashboard_updater import DashboardUpdater
from analytics.monthly_archiving import MonthlyArchiver
from analytics.anomaly_detection import AnomalyDetector
from analytics.weekly_digest import WeeklyDigestGenerator
from data_processing.email_processor import EmailProcessor


class DailyTaskRunner:
    def __init__(self, app_context: dict):
        self.app_context = app_context
        self.sheets_service = app_context["sheets_service"]
        self.telegram_service = app_context["telegram_service"]

        # Initialize services used only for the daily run
        self.monthly_archiver = MonthlyArchiver(
            self.sheets_service, app_context["expense_data_manager"]
        )
        self.email_processor = EmailProcessor(
            self.sheets_service, self.telegram_service
        )
        self.anomaly_detector = AnomalyDetector(app_context["expense_data_manager"])
        self.dashboard_updater = DashboardUpdater(
            self.sheets_service,
            app_context["expense_data_manager"],
            app_context["metrics_calculator"],
        )
        self.weekly_digest_generator = WeeklyDigestGenerator(
            app_context, self.telegram_service
        )
        logger.success("DailyTaskRunner initialized successfully.")

    async def run_daily_tasks(self, application: Application):
        """The main scheduled workflow of the budget tracker application."""
        try:
            logger.info("--- Starting Daily Scheduled Run ---")
            await self._check_and_fix_expenses_header()
            await self._run_monthly_archive()
            await self.email_processor.process_new_transactions()
            await self._run_anomaly_detection()
            await self._update_dashboard_and_notify()
            await self._run_weekly_digest_if_need(application)

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
            archived_data = self.monthly_archiver.archive_monthly_summary()
            if archived_data:
                summary_message = self.telegram_service.format_summary_for_telegram(
                    archived_data
                )
                await self.telegram_service.send_message(summary_message)

    async def _run_anomaly_detection(self):
        """Runs anomaly detection and sends alerts if any are found."""
        logger.info("Running anomaly detection...")
        anomaly_messages = self.anomaly_detector.check_for_spending_anomalies()
        for msg in anomaly_messages or []:
            await self.telegram_service.send_message(msg, parse_mode="Markdown")

        msg = (
            f"Sent {len(anomaly_messages)} anomaly alerts."
            if anomaly_messages
            else "No anomalies detected."
        )
        logger.info(msg)

    async def _update_dashboard_and_notify(self):
        """Updates the budget dashboard and sends a status notification."""
        logger.info("Updating dashboard...")
        dashboard_data = self.dashboard_updater.update_dashboard()

        if dashboard_data:
            remaining = dashboard_data.get("remaining_weekly", 0)
            safe_to_spend = dashboard_data.get("safe_to_spend_today", 0)

            message = (
                f"🏁 *Script Finished*\nDashboard updated.\n\n"
                f"💰 Weekly remaining: *{remaining:,.2f} PLN*\n"
                f"💡 Safe to spend today: *{safe_to_spend:,.2f} PLN*"
            )
        else:
            message = (
                "🏁 *Script Finished*\nDashboard updated, but summary data unavailable."
            )

        await self.telegram_service.send_message(message, parse_mode="Markdown")
        logger.info("Dashboard update complete.")

    async def _run_weekly_digest_if_need(self, application: Application):
        """Generates and sends the weekly AI digest on Mondays."""
        # if datetime.datetime.now().weekday() == 0:  # 0 is Monday
        await self.weekly_digest_generator.generate_and_send_digest(application)
