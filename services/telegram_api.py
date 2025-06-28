import telegram
from loguru import logger

from ..config import *


class TelegramService:
    """
    Manages sending messages to Telegram.
    """

    def __init__(self, bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID):
        if not bot_token or not chat_id:
            logger.warning(
                "Telegram bot token or chat ID not set. Telegram messages will be skipped."
            )
            self.bot = None
        else:
            self.bot = telegram.Bot(token=bot_token)
            self.chat_id = chat_id

    async def send_message(self, text: str, parse_mode="Markdown"):
        """A centralized function to send a Telegram message."""
        if not self.bot:
            logger.debug("Telegram service not initialized. Skipping message.")
            return

        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=text, parse_mode=parse_mode
            )
            logger.info("Successfully sent Telegram message.")
        except telegram.error.BadRequest as e:
            logger.error(
                f"Failed to send Telegram message due to BadRequest (likely Markdown issue): {e}"
            )
            # Fallback: Try sending as plain text if Markdown fails
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id, text=text, parse_mode=None
                )
                logger.warning(
                    "Sent message as plain text after Markdown parsing failure."
                )
            except Exception as retry_e:
                logger.error(
                    f"Failed to send Telegram message even as plain text: {retry_e}",
                    exc_info=True,
                )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}", exc_info=True)

    def format_summary_for_telegram(self, summary_data: dict) -> str:
        """Formats the monthly summary data into a nice Telegram message."""
        month = summary_data.get("month", "N/A")
        total_spent = summary_data.get("total_spent", 0)
        bonus_savings = summary_data.get("bonus_savings", 0)
        needs_percent = summary_data.get("needs_percent", 0)
        wants_percent = summary_data.get("wants_percent", 0)

        header = f"📊 *Monthly Summary: {month}* 📊\n\n"

        if bonus_savings >= 0:
            savings_message = f"🎉 Great job! You generated *{bonus_savings:.2f} PLN* in bonus savings!\nDon't forget to transfer it! ➡️ 🏦"
        else:
            savings_message = f"⚠️ This month, you overspent your budget by *{abs(bonus_savings):.2f} PLN*."

        body = (
            f"*- Total Spent:* `{total_spent:,.2f} PLN`\n"
            f"*- Spending Split:* `{needs_percent:.0%} Needs` vs. `{wants_percent:.0%} Wants`\n\n"
            f"{savings_message}"
        )

        return header + body
