import asyncio
from loguru import logger


import config
from data_processing.transaction_parser import get_parser
from auth.google_auth import GoogleAuthenticator
from services.google_sheets import GoogleSheetsService
from services.gmail_api import GmailService
from services.telegram_api import TelegramService


class EmailProcessor:
    """
    Handles fetching, parsing and processing transaction emails and updating the spreadsheet.
    """

    def __init__(
        self, sheets_service: GoogleSheetsService, telegram_service: TelegramService
    ):
        self.sheets_service = sheets_service
        self.telegram_service = telegram_service
        try:
            authenticator = GoogleAuthenticator()
            gmail_api_client = authenticator.get_gmail_service()
            if not gmail_api_client:
                raise ConnectionError("Failed to get Gmail client for EmailProcessor.")
            self.gmail_service = GmailService(gmail_api_client)
        except Exception as e:
            logger.critical(f"Failed to initialize GmailService in EmailProcessor: {e}")
            self.gmail_service = None

    async def process_new_transactions(self):
        """Fetches and processes daily expense emails using the parser factory."""
        logger.info("Processing daily emails...")

        parser = self._get_parser()
        if not parser:
            return

        worksheets, existing_data = await self._get_processing_data()

        # Process emails and collect results
        new_rows, new_keywords = await self.process_emails(parser, existing_data)

        # Update sheets with new data
        await self._update_sheets_with_transactions(worksheets["expenses"], new_rows)

        # Handle new keywords
        await self._handle_new_keywords(
            worksheets["categories"], existing_data["existing_keywords"], new_keywords
        )

        logger.info("Email processing complete.")

    def _get_parser(self):
        """Retrieves the appropriate email parser based on configuration."""
        parser = get_parser(config.EMAIL_SENDER)
        if not parser:
            error_msg = (
                f"Parser Error: No parser found for sender '{config.EMAIL_SENDER}'."
            )
            logger.error(error_msg)
            asyncio.create_task(self.telegram_service.send_message(error_msg))
        return parser

    async def _get_processing_data(self):
        """Sets up worksheets and existing data needed for email processing."""
        try:
            expenses_ws = self.sheets_service.get_worksheet(
                config.WORKSHEETS["expenses"]
            )
            categories_ws = self.sheets_service.get_worksheet(
                config.WORKSHEETS["categories"]
            )
            existing_dates = set(
                self.sheets_service.get_column_values(config.WORKSHEETS["expenses"], 6)[
                    1:
                ]
            )
            category_records = self.sheets_service.get_all_records(
                config.WORKSHEETS["categories"]
            )
            existing_keywords = {
                rec.get("Keyword", "").lower()
                for rec in category_records
                if rec.get("Keyword")
            }
            return {"expenses": expenses_ws, "categories": categories_ws}, {
                "existing_dates": existing_dates,
                "category_records": category_records,
                "existing_keywords": existing_keywords,
            }
        except Exception as e:
            logger.error(f"Failed to set up email processing data: {e}")
            return None, None

    async def process_emails(self, parser, existing_data):
        """Processes emails for the current month and extracts transactions and keywords."""
        new_rows, new_keywords = [], set()
        email_ids = self.gmail_service.get_email_ids_for_current_month() or []

        for email_id in reversed(email_ids):
            attachment_path = self.gmail_service.save_attachments_from_message(email_id)
            if not attachment_path:
                logger.warning(f"No attachment for email {email_id}.")
                continue

            # Parse and process transactions
            raw_transactions = parser.parse_html(attachment_path)
            rows, keywords = parser.process_transactions(
                raw_transactions,
                attachment_path,
                existing_data["existing_dates"],
                existing_data["category_records"],
            )
            new_rows.extend(rows)
            new_keywords.update(keywords)

        return new_rows, new_keywords

    async def _update_sheets_with_transactions(self, expenses_ws, new_rows):
        """Updates the expenses worksheet with new transaction rows."""
        if new_rows:
            logger.info(f"Adding {len(new_rows)} transactions...")
            self.sheets_service.append_rows(expenses_ws, new_rows)
            await self.telegram_service.send_message(
                f"✅ {len(new_rows)} transactions saved."
            )

    async def _handle_new_keywords(
        self, categories_ws, existing_keywords, new_keywords
    ):
        """Handles new keywords by adding them to the categories worksheet."""
        truly_new_keywords = [
            kw for kw in new_keywords if kw.lower() not in existing_keywords
        ]
        if truly_new_keywords:
            logger.info(f"Adding {len(truly_new_keywords)} new keywords...")
            self.sheets_service.append_rows(
                categories_ws, [[kw, "", ""] for kw in truly_new_keywords]
            )
            await self.telegram_service.send_message(
                f"🤔 New Keywords Found\nPlease categorize:\n- "
                + "\n- ".join(truly_new_keywords)
                + "\n\nUse /categorize."
            )
