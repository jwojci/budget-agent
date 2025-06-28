import pandas as pd
from loguru import logger

from services.google_sheets import GoogleSheetsService
from data_processing.expense_data import ExpenseDataManager
from analytics.dashboard_metrics import DashboardMetricsCalculator
from config import *


class DashboardUpdater:
    """
    Manages updating the main budget dashboard in Google Sheets.
    """

    def __init__(
        self,
        sheets_service: GoogleSheetsService,
        expense_data_manager: ExpenseDataManager,
        metrics_calculator: DashboardMetricsCalculator,
    ):
        self.sheets_service = sheets_service
        self.expense_data_manager = expense_data_manager
        self.metrics_calculator = metrics_calculator
        self.budget_ws = None  # Worksheet object for the budget sheet

    def update_dashboard(self) -> dict | None:
        """
        Calculates a dynamic, proactive monthly budget and updates the dashboard.
        """
        logger.info("Starting dashboard update process...")
        try:
            # 1. Get Budget Worksheet (still needed for formatting later)
            # Reference config.BUDGET_WORKSHEET_NAME directly
            self.budget_ws = self.sheets_service.get_worksheet(BUDGET_WORKSHEET_NAME)

            # 2. Get Monthly Income using ExpenseDataManager
            monthly_disposable_income = (
                self.expense_data_manager.get_monthly_disposable_income()
            )
            if monthly_disposable_income == 0.0:
                logger.error("Monthly disposable income is 0. Cannot update dashboard.")
                return None

            # 3. Load Expense Data
            df = self.expense_data_manager.load_expenses_dataframe()
            if df.empty:
                logger.warning(
                    "No expense data available to update dashboard. Skipping update."
                )
                return None
            # 4. Calculate all metrics - PASS THE INCOME HERE
            metrics = self.metrics_calculator.calculate_all_metrics(
                df, monthly_disposable_income
            )
            if not metrics:
                logger.error("Could not calculate dashboard metrics. Skipping update.")
                return None

            # Need to get category types records for prepare_category_and_type_data
            # Reference config.CATEGORIES_WORKSHEET_NAME directly
            category_types_records = self.sheets_service.get_all_records(
                CATEGORIES_WORKSHEET_NAME
            )
            category_data_for_sheet, needs_wants_data_for_sheet = (
                self.metrics_calculator.prepare_category_and_type_data(
                    metrics["month_to_date_expenses_df"], category_types_records
                )
            )

            top_spending_data = self.metrics_calculator.prepare_top_merchants_data(df)

            # 5. Write to the sheet
            self.sheets_service.clear_worksheet(self.budget_ws)
            summary_data_for_sheet = self.metrics_calculator.prepare_summary_data(
                metrics
            )
            daily_breakdown_header, daily_spending_rows = (
                self.metrics_calculator.prepare_daily_breakdown_data(metrics)
            )

            main_dashboard_data = (
                summary_data_for_sheet + daily_breakdown_header + daily_spending_rows
            )
            self.sheets_service.update_cells(self.budget_ws, "A1", main_dashboard_data)

            self.sheets_service.update_cells(
                self.budget_ws, "E1", category_data_for_sheet
            )

            needs_wants_start_row = len(category_data_for_sheet) + 2
            self.sheets_service.update_cells(
                self.budget_ws, f"E{needs_wants_start_row}", needs_wants_data_for_sheet
            )
            logger.debug(f"DUPA 3 {needs_wants_data_for_sheet}")

            top_merchants_start_row = (
                needs_wants_start_row + len(needs_wants_data_for_sheet) + 2
            )
            self.sheets_service.update_cells(
                self.budget_ws, f"E{top_merchants_start_row}", top_spending_data
            )

            # 6. Apply Formatting (delegated to sheets_service)
            self.sheets_service.format_dashboard_sheet(
                self.budget_ws, metrics["target_weekly_spend"]
            )
            logger.success(
                "Budget sheet updated successfully with Proactive Monthly Plan logic."
            )

            return {
                "remaining_weekly": metrics["remaining_weekly_target"],
                "safe_to_spend_today": metrics["safe_to_spend_today"],
            }
        except Exception as e:
            logger.error(
                f"An error occurred during dashboard update: {e}", exc_info=True
            )
            return None
