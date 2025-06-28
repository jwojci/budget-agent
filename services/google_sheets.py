import gspread
from gspread_formatting import (
    CellFormat,
    GridRange,
    NumberFormat,
    TextFormat,
    Color,
    get_conditional_format_rules,
    ConditionalFormatRule,
    format_cell_range as gspread_format_cell_range,
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
            gspread_format_cell_range(worksheet, range_name, cell_format)
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

    def format_dashboard_sheet(self, budget_ws, weekly_budget):
        """Applies formatting to the entire hybrid budget worksheet."""
        bold_format = CellFormat(textFormat=TextFormat(bold=True))
        currency_format = CellFormat(
            numberFormat=NumberFormat(type="NUMBER", pattern='#,##0.00 "PLN"')
        )
        percent_format = CellFormat(
            numberFormat=NumberFormat(type="NUMBER", pattern="0.00%")
        )
        integer_format = CellFormat(
            numberFormat=NumberFormat(type="NUMBER", pattern="0")
        )
        light_gray_background = CellFormat(backgroundColor=Color(0.9, 0.9, 0.9))
        self.format_cell_range(budget_ws, "A1:A9", bold_format)
        self.format_cell_ranges(
            budget_ws, [("B2:B3", currency_format), ("B5:B9", currency_format)]
        )
        self.format_cell_range(budget_ws, "A10:D10", bold_format)
        self.format_cell_range(
            budget_ws, "A10:D10", CellFormat(backgroundColor=Color(0.8, 0.8, 0.8))
        )
        self.format_cell_ranges(budget_ws, [("C11:D17", currency_format)])
        for i in range(11, 18, 2):
            self.format_cell_range(budget_ws, f"A{i}:D{i}", light_gray_background)

        # Right-Hand Side Tables Formatting - Retrieve values once to find table ranges dynamically
        all_rh_values = budget_ws.get_values("E:E")

        for i, row in enumerate(all_rh_values):
            if not row:
                continue
            header_text = row[0]
            start_row = i + 1

            if "Category" in header_text:
                end_row = start_row
                for j in range(start_row, len(all_rh_values)):
                    if not all_rh_values[j]:
                        break
                    end_row = j + 1
                self.format_cell_range(
                    budget_ws, f"E{start_row}:G{start_row}", bold_format
                )
                self.format_cell_range(
                    budget_ws,
                    f"E{start_row}:G{start_row}",
                    CellFormat(backgroundColor=Color(0.8, 0.8, 0.8)),
                )
                if end_row > start_row:
                    self.format_cell_range(
                        budget_ws, f"F{start_row+1}:F{end_row}", currency_format
                    )
                    self.format_cell_range(
                        budget_ws, f"G{start_row+1}:G{end_row}", percent_format
                    )

            elif "Needs vs. Wants" in header_text:
                self.format_cell_range(
                    budget_ws, f"E{start_row}:G{start_row}", bold_format
                )
                self.format_cell_range(
                    budget_ws,
                    f"E{start_row}:G{start_row}",
                    CellFormat(backgroundColor=Color(0.8, 0.8, 0.8)),
                )
                self.format_cell_range(
                    budget_ws, f"F{start_row+1}:F{start_row+2}", currency_format
                )
                self.format_cell_range(
                    budget_ws, f"G{start_row+1}:G{start_row+2}", percent_format
                )

            elif "Top Merchants by Spending" in header_text:
                end_row = start_row + 5
                self.format_cell_range(
                    budget_ws, f"E{start_row}:G{start_row}", bold_format
                )
                self.format_cell_range(
                    budget_ws,
                    f"E{start_row}:G{start_row}",
                    CellFormat(backgroundColor=Color(0.8, 0.8, 0.8)),
                )
                if end_row > start_row:
                    self.format_cell_range(
                        budget_ws, f"F{start_row+1}:F{end_row}", currency_format
                    )
                    self.format_cell_range(
                        budget_ws, f"G{start_row+1}:G{end_row}", integer_format
                    )

        # Conditional Formatting Rules
        b6_range = GridRange.from_a1_range("B6", budget_ws)
        bonus_savings_range = GridRange.from_a1_range("B9", budget_ws)

        # rules = [
        #     ConditionalFormatRule(
        #         ranges=[b6_range],
        #         booleanRule=BooleanRule(
        #             "NUMBER_LESS",
        #             [str(weekly_budget * 0.1)],
        #         ),
        #     ),
        #     ConditionalFormatRule(
        #         ranges=[b6_range],
        #         booleanRule=BooleanRule(
        #             "NUMBER_BETWEEN",
        #             [str(weekly_budget * 0.1), str(weekly_budget * 0.5)],
        #         ),
        #     ),
        #     ConditionalFormatRule(
        #         ranges=[b6_range],
        #         booleanRule=BooleanRule(
        #             "NUMBER_GREATER",
        #             [str(weekly_budget * 0.5)],
        #         ),
        #     ),
        #     ConditionalFormatRule(
        #         ranges=[bonus_savings_range],
        #         booleanRule=BooleanRule(
        #             "NUMBER_GREATER_THAN_EQ",
        #             ["0"],
        #         ),
        #     ),
        #     ConditionalFormatRule(
        #         ranges=[bonus_savings_range],
        #         booleanRule=BooleanRule(
        #             "NUMBER_LESS",
        #             ["0"],
        #         ),
        #     ),
        # ]
        # self.update_conditional_formats(budget_ws, rules)
        # Column Widths and Freeze Panes
        self.freeze_panes(budget_ws, rows=10, cols=1)

        column_resize_requests = [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": budget_ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 250},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": budget_ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "properties": {"pixelSize": 150},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": budget_ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 2,
                        "endIndex": 4,
                    },
                    "properties": {"pixelSize": 120},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": budget_ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 4,
                        "endIndex": 5,
                    },
                    "properties": {"pixelSize": 220},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": budget_ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 5,
                        "endIndex": 6,
                    },
                    "properties": {"pixelSize": 120},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": budget_ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 6,
                        "endIndex": 7,
                    },
                    "properties": {"pixelSize": 80},
                    "fields": "pixelSize",
                }
            },
        ]

        self.batch_update_properties(budget_ws.id, column_resize_requests)

        logger.info("Applied all formatting to the enhanced dashboard.")
