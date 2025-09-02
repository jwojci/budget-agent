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
        self.budget_ws = sheets_service.get_worksheet(config.WORKSHEETS["budget"])

    def update_dashboard(self) -> dict | None:
        """
        Calculates a dynamic, proactive monthly budget and updates the dashboard.
        """
        logger.info("Starting dashboard update process...")
        try:
            # Load Expense Data
            df = self.expense_data_manager.load_expenses_dataframe()
            if df.empty:
                logger.warning(
                    "No expense data available to update dashboard. Skipping update."
                )
                return None
            metrics = self.metrics_calculator.calculate_all_metrics(df)
            if not metrics:
                logger.error("Could not calculate dashboard metrics. Skipping update.")
                return None

            # Need to get category types records for prepare_category_and_type_data
            # Reference config.WORKSHEETS["categories"] directly
            category_types_records = self.sheets_service.get_all_records(
                config.WORKSHEETS["categories"]
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

            top_merchants_start_row = (
                needs_wants_start_row + len(needs_wants_data_for_sheet) + 2
            )
            self.sheets_service.update_cells(
                self.budget_ws, f"E{top_merchants_start_row}", top_spending_data
            )

            if not df.empty:
                # Get the latest transaction date from the source data
                latest_transaction_date = df["Date"].max()
                # Format it as a string to store in the sheet
                signature = f"Last Updated from Data as of: {latest_transaction_date.strftime('%Y-%m-%d %H:%M:%S')}"
                # Write the signature to an out-of-the-way cell
                self.sheets_service.update_cells(self.budget_ws, "A20", [[signature]])

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
