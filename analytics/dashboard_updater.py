import pandas as pd
from loguru import logger
from services.google_sheets import GoogleSheetsService
from data_processing.expense_data import ExpenseDataManager
from analytics.dashboard_metrics import DashboardMetricsCalculator
import config


class DashboardUpdater:
    """Updates the budget dashboard in Google Sheets."""

    def __init__(
        self,
        sheets_service: GoogleSheetsService,
        expense_data_manager: ExpenseDataManager,
        metrics_calculator: DashboardMetricsCalculator,
    ):
        self.sheets_service = sheets_service
        self.expense_data_manager = expense_data_manager
        self.metrics_calculator = metrics_calculator
        self.budget_ws = sheets_service.get_worksheet(config.BUDGET_WORKSHEET_NAME)

    def update_dashboard(self) -> dict | None:
        """Updates dashboard with calculated metrics."""
        logger.info("Updating dashboard...")

        try:
            # Get monthly income
            income = self.expense_data_manager.get_monthly_disposable_income()
            if income == 0.0:
                logger.error("Monthly income is 0.")
                return None

            # Load expense data
            df = self.expense_data_manager.load_expenses_dataframe()
            if df.empty:
                logger.warning("No expense data available.")
                self.sheets_service.clear_worksheet(self.budget_ws)
                self.sheets_service.update_cells(
                    self.budget_ws, config.NR_BUDGET_SUMMARY, [["No Data"]]
                )
                return None

            # Calculate metrics
            metrics = self.metrics_calculator.calculate_all_metrics(df, income)
            if not metrics:
                logger.error("Failed to calculate metrics.")
                return None

            # Prepare data blocks
            summary_data = self.metrics_calculator.prepare_summary_data(metrics)
            daily_header, daily_rows = (
                self.metrics_calculator.prepare_daily_breakdown_data(metrics)
            )
            category_records = self.sheets_service.get_all_records(
                config.CATEGORIES_WORKSHEET_NAME
            )
            category_data, needs_wants_data = (
                self.metrics_calculator.prepare_category_and_type_data(
                    metrics["month_to_date_expenses_df"], category_records
                )
            )
            top_spending_data = self.metrics_calculator.prepare_top_merchants_data(df)

            # Combine data for sheet
            main_data = summary_data + daily_header + daily_rows
            side_data = (
                category_data + [[]] + needs_wants_data + [[]] + top_spending_data
            )

            # Update sheet
            self.sheets_service.clear_worksheet(self.budget_ws)
            self.sheets_service.update_cells(
                self.budget_ws, config.NR_BUDGET_SUMMARY, main_data
            )
            self.sheets_service.update_cells(
                self.budget_ws, config.NR_DASHBOARD_SIDEPANEL, side_data
            )
            self.sheets_service.format_dashboard_sheet(
                self.budget_ws, metrics["target_weekly_spend"]
            )

            logger.info("Dashboard updated.")
            return {
                "remaining_weekly": metrics["remaining_weekly_target"],
                "safe_to_spend_today": metrics["safe_to_spend_today"],
            }

        except Exception as e:
            logger.error(f"Dashboard update failed: {e}")
            return None
