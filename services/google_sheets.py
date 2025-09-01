"""
Google Sheets service module for interacting with spreadsheets using gspread.

Provides methods for accessing, updating, and formatting Google Sheets.
"""

from loguru import logger
import gspread
from gspread_formatting import (
    CellFormat,
    GridRange,
    NumberFormat,
    TextFormat,
    BooleanRule,
    BooleanCondition,
    Color,
    get_conditional_format_rules,
    ConditionalFormatRule,
    format_cell_range as gspread_format_cell_range,
)


class GoogleSheetsService:
    """Interface for interacting with Google Sheets using gspread."""

    def __init__(self, gspread_client: gspread.Client):
        """Initialize with an authenticated gspread client."""
        self.gspread_client = gspread_client
        self.spreadsheet = None

    def _handle_exception(self, action: str, target: str, e: Exception):
        """Centralized exception handling for logging and raising errors."""
        logger.error(f"Failed to {action} '{target}': {e}")
        raise

    def open_spreadsheet(self, spreadsheet_name: str) -> gspread.Spreadsheet:
        """Open and return a spreadsheet by name."""
        try:
            self.spreadsheet = self.gspread_client.open(spreadsheet_name)
            logger.info(f"Opened spreadsheet '{spreadsheet_name}'")
            return self.spreadsheet
        except gspread.exceptions.SpreadsheetNotFound:
            self._handle_exception(
                "open spreadsheet", spreadsheet_name, Exception("Spreadsheet not found")
            )
        except Exception as e:
            self._handle_exception("open spreadsheet", spreadsheet_name, e)

    def get_worksheet(self, worksheet_name: str) -> gspread.Worksheet:
        """Return a worksheet from the opened spreadsheet."""
        if not self.spreadsheet:
            self._handle_exception(
                "access worksheet", worksheet_name, ValueError("No spreadsheet open")
            )
        try:
            worksheet = self.spreadsheet.worksheet(worksheet_name)
            logger.debug(f"Retrieved worksheet '{worksheet_name}'")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            self._handle_exception(
                "retrieve worksheet", worksheet_name, Exception("Worksheet not found")
            )
        except Exception as e:
            self._handle_exception("retrieve worksheet", worksheet_name, e)

    def get_all_records(self, worksheet_name: str) -> list[dict]:
        """Retrieve all records from a worksheet."""
        try:
            worksheet = self.get_worksheet(worksheet_name)
            records = worksheet.get_all_records()
            logger.debug(f"Retrieved {len(records)} records from '{worksheet_name}'")
            return records
        except Exception as e:
            logger.error(f"Failed to retrieve records from '{worksheet_name}': {e}")
            return []

    def get_all_values(self, worksheet_name: str) -> list[list]:
        """Retrieve all values from a worksheet."""
        try:
            worksheet = self.get_worksheet(worksheet_name)
            values = worksheet.get_all_values()
            logger.debug(f"Retrieved {len(values)} rows from '{worksheet_name}'")
            return values
        except Exception as e:
            logger.error(f"Failed to retrieve values from '{worksheet_name}': {e}")
            return []

    def get_column_values(self, worksheet_name: str, col_index: int) -> list:
        """Retrieve all values from a specific column in a worksheet."""
        try:
            worksheet = self.get_worksheet(worksheet_name)
            values = worksheet.col_values(col_index)
            logger.debug(
                f"Retrieved {len(values)} values from column {col_index} in '{worksheet_name}'"
            )
            return values
        except Exception as e:
            logger.error(
                f"Failed to retrieve column {col_index} values from '{worksheet_name}': {e}"
            )
            return []

    def get_values(self, worksheet_name: str, range_name: str) -> list[list]:
        """Retrieve values from a specific range in a worksheet."""
        try:
            worksheet = self.get_worksheet(worksheet_name)
            values = worksheet.get_values(range_name)
            logger.debug(
                f"Retrieved values from range '{range_name}' in '{worksheet_name}'"
            )
            return values
        except Exception as e:
            logger.error(
                f"Failed to retrieve values from range '{range_name}' in '{worksheet_name}': {e}"
            )
            return []

    def get_cell_value(self, worksheet_name: str, cell_address: str) -> str | None:
        """Retrieve the value of a single cell."""
        try:
            worksheet = self.get_worksheet(worksheet_name)
            value = worksheet.acell(cell_address).value
            logger.debug(
                f"Retrieved value '{value}' from cell '{cell_address}' in '{worksheet_name}'"
            )
            return value
        except Exception as e:
            logger.error(
                f"Failed to retrieve value from cell '{cell_address}' in '{worksheet_name}': {e}"
            )
            return None

    def update_cells(
        self,
        worksheet: gspread.Worksheet,
        range_name: str,
        values: list,
        value_input_option: str = "USER_ENTERED",
    ):
        """Update a range of cells in a worksheet."""
        try:
            worksheet.update(
                range_name=range_name,
                values=values,
                value_input_option=value_input_option,
            )
            logger.debug(f"Updated range '{range_name}' in '{worksheet.title}'")
        except Exception as e:
            self._handle_exception(
                "update range", f"{range_name} in {worksheet.title}", e
            )

    def update_cell(self, worksheet: gspread.Worksheet, row: int, col: int, value):
        """Update a single cell in a worksheet."""
        try:
            worksheet.update_cell(row, col, value)
            logger.debug(f"Updated cell ({row}, {col}) in '{worksheet.title}'")
        except Exception as e:
            self._handle_exception(
                "update cell", f"({row}, {col}) in {worksheet.title}", e
            )

    def append_row(
        self,
        worksheet: gspread.Worksheet,
        row_data: list,
        value_input_option: str = "USER_ENTERED",
    ):
        """Append a new row to a worksheet."""
        try:
            worksheet.append_row(values=row_data, value_input_option=value_input_option)
            logger.debug(f"Appended row to '{worksheet.title}'")
        except Exception as e:
            self._handle_exception("append row", worksheet.title, e)

    def append_rows(
        self,
        worksheet: gspread.Worksheet,
        rows_data: list[list],
        value_input_option: str = "USER_ENTERED",
    ):
        """Append multiple rows to a worksheet."""
        try:
            worksheet.append_rows(
                values=rows_data, value_input_option=value_input_option
            )
            logger.debug(f"Appended {len(rows_data)} rows to '{worksheet.title}'")
        except Exception as e:
            self._handle_exception(
                "append rows", f"{len(rows_data)} rows to {worksheet.title}", e
            )

    def insert_rows(
        self,
        worksheet: gspread.Worksheet,
        rows_data: list[list],
        row_index: int = 1,
        value_input_option: str = "USER_ENTERED",
    ):
        """Insert multiple rows into a worksheet at a specified index."""
        try:
            worksheet.insert_rows(
                values=rows_data, row=row_index, value_input_option=value_input_option
            )
            logger.debug(
                f"Inserted {len(rows_data)} rows at index {row_index} in '{worksheet.title}'"
            )
        except Exception as e:
            self._handle_exception(
                "insert rows",
                f"{len(rows_data)} rows at index {row_index} in {worksheet.title}",
                e,
            )

    def clear_worksheet(self, worksheet: gspread.Worksheet):
        """Clear all content from a worksheet."""
        try:
            worksheet.clear()
            logger.debug(f"Cleared worksheet '{worksheet.title}'")
        except Exception as e:
            self._handle_exception("clear worksheet", worksheet.title, e)

    def format_cell_range(
        self, worksheet: gspread.Worksheet, range_name: str, cell_format: CellFormat
    ):
        """Apply formatting to a specific cell range."""
        try:
            gspread_format_cell_range(worksheet, range_name, cell_format)
            logger.debug(f"Applied format to '{range_name}' in '{worksheet.title}'")
        except Exception as e:
            logger.error(
                f"Failed to apply format to '{range_name}' in '{worksheet.title}': {e}"
            )

    def format_cell_ranges(
        self, worksheet: gspread.Worksheet, ranges_formats: list[tuple[str, CellFormat]]
    ):
        """Apply multiple formatting rules to ranges."""
        for range_name, cell_format in ranges_formats:
            self.format_cell_range(worksheet, range_name, cell_format)

    def update_conditional_formats(
        self, worksheet: gspread.Worksheet, rules: list[ConditionalFormatRule]
    ):
        """Update conditional formatting rules for a worksheet."""
        try:
            sheet_rules = get_conditional_format_rules(worksheet)
            sheet_rules.clear()
            sheet_rules.extend(rules)
            sheet_rules.save()
            logger.debug(
                f"Updated conditional formatting rules for '{worksheet.title}'"
            )
        except Exception as e:
            logger.error(
                f"Failed to update conditional formatting rules for '{worksheet.title}': {e}"
            )

    def freeze_panes(self, worksheet: gspread.Worksheet, rows: int = 0, cols: int = 0):
        """Freeze rows and columns in a worksheet."""
        try:
            worksheet.freeze(rows=rows, cols=cols)
            logger.debug(f"Froze {rows} rows and {cols} columns in '{worksheet.title}'")
        except Exception as e:
            self._handle_exception("freeze panes", worksheet.title, e)

    def batch_update_properties(self, worksheet_id: int, requests: list):
        """Perform batch updates for sheet properties (e.g., column widths)."""
        try:
            self.spreadsheet.batch_update({"requests": requests})
            logger.debug(f"Performed batch update for sheet ID {worksheet_id}")
        except Exception as e:
            self._handle_exception(
                "perform batch update", f"sheet ID {worksheet_id}", e
            )

    def format_dashboard_sheet(
        self, worksheet: gspread.Worksheet, weekly_budget: float
    ):
        """Apply formatting to the hybrid budget dashboard worksheet."""
        # Define reusable formats
        formats = {
            "bold": CellFormat(textFormat=TextFormat(bold=True)),
            "currency": CellFormat(
                numberFormat=NumberFormat(type="NUMBER", pattern='#,##0.00 "PLN"')
            ),
            "percent": CellFormat(
                numberFormat=NumberFormat(type="NUMBER", pattern="0.00%")
            ),
            "integer": CellFormat(
                numberFormat=NumberFormat(type="NUMBER", pattern="0")
            ),
            "light_gray": CellFormat(backgroundColor=Color(0.9, 0.9, 0.9)),
            "header": CellFormat(backgroundColor=Color(0.8, 0.8, 0.8)),
        }

        # Apply left-hand side formatting
        self.format_cell_ranges(
            worksheet,
            [
                ("A1:A9", formats["bold"]),
                ("B2:B3", formats["currency"]),
                ("B5:B9", formats["currency"]),
                ("A10:D10", formats["bold"]),
                ("A10:D10", formats["header"]),
                ("C11:D17", formats["currency"]),
                *[(f"A{i}:D{i}", formats["light_gray"]) for i in range(11, 18, 2)],
            ],
        )

        # Right-hand side table formatting
        column_e_values = worksheet.col_values(5)
        for i, value in enumerate(column_e_values, start=1):
            if not value:
                continue
            start_row, header_text = i, value
            format_rules = []

            if "Category" in header_text:
                end_row = next(
                    (
                        j + 1
                        for j, v in enumerate(column_e_values[i:], start=i)
                        if not v
                    ),
                    len(column_e_values) + 1,
                )
                format_rules = [
                    (f"E{start_row}:G{start_row}", formats["bold"]),
                    (f"E{start_row}:G{start_row}", formats["header"]),
                    (f"F{start_row + 1}:F{end_row}", formats["currency"]),
                    (f"G{start_row + 1}:G{end_row}", formats["percent"]),
                ]
            elif "Needs vs. Wants" in header_text:
                format_rules = [
                    (f"E{start_row}:G{start_row}", formats["bold"]),
                    (f"E{start_row}:G{start_row}", formats["header"]),
                    (f"F{start_row + 1}:F{start_row + 2}", formats["currency"]),
                    (f"G{start_row + 1}:G{start_row + 2}", formats["percent"]),
                ]
            elif "Top Merchants by Spending" in header_text:
                end_row = start_row + 5
                format_rules = [
                    (f"E{start_row}:G{start_row}", formats["bold"]),
                    (f"E{start_row}:G{start_row}", formats["header"]),
                    (f"F{start_row + 1}:F{end_row}", formats["currency"]),
                    (f"G{start_row + 1}:G{end_row}", formats["integer"]),
                ]

            if format_rules:
                self.format_cell_ranges(worksheet, format_rules)

        # Conditional formatting
        rules = [
            ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("B6", worksheet)],
                booleanRule=BooleanRule(
                    condition=BooleanCondition(
                        "NUMBER_LESS", [str(weekly_budget * 0.1)]
                    ),
                    format=CellFormat(backgroundColor=Color(0.95, 0.7, 0.7)),
                ),
            ),
            ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("B6", worksheet)],
                booleanRule=BooleanRule(
                    condition=BooleanCondition(
                        "NUMBER_BETWEEN",
                        [str(weekly_budget * 0.1), str(weekly_budget * 0.5)],
                    ),
                    format=CellFormat(backgroundColor=Color(1.0, 0.95, 0.8)),
                ),
            ),
            ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("B6", worksheet)],
                booleanRule=BooleanRule(
                    condition=BooleanCondition(
                        "NUMBER_GREATER", [str(weekly_budget * 0.5)]
                    ),
                    format=CellFormat(backgroundColor=Color(0.8, 0.9, 0.8)),
                ),
            ),
            ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("B9", worksheet)],
                booleanRule=BooleanRule(
                    condition=BooleanCondition("NUMBER_GREATER_THAN_EQ", ["0"]),
                    format=CellFormat(backgroundColor=Color(0.8, 0.9, 0.8)),
                ),
            ),
            ConditionalFormatRule(
                ranges=[GridRange.from_a1_range("B9", worksheet)],
                booleanRule=BooleanRule(
                    condition=BooleanCondition("NUMBER_LESS", ["0"]),
                    format=CellFormat(backgroundColor=Color(0.95, 0.7, 0.7)),
                ),
            ),
        ]
        self.update_conditional_formats(worksheet, rules)

        # Freeze panes and column widths
        self.freeze_panes(worksheet, rows=10, cols=1)
        self.batch_update_properties(
            worksheet.id,
            [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "COLUMNS",
                            "startIndex": i,
                            "endIndex": i + 1,
                        },
                        "properties": {"pixelSize": size},
                        "fields": "pixelSize",
                    }
                }
                for i, size in [
                    (0, 250),
                    (1, 150),
                    (2, 120),
                    (3, 120),
                    (4, 220),
                    (5, 120),
                    (6, 80),
                ]
            ],
        )

        logger.info(f"Applied formatting to dashboard worksheet '{worksheet.title}'")
