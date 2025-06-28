import re

import pandas as pd
from loguru import logger

from services.google_sheets import GoogleSheetsService
from config import *


class ExpenseDataManager:
    """
    Manages loading, cleaning, and preparing expense data from Google Sheets.
    Also handles category and type mapping.
    """

    def __init__(self, sheets_service: GoogleSheetsService):
        self.sheets_service = sheets_service

    def load_expenses_dataframe(self) -> pd.DataFrame:
        """
        Loads all records from the expenses worksheet into a Pandas DataFrame,
        ensuring 'Expense' is numeric and 'Date' is a timezone-naive datetime object.
        """
        try:
            all_records = self.sheets_service.get_all_records(EXPENSES_WORKSHEET_NAME)

            if not all_records:
                logger.warning(
                    f"Expenses worksheet '{EXPENSES_WORKSHEET_NAME}' is empty. Returning empty DataFrame."
                )
                return pd.DataFrame(columns=EXPECTED_EXPENSE_HEADER)

            df = pd.DataFrame(all_records)

            # Ensure required columns exist
            if not all(col in df.columns for col in REQUIRED_DF_COLUMNS):
                missing_cols = [
                    col for col in REQUIRED_DF_COLUMNS if col not in df.columns
                ]
                logger.error(
                    f"Expenses worksheet is missing one or more required columns: {missing_cols}. Current columns: {df.columns.tolist()}"
                )
                return pd.DataFrame(columns=EXPECTED_EXPENSE_HEADER)

            df["Expense"] = pd.to_numeric(df["Expense"], errors="coerce").fillna(0)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.tz_localize(
                None
            )

            logger.info(
                f"Successfully loaded {len(df)} records from '{EXPENSES_WORKSHEET_NAME}'."
            )
            return df
        except Exception as e:
            logger.error(
                f"Error loading expenses DataFrame from '{EXPENSES_WORKSHEET_NAME}': {e}",
                exc_info=True,
            )
            return pd.DataFrame(columns=EXPECTED_EXPENSE_HEADER)

    def get_category_data(self) -> tuple[list[dict], list[str], any]:
        """
        Fetches all categorization data from the 'Categories' worksheet.
        Returns uncategorized keywords, existing categories, and the worksheet object.
        """
        try:
            categories_ws = self.sheets_service.get_worksheet(CATEGORIES_WORKSHEET_NAME)
            all_category_data = self.sheets_service.get_all_records(
                CATEGORIES_WORKSHEET_NAME
            )

            uncategorized = [
                row
                for row in all_category_data
                if not row.get("Category") and row.get("Keyword")
            ]
            existing_categories = sorted(
                list(
                    set(
                        row["Category"]
                        for row in all_category_data
                        if row.get("Category")
                    )
                )
            )
            logger.info(
                f"Loaded {len(all_category_data)} category entries. Found {len(uncategorized)} uncategorized keywords."
            )
            return uncategorized, existing_categories, categories_ws
        except Exception as e:
            logger.error(
                f"Error getting category data from '{CATEGORIES_WORKSHEET_NAME}': {e}",
                exc_info=True,
            )
            return [], [], None

    def get_monthly_disposable_income(self) -> float:
        """Retrieves and cleans the monthly disposable income from the budget worksheet."""
        try:
            spreadsheet = self.sheets_service
            budget_ws = self.sheets_service.get_worksheet(BUDGET_WORKSHEET_NAME)
            monthly_income_str = self.sheets_service.get_acell_value(
                budget_ws.title, "B2"
            )  # Pass worksheet title and cell
            if not monthly_income_str:
                logger.error("Monthly Income cell (B2) is empty. Please enter a value.")
                return 0.0

            # Clean the string for parsing
            cleaned_income_str = re.sub(r"[^\d,.]", "", str(monthly_income_str))
            if "," in cleaned_income_str and "." in cleaned_income_str:
                # If both exist, assume comma is thousands separator (e.g., 1,000.00)
                cleaned_income_str = cleaned_income_str.replace(",", "")
            else:
                # Otherwise, comma is decimal separator (e.g., 123,45)
                cleaned_income_str = cleaned_income_str.replace(",", ".")

            return float(cleaned_income_str)
        except Exception as e:
            logger.error(
                f"Could not read or parse monthly income from '{BUDGET_WORKSHEET_NAME}' cell B2: {e}",
                exc_info=True,
            )
            return 0.0

    def calculate_category_spending(
        self, df: pd.DataFrame, category_types_records: list[dict]
    ) -> tuple[float, float, float, float]:
        """Calculates spending by category type (Need/Want)."""
        category_to_type_map = {
            rec["Category"]: rec["Type"]
            for rec in category_types_records
            if rec.get("Type")
        }

        # Use .copy() to prevent SettingWithCopyWarning
        df_processed = df.copy()
        df_processed["Type"] = (
            df_processed["Category"].map(category_to_type_map).fillna("Unclassified")
        )
        needs_wants_spending = df_processed.groupby("Type")["Expense"].sum()

        needs_spent = needs_wants_spending.get("Need", 0)
        wants_spent = needs_wants_spending.get("Want", 0)
        total_needs_wants = needs_spent + wants_spent

        needs_percent = needs_spent / total_needs_wants if total_needs_wants > 0 else 0
        wants_percent = wants_spent / total_needs_wants if total_needs_wants > 0 else 0

        return needs_spent, wants_spent, needs_percent, wants_percent
