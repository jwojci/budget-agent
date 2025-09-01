import re
import pandas as pd
from loguru import logger
from services.google_sheets import GoogleSheetsService
import config


class ExpenseDataManager:
    """Manages expense data loading, cleaning, and categorization from Google Sheets."""

    def __init__(self, sheets_service: GoogleSheetsService):
        self.sheets_service = sheets_service

    def load_expenses_dataframe(self) -> pd.DataFrame:
        """Loads expenses from worksheet into a DataFrame with numeric 'Expense' and datetime 'Date'."""
        try:
            records = self.sheets_service.get_all_records(config.WORKSHEETS["expenses"])
            if not records:
                logger.warning(f"'{config.WORKSHEETS['expenses']}' is empty.")
                return pd.DataFrame(columns=config.EXPENSE_HEADER)

            df = pd.DataFrame(records)
            if not all(col in df.columns for col in config.DF_COLUMNS):
                logger.error(
                    f"Missing required columns: {[col for col in config.DF_COLUMNS if col not in df.columns]}"
                )
                return pd.DataFrame(columns=config.EXPENSE_HEADER)

            df["Expense"] = pd.to_numeric(df["Expense"], errors="coerce").fillna(0)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.tz_localize(
                None
            )

            logger.info(f"Loaded {len(df)} expense records.")
            return df

        except Exception as e:
            logger.error(
                f"Failed to load expenses from '{config.WORKSHEETS['expenses']}': {e}"
            )
            return pd.DataFrame(columns=config.EXPENSE_HEADER)

    def get_category_data(self) -> tuple[list[dict], list[str], any]:
        """Fetches uncategorized keywords, existing categories, and Categories worksheet."""
        try:
            categories_ws = self.sheets_service.get_worksheet(
                config.WORKSHEETS["categories"]
            )
            records = self.sheets_service.get_all_records(
                config.WORKSHEETS["categories"]
            )

            uncategorized = [
                row for row in records if not row.get("Category") and row.get("Keyword")
            ]
            existing_categories = sorted(
                set(row["Category"] for row in records if row.get("Category"))
            )

            logger.info(
                f"Loaded {len(records)} category entries, {len(uncategorized)} uncategorized."
            )
            return uncategorized, existing_categories, categories_ws

        except Exception as e:
            logger.error(
                f"Failed to load category data from '{config.WORKSHEETS['categories']}': {e}"
            )
            return [], [], None

    def get_monthly_disposable_income(self) -> float:
        """Retrieves monthly disposable income from the budget worksheet."""
        try:
            value_range = self.sheets_service.get_values(
                config.WORKSHEETS["budget"], config.NAMED_RANGES["monthly_income"]
            )

            if not value_range or not value_range[0] or not value_range[0][0]:
                logger.error(
                    f"Named range '{config.NAMED_RANGES['monthly_income']}' is empty."
                )
                return 0.0

            income_str = re.sub(r"[^\d,.]", "", str(value_range[0][0]))
            income_str = income_str.replace(",", "" if "." in income_str else ".")

            return float(income_str)

        except Exception as e:
            logger.error(
                f"Failed to parse monthly income from '{config.NAMED_RANGES['monthly_income']}': {e}"
            )
            return 0.0

    def calculate_category_spending(
        self, df: pd.DataFrame, category_types_records: list[dict]
    ) -> tuple[float, float, float, float]:
        """Calculates Need/Want spending and percentages."""
        category_to_type = {
            rec["Category"]: rec["Type"]
            for rec in category_types_records
            if rec.get("Type")
        }
        df = df.copy()
        df["Type"] = df["Category"].map(category_to_type).fillna("Unclassified")

        spending = df.groupby("Type")["Expense"].sum()
        needs_spent = spending.get("Need", 0)
        wants_spent = spending.get("Want", 0)
        total = needs_spent + wants_spent

        needs_percent = needs_spent / total if total > 0 else 0
        wants_percent = wants_spent / total if total > 0 else 0

        return needs_spent, wants_spent, needs_percent, wants_percent
