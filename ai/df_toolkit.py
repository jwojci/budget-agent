import pandas as pd
from loguru import logger
from langchain_core.tools import tool
from data_processing.expense_data import ExpenseDataManager


class DataFrameToolkit:
    """
    A stateful toolkit for analyzing a pandas dataframe.
    An instance of this class acts as a workspace for the agent,
    holding a dataframe in memory that can be modified.
    """

    def __init__(self, expense_data_manager: ExpenseDataManager):
        self.expense_data_manager = expense_data_manager
        self._original_df: pd.DataFrame | None = None
        self._active_df: pd.DataFrame | None = None

    @tool
    def load_data(self) -> str:
        """
        Loads or reloads the full, original expense DataFrame into the active workspace.
        This should be the FIRST step in any analysis. Wipes any previous filtering or sorting.
        """
        try:
            self._original_df = self.expense_data_manager.load_expenses_dataframe()
            self._active_df = self._original_df.copy()
            return f"Successfully loaded {len(self._active_df)} transactions into the workspace."
        except Exception as e:
            return f"Error loading data: {e}"

    @tool
    def filter_data(self, column: str, operator: str, value: any) -> str:
        """
        Filters the active DataFrame based on a condition. Modifies the DataFrame in the workspace.
        - Supported operators: '==', '!=', '>', '<', '>=', '<=', 'isin', 'notin'.
        - For dates, use 'YYYY-MM-DD' format for the 'value'.
        """
        if self._active_df is None:
            return "Error: Data not loaded. Please use `load_data` first."

        try:
            # Make a copy to avoid SettingWithCopyWarning
            df = self._active_df.copy()

            # Special handling for date comparisons
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                value = pd.to_datetime(value)

            if operator == "==":
                df = df[df[column] == value]
            elif operator == "!=":
                df = df[df[column] != value]
            elif operator == ">":
                df = df[df[column] > value]
            elif operator == "<":
                df = df[df[column] < value]
            elif operator == ">=":
                df = df[df[column] >= value]
            elif operator == "<=":
                df = df[df[column] <= value]
            elif operator == "isin":
                df = df[df[column].isin(value)]
            elif operator == "notin":
                df = df[~df[column].isin(value)]
            else:
                return f"Error: Unsupported operator '{operator}'."

            self._active_df = df
            return f"Filter applied. The active DataFrame now has {len(self._active_df)} rows."
        except Exception as e:
            return f"Error applying filter: {e}"

    @tool
    def sort_data(self, by: str | list[str], ascending: bool = True) -> str:
        """
        Sorts the active DataFrame by one or more columns. Modifies the DataFrame in the workspace.
        """
        if self._active_df is None:
            return "Error: Data not loaded. Please use `load_data` first."
        try:
            self._active_df.sort_values(by=by, ascending=ascending, inplace=True)
            return f"Data sorted by '{by}'."
        except Exception as e:
            return f"Error sorting data: {e}"

    @tool
    def group_and_aggregate(
        self, group_by: list[str], aggregations: dict[str, str]
    ) -> str:
        """
        Groups the active DataFrame and calculates aggregations (e.g., sum, mean, count).
        This replaces the active DataFrame with the new, grouped summary DataFrame.
        Example: group_by=['Category'], aggregations={'Expense': 'sum'}
        """
        if self._active_df is None:
            return "Error: Data not loaded. Please use `load_data` first."
        try:
            self._active_df = (
                self._active_df.groupby(group_by).agg(aggregations).reset_index()
            )
            return f"Data grouped by '{group_by}'. The active DataFrame is now a summary table with {len(self._active_df)} rows."
        except Exception as e:
            return f"Error during aggregation: {e}"

    @tool
    def show_data(self, head: int = 10) -> str:
        """
        Displays the first few rows of the CURRENT active DataFrame in the workspace.
        Use this as the LAST step to see the result of your analysis.
        """
        if self._active_df is None:
            return "Error: Data not loaded. Please use `load_data` first."

        return self._active_df.head(head).to_string()
