import datetime

from loguru import logger
from services.google_sheets import GoogleSheetsService
from data_processing.expense_data import (
    ExpenseDataManager,
)  # To get monthly income and category spending

from config import *


class MonthlyArchiver:
    """
    Manages the archiving of monthly spending summaries to a 'History' sheet.
    """

    def __init__(
        self,
        sheets_service: GoogleSheetsService,
        expense_data_manager: ExpenseDataManager,
    ):
        self.sheets_service = sheets_service
        self.expense_data_manager = expense_data_manager

    def _get_previous_month_info(self) -> tuple[int, int, str]:
        """Calculates and returns the year, month, and YYYY-MM string for the previous month."""
        first_day_current_month = datetime.datetime.now().replace(day=1)
        last_day_previous_month = first_day_current_month - datetime.timedelta(days=1)
        year = last_day_previous_month.year
        month = last_day_previous_month.month
        month_str = last_day_previous_month.strftime("%Y-%m")
        return year, month, month_str

    def _is_month_archived(self, month_str: str) -> bool:
        """Checks if the given month's summary is already archived."""
        try:
            archived_months = self.sheets_service.get_col_values(
                HISTORY_WORKSHEET_NAME, 1
            )
            return month_str in archived_months
        except Exception as e:
            logger.error(
                f"Error checking if month '{month_str}' is archived: {e}", exc_info=True
            )
            return False  # Assume not archived to attempt archiving and get another error if truly not accessible

    def archive_monthly_summary(self) -> dict | None:
        """
        Calculates and archives previous month's summary.
        Returns the summary data if a new archive is created, otherwise returns None.
        """
        logger.info("Initiating monthly summary archiving process...")
        try:
            # 1. Determine Month to Archive
            year, last_month, month_to_archive_str = self._get_previous_month_info()

            # 2. Check if Already Archived
            if self._is_month_archived(month_to_archive_str):
                logger.info(f"Summary for {month_to_archive_str} is already archived.")
                return None

            logger.info(
                f"Generating summary for {month_to_archive_str} to be archived..."
            )

            # 3. Load and Filter Expense Data for Previous Month
            df = self.expense_data_manager.load_expenses_dataframe()
            if df.empty:
                logger.info("No expense records found. Skipping monthly archive.")
                return None

            previous_month_df = df[
                (df["Date"].dt.year == year) & (df["Date"].dt.month == last_month)
            ].copy()  # Ensure we work on a copy

            if previous_month_df.empty:
                logger.info(
                    f"No expense records for {month_to_archive_str} found to archive."
                )
                return None

            # 4. Calculate Financial Metrics
            total_spent = previous_month_df["Expense"].sum()
            monthly_disposable_income = (
                self.expense_data_manager.get_monthly_disposable_income()
            )
            bonus_savings = monthly_disposable_income - total_spent

            # 5. Calculate Needs/Wants Spending (requires category data)
            category_types_records = self.sheets_service.get_all_records(
                CATEGORIES_WORKSHEET_NAME
            )
            _, _, needs_percent, wants_percent = (
                self.expense_data_manager.calculate_category_spending(
                    previous_month_df, category_types_records
                )
            )

            # 6. Prepare and Archive Data
            history_ws = self.sheets_service.get_worksheet(HISTORY_WORKSHEET_NAME)
            new_history_row = [
                month_to_archive_str,
                total_spent,
                bonus_savings,
                needs_percent,
                wants_percent,
            ]
            self.sheets_service.append_row(history_ws, new_history_row)
            logger.success(f"Successfully archived summary for {month_to_archive_str}.")

            # 7. Return Summary Data
            summary_data = {
                "month": month_to_archive_str,
                "total_spent": total_spent,
                "bonus_savings": bonus_savings,
                "needs_percent": needs_percent,
                "wants_percent": wants_percent,
            }
            return summary_data
        except Exception as e:
            logger.error(
                f"An error occurred during monthly archiving: {e}", exc_info=True
            )
            return None
