import datetime

from loguru import logger
import pandas as pd
from data_processing.expense_data import ExpenseDataManager

from config import *


class AnomalyDetector:
    """
    Analyzes historical spending to find and report on anomalous spending.
    """

    def __init__(self, expense_data_manager: ExpenseDataManager):
        self.expense_data_manager = expense_data_manager

    def check_for_spending_anomalies(self) -> list[str]:
        """
        Analyzes historical spending to find and report on anomalous spending this week.
        Returns a list of formatted messages for any anomalies found.
        """
        logger.info("Starting spending anomaly detection...")
        df = self.expense_data_manager.load_expenses_dataframe()
        if df.empty:
            logger.info("No expense data available for anomaly detection.")
            return []

        # Ensure we only consider expenses, not income
        expense_df = df[df["Expense"] > 0].copy()
        if expense_df.empty:
            logger.info("No expense transactions found for anomaly detection.")
            return []

        # --- 1. Calculate historical average weekly spend per category ---
        expense_df["year"] = expense_df["Date"].dt.isocalendar().year
        expense_df["week"] = expense_df["Date"].dt.isocalendar().week

        # Sum expenses by category, for each unique week
        weekly_spending = (
            expense_df.groupby(["year", "week", "Category"])["Expense"]
            .sum()
            .reset_index()
        )

        today = datetime.datetime.now()
        current_week_number = today.isocalendar().week
        current_year = today.isocalendar().year

        # Exclude the current week from the historical average calculation
        historical_weekly_spending = weekly_spending[
            ~(
                (weekly_spending["year"] == current_year)
                & (weekly_spending["week"] == current_week_number)
            )
        ]

        # Calculate the average and the number of data points (weeks) for each category
        category_stats = (
            historical_weekly_spending.groupby("Category")["Expense"]
            .agg(["mean", "count"])
            .rename(columns={"mean": "avg_spend", "count": "week_count"})
        )

        # --- 2. Get this week's spending per category ---
        this_week_df = weekly_spending[
            (weekly_spending["year"] == current_year)
            & (weekly_spending["week"] == current_week_number)
        ]

        # --- 3. Compare and find anomalies ---
        anomaly_messages = []
        for _, row in this_week_df.iterrows():
            category = row["Category"]
            current_spend = row["Expense"]

            # Check if we have enough historical data for this category
            if (
                category in category_stats.index
                and category_stats.loc[category]["week_count"] >= MINIMUM_WEEKS_OF_DATA
            ):
                average_spend = category_stats.loc[category]["avg_spend"]

                is_significant_spend = current_spend > MINIMUM_SPEND_FOR_ALERT
                is_anomalous = current_spend > (average_spend * ANOMALY_THRESHOLD)

                if is_significant_spend and is_anomalous:
                    logger.warning(
                        f"Anomaly detected in '{category}'! Current: {current_spend:.2f}, Average: {average_spend:.2f}"
                    )
                    message = (
                        f"📈 *Spending Alert*\n"
                        f"Heads up! Your spending in the *{category}* category this week is `{current_spend:,.2f} PLN`.\n"
                        f"This is significantly higher than your weekly average of `{average_spend:,.2f} PLN`."
                    )
                    anomaly_messages.append(message)
        logger.info(
            f"Anomaly detection complete. Found {len(anomaly_messages)} anomalies."
        )
        return anomaly_messages
