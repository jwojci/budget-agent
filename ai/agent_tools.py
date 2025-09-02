import operator as op
from datetime import datetime, timedelta

import pandas as pd
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from data_processing.expense_data import ExpenseDataManager
from services.google_sheets import GoogleSheetsService
from analytics.dashboard_metrics import DashboardMetricsCalculator


class Filter(BaseModel):
    """Model for filtering DataFrame."""

    column: str = Field(..., description="Column to filter on")
    operator: str = Field(
        ..., description="Comparison operator (e.g., '==', '>', '<=', 'in')"
    )
    value: str | int | float = Field(..., description="Value to compare against")


class FilteredAggregatedDataInput(BaseModel):
    """Input schema for get_filtered_aggregated_data tool."""

    filters: list[Filter] | None = Field(None, description="Filters to apply")
    group_by: list[str] | None = Field(None, description="Columns to group by")
    aggregations: dict[str, str] | None = Field(
        None, description="Aggregation functions (e.g., {'Expense': 'sum'})"
    )
    sort_by: str | None = Field(None, description="Column to sort by")
    ascending: bool = Field(False, description="Sort order (False for descending)")
    head: int = Field(10, description="Number of rows to return")


def create_agent_tools(app_context):
    """Creates and configures agent tools."""
    expense_data: ExpenseDataManager | None = app_context["expense_data_manager"]
    sheets: GoogleSheetsService | None = app_context["sheets_service"]
    metrics: DashboardMetricsCalculator | None = app_context["metrics_calculator"]

    @tool
    def get_dashboard_summary() -> str:
        """Returns a summary of budget status."""
        try:
            df = expense_data.load_expenses_dataframe()
            metrics_data = metrics.calculate_all_metrics(df)
            print(type(metrics), type(expense_data))
            if not metrics_data:
                return "Could not calculate budget summary."
            return (
                f"Weekly Remaining: {metrics_data['remaining_weekly_target']:.2f} PLN\n"
                f"Daily Safe to Spend: {metrics_data['safe_to_spend_today']:.2f} PLN\n"
                f"Monthly Savings: {metrics_data['bonus_savings']:.2f} PLN"
            )
        except Exception as e:
            print(f"Error during getting dashboard summary: {e}")

    @tool
    def categorize_merchant(merchant_name: str, category: str, type: str) -> str:
        """Assigns category and type (Need/Want) to a merchant."""
        if type not in ["Need", "Want"]:
            return "Error: Type must be 'Need' or 'Want'."

        try:
            ws = sheets.get_worksheet("Categories")
            cell = ws.find(merchant_name, in_column=1)
            if not cell:
                return f"Error: Merchant '{merchant_name}' not found."

            sheets.update_cell(ws, cell.row, 2, category)
            sheets.update_cell(ws, cell.row, 3, type)
            return f"Categorized '{merchant_name}' as '{category}' ({type})."
        except Exception as e:
            return f"Error categorizing '{merchant_name}': {e}"

    @tool
    def get_weekly_spending_data() -> str:
        """Summarizes last week's spending."""
        df = expense_data.load_expenses_dataframe()
        if df.empty:
            return "No spending data available."

        today = datetime.now()
        start = today - timedelta(days=today.weekday() + 7)
        end = today - timedelta(days=today.weekday() + 1)

        df_week = df[
            (df["Date"].dt.date >= start.date()) & (df["Date"].dt.date <= end.date())
        ]
        if df_week.empty:
            return "No spending last week."

        total = df_week["Expense"].sum()
        top_cat = df_week.groupby("Category")["Expense"].sum().idxmax()
        top_merchant = df_week.groupby("Description")["Expense"].sum().idxmax()

        return (
            f"Last Week's Spending:\n"
            f"- Total: {total:.2f} PLN\n"
            f"- Top Category: {top_cat}\n"
            f"- Top Merchant: {top_merchant}"
        )

    @tool
    def get_filtered_aggregated_data(
        filters: list[Filter] | None = None,
        group_by: list[str] | None = None,
        aggregations: dict[str, str] | None = None,
        sort_by: str | None = None,
        ascending: bool = False,
        head: int = 10,
    ) -> str:
        """
        Safely queries the transaction DataFrame.
        This tool allows for filtering, grouping, and aggregating data.

        Args:
            filters (Optional[List[Dict]]): List of filters. Each dict has 'column', 'operator', 'value'.
                Example: [{'column': 'Category', 'operator': '==', 'value': 'Groceries'}]
                Supported operators: '==', '!=', '>', '<', '>=', '<=', 'in', 'not in'.
            group_by (Optional[List[str]]): Column(s) to group by. Example: ['Category', 'Description']
            aggregations (Optional[Dict[str, str]]): Aggregation functions to apply. Example: {{'Expense': 'sum'}}
            sort_by (Optional[str]): Column to sort the final result by.
            ascending (bool): Sort order. Defaults to False (descending).
            head (int): Number of top results to return.

        Example usage for "total expense per category":
        group_by=['Category'], aggregations={{'Expense': 'sum'}}
        """

        ops = {
            "==": op.eq,
            "!=": op.ne,
            ">": op.gt,
            "<": op.lt,
            ">=": op.ge,
            "<=": op.le,
            "in": lambda s, v: s.isin(v),
            "not in": lambda s, v: ~s.isin(v),
        }

        try:
            df = expense_data.load_expenses_dataframe()

            if filters:
                for f in filters:
                    if f.column in df.columns and f.operator in ops:
                        df = df[ops[f.operator](df[f.column], f.value)]

            if group_by and aggregations:
                df = df.groupby(group_by).agg(aggregations)

            if sort_by and sort_by in df.columns:
                df = df.sort_values(by=sort_by, ascending=ascending)

            return df.head(head).to_string()
        except Exception as e:
            return f"Query error: {e}"

    @tool
    def calculate_average_weekly_spending(start_date: str, end_date: str) -> str:
        """Calculates average weekly spending in a date range."""
        try:
            df = expense_data.load_expenses_dataframe()
            if df.empty:
                return "No spending data available."

            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            df_range = df[
                (df["Date"] >= start) & (df["Date"] <= end) & (df["Expense"] > 0)
            ]

            if df_range.empty:
                return f"No spending between {start_date} and {end_date}."

            weeks = max((end - start).days / 7, 1)
            total = df_range["Expense"].sum()
            avg = total / weeks

            return (
                f"From {start_date} to {end_date}:\n"
                f"Total spent: {total:,.2f} PLN\n"
                f"Average weekly: {avg:,.2f} PLN"
            )
        except Exception as e:
            return f"Error calculating average: {e}"

    @tool
    def get_monthly_spending_summary(year: int, month: int) -> str:
        """
        Provides a summary of spending for a specific month and year.
        Returns total spending, top category, and top 5 merchants for that month.
        """
        try:
            df = expense_data.load_expenses_dataframe()
            if df.empty:
                return "No spending data available."

            df_month = df[
                (df["Date"].dt.year == year) & (df["Date"].dt.month == month)
            ].copy()

            if df_month.empty:
                return f"No spending data found for {year}-{month:02d}."
            # Only consider expenses, not income
            df_month_expenses = df_month[df_month["Expense"] > 0]
            if df_month_expenses.empty:
                return f"No expenses (only income or transfers) recorded for {year}-{month:02d}."

            total_spent = df_month_expenses["Expense"].sum()
            top_category = (
                df_month_expenses.groupby("Category")["Expense"].sum().idxmax()
            )

            top_merchants = (
                df_month_expenses.groupby("Description")["Expense"]
                .sum()
                .nlargest(5)
                .reset_index()
            )
            top_merchants_str = "\n".join(
                [
                    f"-{row['Description']}: {row['Expense']:.2f} PLN"
                    for _, row in top_merchants.iterrows()
                ]
            )

            return (
                f"Spending Summary for {year}-{month:02d}:\n"
                f"***Total Spent***: {total_spent:.2f} PLN\n"
                f"***Top Category***: {top_category}\n\n"
                f"***Top 5 Merchants***:\n{top_merchants_str}"
            )
        except Exception as e:
            return f"Error generating monthly summary: {e}"

    return [
        get_dashboard_summary,
        categorize_merchant,
        get_weekly_spending_data,
        get_filtered_aggregated_data,
        calculate_average_weekly_spending,
        get_monthly_spending_summary,
    ]
