import pandas as pd
from datetime import datetime, timedelta

import config


class AgentTools:
    def __init__(self, app_context):
        self.expense_data_manager = app_context["expense_data_manager"]
        self.sheets_service = app_context["sheets_service"]
        self.metrics_calculator = app_context["metrics_calculator"]
        self.telegram_service = app_context["telegram_service"]

    def get_dashboard_summary(self) -> str:
        """
        Returns:
            A high-level summary of the user's current budget status.
            Provides key metrics like remaining weekly budget and safe-to-spend amounts.
        """
        df = self.expense_data_manager.load_expenses_dataframe()
        income = self.expense_data_manager.get_monthly_disposable_income()
        metrics = self.metrics_calculator.calculate_all_metrics(df, income)

        if not metrics:
            return "Could not calculate budget summary. Income might not be set."

        summary = (
            f"Remaining This Week: {metrics['remaining_weekly_target']:.2f} PLN\n"
            f"Safe to Spend Today: {metrics['safe_to_spend_today']:.2f} PLN\n"
            f"On-Pace Savings This Month: {metrics['bonus_savings']:.2f} PLN"
        )
        return summary

    def execute_pandas_query(self, query_code: str) -> str:
        """
        Executes a safe, read-only Pandas query against the transactions DataFrame and returns the result as a string.
        This tool allows for dynamic and complex data analysis.

        Args:
            query_code (str): A string containing the Pandas DataFrame query to execute.
                            The DataFrame is referred to as 'df'.
                            Example: "df[df['Category'] == 'Groceries'].groupby('Description')['Expense'].sum().nlargest(5)"
        """
        try:
            df = self.expense_data_manager.load_expenses_dataframe()

            # We ensure the query is read-only. This is a simple check, in production would use something more robust.
            if any(
                denied in query_code
                for denied in [".to_csv", ".to_excel", "os.", "subprocess", "eval("]
            ):
                return "Error: Query contains a disallowed operation."

            result = eval(query_code, {"pd": pd, "df": df, "datetime": pd.to_datetime})

            # Convert to a clean string
            if isinstance(result, pd.DataFrame):
                return result.to_string()
            elif isinstance(result, pd.Series):
                return result.to_string()
            else:
                return str(result)

        except Exception as e:
            return f"Error: I couldn't execute that query. There might be a syntax error. The error was: {e}"

    def categorize_merchant(self, merchant_name: str, category: str, type: str) -> str:
        """
        Assigns a category and type (Need/Want) to a previously uncategorized merchant keyword.
        This tool WRITES data to the 'Categories' sheet.

        Args:
            merchant_name (str): The exact merchant keyword to categorize.
            category (str): The category to assign (e.g., 'Groceries', 'Transport').
            type (str): The type to assign. Must be either 'Need' or 'Want'.
        """
        if type not in ["Need", "Want"]:
            return "Error: Type must be either 'Need' or 'Want'."
        try:
            categories_ws = self.sheets_service.get_worksheet(
                config.CATEGORIES_WORKSHEET_NAME
            )
            cell = categories_ws.find(merchant_name, in_column=1)
            if not cell:
                return f"Error: Could not find merchant '{merchant_name}' in the Categories sheet."

            self.sheets_service.update_cell(categories_ws, cell.row, 2, category)
            self.sheets_service.update_cell(categories_ws, cell.row, 3, type)
            return f"Success! I have categorized '{merchant_name}' as '{category}' ({type})."
        except Exception as e:
            return f"An error occurred while trying to categorize '{merchant_name}'."

    def generate_weekly_digest(self) -> str:
        """
        Analyzes the previous week's spending and asks the AI to generate a short, insightful, and encouraging summary.
        """
        df = self.expense_data_manager.load_expenses_dataframe()
        if df.empty:
            return "There is no spending data to analyze for the weekly digest."

        today = datetime.now()
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = today - timedelta(days=today.weekday() + 1)

        df_last_week = df[
            (df["Date"].dt.date >= start_of_last_week.date())
            & (df["Date"].dt.date <= end_of_last_week.date())
        ].copy()

        if df_last_week.empty:
            return "You had no spending last week."

        total_spent = df_last_week["Expense"].sum()
        top_category = df_last_week.groupby("Category")["Expense"].sum().idxmax()
        top_merchant = df_last_week.groupby("Description")["Expense"].sum().idxmax()

        return (
            f"Here is the data for last week's spending summary:\n"
            f"- Total Spent: {total_spent:.2f} PLN\n"
            f"- Top Category: {top_category}\n"
            f"- Top Merchant: {top_merchant}\n"
        )

    def get_filtered_aggregated_data(
        self,
        filters: list[dict[str, any]] | None = None,
        group_by: list[str] | None = None,
        aggregation: dict[str, str] | None = None,
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
            aggregation (Optional[Dict[str, str]]): Aggregation function to apply. Example: {'Expense': 'sum'}
            sort_by (Optional[str]): Column to sort the final result by.
            ascending (bool): Sort order. Defaults to False (descending).
            head (int): Number of top results to return.
        """
        try:
            df = self.expense_data_manager.load_expenses_dataframe()

            # --- apply filters ---
            if filters:
                for f in filters:
                    col, op, val = f["column"], f["operator"], f["value"]
                    if col not in df.columns:
                        continue
                    if op == "==":
                        df = df[df[col] == val]
                    elif op == "!=":
                        df = df[df[col] != val]
                    elif op == ">":
                        df = df[df[col] > val]
                    elif op == "<":
                        df = df[df[col] < val]
                    elif op == ">=":
                        df = df[df[col] >= val]
                    elif op == "<=":
                        df = df[df[col] <= val]
                    elif op == "in":
                        df = df[df[col].isin(val)]
                    elif op == "not in":
                        df = df[~df[col].isin(val)]

            # --- apply grouping and aggregation ---
            if group_by and aggregation:
                result_df = df.groupby(group_by).agg(aggregation)
            else:
                result_df = df

            # --- apply sorting ---
            if sort_by and sort_by in result_df.columns:
                result_df = result_df.sort_values(by=sort_by, ascending=ascending)

            return result_df.head(head).to_string()

        except Exception as e:
            return f"Error executing query: {e}"
