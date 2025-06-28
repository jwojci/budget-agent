import gspread
from gspread_formatting import (
    CellFormat,
    get_conditional_format_rules,
    ConditionalFormatRule,
)
from loguru import logger


class GoogleSheetsService:
    """
    Provides an interface for interacting with Google Sheets using gspread.
    """

    def __init__(self, gspread_client: gspread.Client):
        self.gspread_client = gspread_client
        self.spreadsheet = None

    def open_spreadsheet(self, spreadsheet_name: str):
        """Opens the specified spreadsheet and stores it."""
        try:
            self.spreadsheet = self.gspread_client.open(spreadsheet_name)
            logger.info(f"Successfully opened spreadsheet: '{spreadsheet_name}'")
            return self.spreadsheet
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(
                f"Spreadsheet '{spreadsheet_name}' not found. Please ensure the name is correct and the bot has access."
            )
            raise
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while opening spreadsheet '{spreadsheet_name}': {e}",
                exc_info=True,
            )
            raise

    def get_worksheet(self, worksheet_name: str):
        """Gets a specific worksheet from the opened spreadsheet."""
        if not self.spreadsheet:
            logger.error(
                "No spreadsheet is currently open. Call open_spreadsheet first."
            )
            raise ValueError("No spreadsheet open")
        try:
            worksheet = self.spreadsheet.worksheet(worksheet_name)
            logger.debug(f"Successfully retrieved worksheet: '{worksheet_name}'.")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            logger.error(
                f"Worksheet '{worksheet_name}' not found in '{self.spreadsheet.title}'. Please ensure it exists."
            )
            raise
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while getting worksheet '{worksheet_name}': {e}",
                exc_info=True,
            )
            raise

    def get_all_records(self, worksheet_name: str) -> list[dict]:
        """Retrieves all records from a specified worksheet."""
        try:
            ws = self.get_worksheet(worksheet_name)
            records = ws.get_all_records()
            logger.debug(f"Retrieved {len(records)} records from '{worksheet_name}'.")
            return records
        except Exception as e:
            logger.error(f"Failed to get all records from '{worksheet_name}': {e}")
            return []

    def get_all_values(self, worksheet_name: str) -> list[list]:
        """Retrieves all values from a specified worksheet."""
        try:
            ws = self.get_worksheet(worksheet_name)
            values = ws.get_all_values()
            logger.debug(
                f"Retrieved {len(values)} rows of values from '{worksheet_name}'."
            )
            return values
        except Exception as e:
            logger.error(
                f"Failed to get all values from '{worksheet_name}': {e}", exc_info=True
            )
            return []

    def get_col_values(self, worksheet_name: str, col_index: int) -> list:
        """Retrieves all values from a specific column in a worksheet."""
        try:
            ws = self.get_worksheet(worksheet_name)
            values = ws.col_values(col_index)
            logger.debug(
                f"Retrieved {len(values)} values from column {col_index} of '{worksheet_name}'."
            )
            return values
        except Exception as e:
            logger.error(
                f"Failed to get column values from '{worksheet_name}', column {col_index}: {e}",
                exc_info=True,
            )
            return []  # Return empty list on failure

    def get_values(self, worksheet_name: str, range_name: str) -> list[list]:
        """Retrieves values from a specific range in a worksheet."""
        try:
            ws = self.get_worksheet(worksheet_name)
            values = ws.get_values(range_name)
            logger.debug(
                f"Retrieved values from range '{range_name}' in '{worksheet_name}'."
            )
            return values
        except Exception as e:
            logger.error(
                f"Failed to get values from range '{range_name}' in '{worksheet_name}': {e}",
                exc_info=True,
            )
            return []

    def get_acell_value(self, worksheet_name: str, cell_address: str):
        """Retrieves the value of a single cell."""
        try:
            ws = self.get_worksheet(worksheet_name)
            value = ws.acell(cell_address).value
            logger.debug(
                f"Retrieved value '{value}' from cell '{cell_address}' in '{worksheet_name}'."
            )
            return value
        except Exception as e:
            logger.error(
                f"Failed to get value from cell '{cell_address}' in '{worksheet_name}': {e}",
                exc_info=True,
            )
            return None

    def update_cells(
        self,
        worksheet,
        range_name: str,
        values: list,
        value_input_option: str = "USER_ENTERED",
    ):
        """Updates a range of cells in a worksheet."""
        try:
            worksheet.update(
                range_name=range_name,
                values=values,
                value_input_option=value_input_option,
            )
            logger.debug(f"Updated range '{range_name}' in '{worksheet.title}'.")
        except Exception as e:
            logger.error(
                f"Failed to update range '{range_name}' in '{worksheet.title}': {e}",
                exc_info=True,
            )
            raise

    def update_cell(self, worksheet, row: int, col: int, value):
        """Updates a single cell in a worksheet."""
        try:
            worksheet.update_cell(row, col, value)
            logger.debug(f"Updated cell ({row}, {col}) in '{worksheet.title}'.")
        except Exception as e:
            logger.error(
                f"Failed to update cell ({row}, {col}) in '{worksheet.title}': {e}",
                exc_info=True,
            )
            raise

    def append_row(
        self, worksheet, row_data: list, value_input_option: str = "USER_ENTERED"
    ):
        """Appends a new row to a worksheet."""
        try:
            worksheet.append_row(values=row_data, value_input_option=value_input_option)
            logger.debug(f"Appended row to '{worksheet.title}'.")
        except Exception as e:
            logger.error(
                f"Failed to append row to '{worksheet.title}': {e}", exc_info=True
            )
            raise

    def append_rows(
        self, worksheet, rows_data: list[list], value_input_option: str = "USER_ENTERED"
    ):
        """Appends multiple rows to a worksheet."""
        try:
            worksheet.append_rows(
                values=rows_data, value_input_option=value_input_option
            )
            logger.debug(f"Appended {len(rows_data)} rows to '{worksheet.title}'.")
        except Exception as e:
            logger.error(
                f"Failed to append {len(rows_data)} rows to '{worksheet.title}': {e}",
                exc_info=True,
            )
            raise

    def insert_rows(
        self,
        worksheet,
        rows_data: list[list],
        row_index: int = 1,
        value_input_option: str = "USER_ENTERED",
    ):
        """Inserts multiple rows into a worksheet at a specified index."""
        try:
            worksheet.insert_rows(
                values=rows_data, row=row_index, value_input_option=value_input_option
            )
            logger.debug(
                f"Inserted {len(rows_data)} rows at row index {row_index} in '{worksheet.title}'."
            )
        except Exception as e:
            logger.error(
                f"Failed to insert {len(rows_data)} rows at row index {row_index} in '{worksheet.title}': {e}",
                exc_info=True,
            )
            raise

    def clear_worksheet(self, worksheet):
        """Clears all content from a worksheet."""
        try:
            worksheet.clear()
            logger.debug(f"Cleared worksheet '{worksheet.title}'.")
        except Exception as e:
            logger.error(
                f"Failed to clear worksheet '{worksheet.title}': {e}", exc_info=True
            )
            raise

    def format_cell_range(self, worksheet, range_name: str, cell_format: CellFormat):
        """Applies formatting to a specific cell range."""
        try:
            gspread.worksheet.Worksheet.format(worksheet, range_name, cell_format)
            logger.debug(f"Applied format to '{range_name}' in '{worksheet.title}'.")
        except Exception as e:
            logger.error(
                f"Failed to apply format to '{range_name}' in '{worksheet.title}': {e}",
                exc_info=True,
            )
            # Do not re-raise as formatting issues often shouldn't stop main process

    def format_cell_ranges(
        self, worksheet, ranges_formats: list[tuple[str, CellFormat]]
    ):
        """Applies multiple formatting rules to ranges."""
        for range_name, cell_format in ranges_formats:
            self.format_cell_range(worksheet, range_name, cell_format)

    def update_conditional_formats(self, worksheet, rules: list[ConditionalFormatRule]):
        """Updates conditional formatting rules for a worksheet."""
        try:
            sheet_rules = get_conditional_format_rules(worksheet)
            sheet_rules.clear()
            sheet_rules.extend(rules)
            sheet_rules.save()
            logger.debug(
                f"Updated conditional formatting rules for '{worksheet.title}'."
            )
        except Exception as e:
            logger.error(
                f"Failed to update conditional formatting rules for '{worksheet.title}': {e}",
                exc_info=True,
            )

    def freeze_panes(self, worksheet, rows: int = 0, cols: int = 0):
        """Freezes rows and columns in a worksheet."""
        try:
            worksheet.freeze(rows=rows, cols=cols)
            logger.debug(
                f"Frozen {rows} rows and {cols} columns in '{worksheet.title}'."
            )
        except Exception as e:
            logger.error(
                f"Failed to freeze panes in '{worksheet.title}': {e}", exc_info=True
            )

    def batch_update_properties(self, worksheet_id: int, requests: list):
        """Performs a batch update for sheet properties (e.g., column widths)."""
        try:
            body = {"requests": requests}
            self.spreadsheet.batch_update(body)
            logger.debug(
                f"Performed batch update for sheet properties on sheet ID {worksheet_id}."
            )
        except Exception as e:
            logger.error(
                f"Failed to perform batch update for sheet properties on sheet ID {worksheet_id}: {e}",
                exc_info=True,
            )
            raise
