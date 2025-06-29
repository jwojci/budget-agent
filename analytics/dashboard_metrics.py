import datetime
import calendar

import pandas as pd
from loguru import logger
from services.google_sheets import GoogleSheetsService  # For fetching income

import config


class DashboardMetricsCalculator:
    """
    Calculates various financial metrics for the budget dashboard.
    """

    def __init__(self, sheets_service: GoogleSheetsService):
        self.sheets_service = sheets_service

    def calculate_all_metrics(
        self, df: pd.DataFrame, monthly_disposable_income: float
    ) -> dict:
        """
        Calculates all primary budget and spending metrics for the dashboard.
        Assumes df is already cleaned with 'Date' as datetime and 'Expense' as numeric.
        """
        if monthly_disposable_income == 0.0:
            logger.warning(
                "Monthly disposable income is 0. Cannot calculate budget metrics."
            )
            return {}  # Return an empty dict if income is not set

        today = datetime.datetime.now()
        day_of_month = today.day
        _, days_in_month = calendar.monthrange(today.year, today.month)
        days_remaining_in_month = days_in_month - day_of_month + 1

        daily_rate = monthly_disposable_income / days_in_month
        target_weekly_spend = daily_rate * 7  # Simplified weekly target

        month_to_date_expenses_df = df[df["Date"].dt.month == today.month].copy()
        month_to_date_total_spent = month_to_date_expenses_df["Expense"].sum()

        start_of_week = (today - datetime.timedelta(days=today.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        weekly_expenses_df = df[df["Date"] >= start_of_week].copy()
        weekly_total_spent = weekly_expenses_df["Expense"].sum()

        remaining_monthly_budget = monthly_disposable_income - month_to_date_total_spent
        safe_to_spend_today = (
            remaining_monthly_budget / days_remaining_in_month
            if days_remaining_in_month > 0
            else 0
        )

        remaining_weekly_target = target_weekly_spend - weekly_total_spent
        current_day_of_week_index = today.weekday()  # Monday is 0, Sunday is 6
        avg_daily_spending_this_week = (
            weekly_total_spent
            / (current_day_of_week_index + 1)  # Divide by days passed this week
            if (current_day_of_week_index + 1)
            > 0  # Avoid division by zero on Monday before any spending
            else 0
        )
        yesterdays_date = (today - datetime.timedelta(days=1)).date()
        yesterdays_total_spent = df[df["Date"].dt.date == yesterdays_date][
            "Expense"
        ].sum()

        budget_earned_so_far = daily_rate * day_of_month
        bonus_savings = budget_earned_so_far - month_to_date_total_spent

        return {
            "monthly_disposable_income": monthly_disposable_income,
            "target_weekly_spend": target_weekly_spend,
            "weekly_total_spent": weekly_total_spent,
            "remaining_weekly_target": remaining_weekly_target,
            "avg_daily_spending_this_week": avg_daily_spending_this_week,
            "yesterdays_total_spent": yesterdays_total_spent,
            "bonus_savings": bonus_savings,
            "safe_to_spend_today": safe_to_spend_today,
            "month_to_date_expenses_df": month_to_date_expenses_df,
            "weekly_expenses_df": weekly_expenses_df,
        }

    def prepare_summary_data(self, metrics: dict) -> list[list]:
        """Prepares the main summary table for the sheet."""
        if not metrics:
            return []
        return [
            ["Item", "Value"],
            ["Monthly Disposable Income", metrics["monthly_disposable_income"]],
            ["Target Weekly Budget", metrics["target_weekly_spend"]],
            ["-", "-"],
            ["Spent This Week", metrics["weekly_total_spent"]],
            ["Remaining This Week (Target)", metrics["remaining_weekly_target"]],
            [
                "Average Daily Spending (This Week)",
                metrics["avg_daily_spending_this_week"],
            ],
            ["Yesterday's Spending", metrics["yesterdays_total_spent"]],
            ["On-Pace Savings This Month", metrics["bonus_savings"]],
        ]

    def prepare_daily_breakdown_data(
        self, metrics: dict
    ) -> tuple[list[list], list[list]]:
        """Prepares the daily spending breakdown table."""
        if not metrics:
            return [], []
        daily_breakdown_header = [["Day", "Date", "Spent", "Safe to Spend Daily"]]
        daily_spending_rows = []
        days_of_week = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        today = datetime.datetime.now()
        start_of_week = (today - datetime.timedelta(days=today.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        for i in range(7):
            day = start_of_week + datetime.timedelta(days=i)
            spent_on_day = metrics["weekly_expenses_df"][
                metrics["weekly_expenses_df"]["Date"].dt.date == day.date()
            ]["Expense"].sum()
            safe_spend_display = (
                f"{metrics['safe_to_spend_today']:.2f}"
                if day.date() >= today.date()
                else "-"
            )
            daily_spending_rows.append(
                [
                    days_of_week[i],
                    day.strftime("%Y-%m-%d"),
                    spent_on_day,
                    safe_spend_display,
                ]
            )
        return daily_breakdown_header, daily_spending_rows

    def prepare_category_and_type_data(
        self, df_month_to_date: pd.DataFrame, category_types_records: list[dict]
    ) -> tuple[list[list], list[list]]:
        """Prepares category and Needs vs. Wants summary tables."""
        if df_month_to_date.empty:
            return [["Category", "Spent", "%"]], [["Needs vs. Wants", "Spent", "%"]]

        # First, ensure 'Type' column is correctly mapped for this month's data
        # The expense_data.py has the logic for category_to_type mapping
        # so we'll pass category_types_records here to remap if needed.
        category_to_type_map = {
            rec["Category"]: rec["Type"]
            for rec in category_types_records
            if rec.get("Type")
        }
        df_month_to_date_processed = df_month_to_date.copy()
        df_month_to_date_processed.to_csv("test.csv")
        df_month_to_date_processed["Type"] = (
            df_month_to_date_processed["Category"]
            .map(category_to_type_map)
            .fillna("Unclassified")
        )

        total_monthly_spent = df_month_to_date_processed["Expense"].sum()

        category_spending = (
            df_month_to_date_processed.groupby("Category")["Expense"]
            .sum()
            .sort_values(ascending=False)
        )
        category_data_for_sheet = [["Category", "Spent", "%"]]
        for category, spent in category_spending.items():
            percentage = (spent / total_monthly_spent) if total_monthly_spent > 0 else 0
            category_data_for_sheet.append([category, spent, percentage])

        needs_wants_spending = df_month_to_date_processed.groupby("Type")[
            "Expense"
        ].sum()
        needs_spent = needs_wants_spending.get("Need", 0)
        wants_spent = needs_wants_spending.get("Want", 0)
        needs_wants_data_for_sheet = [["Needs vs. Wants", "Spent", "%"]]
        total_needs_wants = needs_spent + wants_spent
        if total_needs_wants > 0:
            needs_wants_data_for_sheet.append(
                ["Needs", needs_spent, needs_spent / total_needs_wants]
            )
            needs_wants_data_for_sheet.append(
                ["Wants", wants_spent, wants_spent / total_needs_wants]
            )

        return category_data_for_sheet, needs_wants_data_for_sheet

    def prepare_top_merchants_data(self, df: pd.DataFrame) -> list[list]:
        """Calculates and prepares top merchants by spending data."""
        if df.empty:
            return [["Top Merchants by Spending", "Spent", "Visits"]]

        # Filter for actual expenses (Expense > 0) before grouping
        expenses_only_df = df[df["Expense"] > 0].copy()
        if expenses_only_df.empty:
            return [["Top Merchants by Spending", "Spent", "Visits"]]

        top_merchants_df = (
            expenses_only_df.groupby("Description")["Expense"]
            .agg(["sum", "count"])
            .nlargest(5, "sum")
            .reset_index()
        )
        top_merchants_df.columns = ["Merchant", "Spent", "Visits"]

        top_spending_data = [["Top Merchants by Spending", "Spent", "Visits"]]
        for _, row in top_merchants_df.iterrows():
            top_spending_data.append(
                [row["Merchant"], row["Spent"], int(row["Visits"])]
            )
        return top_spending_data
