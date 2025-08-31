import datetime
import asyncio

from loguru import logger
from telegram.ext import Application
from langchain_core.messages import HumanMessage, AIMessage

import config
from services.telegram_api import TelegramService
from ai.agent import BudgetAgent


class WeeklyDigestGenerator:
    def __init__(self, app_context: dict, telegram_service: TelegramService):
        self.app_context = app_context
        self.telegram_service = telegram_service

    def _get_main_chat_agent(self, application: Application) -> BudgetAgent | None:
        """
        Gets the user's persistent BudgetAgent instance from chat_data.
        """
        chat_id = int(config.TELEGRAM_CHAT_ID)
        chat_data = application.chat_data[chat_id]

        if "budget_agent_instance" not in chat_data:
            logger.info("Main chat agent not found, creating one for weekly digest.")
            chat_data["budget_agent_instance"] = BudgetAgent(self.app_context)

        return chat_data["budget_agent_instance"]

    async def generate_and_send_digest(self, application: Application):
        """Generates, sends, and saves weekly digest to the main chat context."""
        logger.info("Generating weekly AI digest...")
        try:
            main_agent = self._get_main_chat_agent(application)
            if not main_agent:
                return

            prompt = "Generate a weekly financial digest based on user's last week's spending data."
            digest_text = await asyncio.to_thread(main_agent.invoke, prompt)

            # send the message to the user
            await self.telegram_service.send_message(digest_text, parse_mode="Markdown")

            # this makes the agent "remember" this system-initiated conversation.
            main_agent.chat_history.append(HumanMessage(content=prompt))
            main_agent.chat_history.append(AIMessage(content=digest_text))

            logger.info(
                "Weekly AI digest sent and context updated in main chat session."
            )

        except Exception as e:
            logger.error(f"Failed to generate weekly digest: {e}")
