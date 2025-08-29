"""
Manages sending messages to Telegram.
"""

from loguru import logger
import telegram
from telegram.error import BadRequest
import config


class TelegramService:
    """Handles sending messages to Telegram with fallback for formatting issues."""

    def __init__(
        self,
        bot_token: str = config.TELEGRAM_BOT_TOKEN,
        chat_id: str = config.TELEGRAM_CHAT_ID,
    ):
        """Initialize with bot token and chat ID, or disable if not provided."""
        if not bot_token or not chat_id:
            logger.warning(
                "Missing Telegram bot token or chat ID. Messages will be skipped."
            )
            self.bot = None
            return
        self.bot = telegram.Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> None:
        """Send a Telegram message with fallback to plain text if Markdown fails."""
        if not self.bot:
            logger.debug("Telegram service not initialized. Skipping message.")
            return

        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=text, parse_mode=parse_mode
            )
            logger.info("Successfully sent Telegram message.")
        except BadRequest as e:
            logger.error(f"Markdown error in Telegram message: {e}")
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id, text=text, parse_mode=None
                )
                logger.warning("Sent message as plain text after Markdown failure.")
            except Exception as retry_e:
                logger.error(f"Failed to send plain text Telegram message: {retry_e}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def format_summary_for_telegram(self, summary_data: dict) -> str:
        """Format monthly summary data into a Telegram message."""
        month = summary_data.get("month", "N/A")
        total_spent = summary_data.get("total_spent", 0)
        bonus_savings = summary_data.get("bonus_savings", 0)
        needs_percent = summary_data.get("needs_percent", 0)
        wants_percent = summary_data.get("wants_percent", 0)

        savings_message = (
            f"🎉 Great job! You generated *{bonus_savings:.2f} PLN* in bonus savings!\nDon't forget to transfer it! ➡️ 🏦"
            if bonus_savings >= 0
            else f"⚠️ Overspent by *{abs(bonus_savings):.2f} PLN*."
        )

        return (
            f"📊 *Monthly Summary: {month}* 📊\n\n"
            f"*- Total Spent:* `{total_spent:,.2f} PLN`\n"
            f"*- Spending Split:* `{needs_percent:.0%} Needs` vs. `{wants_percent:.0%} Wants`\n\n"
            f"{savings_message}"
        )
