from loguru import logger

import config
from services.google_sheets import GoogleSheetsService


class HeaderValidator:
    def __init__(self, sheets_service: GoogleSheetsService):
        self.sheets_service = sheets_service

    async def check_and_fix_expenses_header(self):
        """Ensures the expenses worksheet has the correct header."""
        try:
            expenses_ws = self.sheets_service.get_worksheet(
                config.WORKSHEETS["expenses"]
            )
            header = expenses_ws.row_values(1)
            if header != config.EXPENSE_HEADER:
                logger.warning("Expenses sheet header is incorrect. Fixing...")
                expenses_ws.clear()
                self.sheets_service.append_row(expenses_ws, config.EXPENSE_HEADER)
            else:
                logger.info("Expenses sheet header is correct.")
        except Exception as e:
            logger.error(f"Failed to check or fix expenses header: {e}", exc_info=True)
