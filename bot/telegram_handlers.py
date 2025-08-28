import asyncio

from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from services.google_sheets import GoogleSheetsService
from services.telegram_api import TelegramService
from data_processing.expense_data import ExpenseDataManager
from analytics.dashboard_metrics import DashboardMetricsCalculator
from ai.gemini_ai import GeminiAI

# Conversation States for /categorize
SELECTING_CATEGORY, SELECTING_TYPE = range(2)


class TelegramBotHandlers:
    """
    Collection of Telegram bot command and message handlers.
    """

    def __init__(
        self,
        sheets_service: GoogleSheetsService,
        telegram_service: TelegramService,
        expense_data_manager: ExpenseDataManager,
        metrics_calculator: DashboardMetricsCalculator,
        gemini_ai: GeminiAI,
    ):
        self.sheets_service = sheets_service
        self.telegram_service = telegram_service
        self.expense_data_manager = expense_data_manager
        self.metrics_calculator = metrics_calculator
        self.gemini_ai = gemini_ai

    async def _create_new_ai_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Helper to initialize a new AI agent chat session."""
        try:
            # This is now super simple
            chat_session = self.gemini_ai.start_new_chat()
            if chat_session:
                context.chat_data["ai_chat_session"] = chat_session
                logger.info("New AI Agent chat session started.")
                return chat_session
            else:
                await update.message.reply_text(
                    "Sorry, the AI model could not be initialized."
                )
                return None
        except Exception as e:
            logger.error(f"Error creating new AI chat session: {e}", exc_info=True)
            await update.message.reply_text("An error occurred while starting the AI.")
            return None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends a welcome message and lists available commands."""
        welcome_text = (
            "👋 *Welcome to Your Personal Finance Bot!*\n\n"
            "I can give you on-demand updates from your budget spreadsheet.\n\n"
            "Here are the commands you can use:\n"
            "`/summary` - Get a full weekly budget and daily breakdown.\n"
            "`/top5` - Show your top 5 merchants by spending.\n"
            "`/categorize` - Start an interactive session to categorize new merchants.\n"
            "`/newchat` - Start a fresh AI conversation.\n"
            "`/help` - Show this message again."
        )
        await self.telegram_service.send_message(welcome_text, parse_mode="Markdown")

    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /summary command by asking the AI agent."""
        await self.handle_text_query(
            update,
            context,
            command_query="give me a summary of my current budget status",
        )

    async def top5_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /top5 command by asking the AI agent."""
        await self.handle_text_query(
            update,
            context,
            command_query="what are my top 5 merchants by spending this month?",
        )

    async def new_chat_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Clears the previous AI conversation and starts a new one."""
        if "ai_chat_session" in context.chat_data:
            context.chat_data.pop("ai_chat_session")
            logger.info("Existing AI chat session cleared.")
            await self.telegram_service.send_message(
                "✨ My short-term memory has been cleared."
            )

        await self.telegram_service.send_message(
            "🧠 Starting a new AI conversation... please wait a moment while I load your data."
        )

        # Trigger typing action
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        chat_session = await self._create_new_ai_session(update, context)

        if chat_session:
            await self.telegram_service.send_message(
                "I've loaded the latest data. What would you like to know?"
            )
        else:
            # Error message already sent by _create_new_ai_session
            pass

    async def start_categorization(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        await self.telegram_service.send_message(
            "🔍 Searching for uncategorized merchants..."
        )
        try:
            uncategorized, existing_categories, categories_ws = (
                self.expense_data_manager.get_category_data()
            )
        except Exception as e:
            logger.error(
                f"Error fetching category data for categorization: {e}", exc_info=True
            )
            await self.telegram_service.send_message(
                "❌ Error loading category data. Please try again later."
            )
            return ConversationHandler.END

        if not uncategorized:
            await self.telegram_service.send_message(
                "✨ All merchants are categorized. Great job!"
            )
            return ConversationHandler.END

        context.user_data["uncategorized_keywords"] = (
            uncategorized  # Rename for clarity
        )
        context.user_data["existing_categories"] = existing_categories
        context.user_data["categories_ws"] = categories_ws  # Store the worksheet object
        context.user_data["current_index"] = 0
        return await self.ask_to_categorize_keyword(update, context)

    async def ask_to_categorize_keyword(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        uncategorized_list = context.user_data["uncategorized_keywords"]
        index = context.user_data["current_index"]

        if index >= len(uncategorized_list):
            final_message = "🎉 All done! Everything is now categorized."
            if update.callback_query:
                await update.callback_query.message.reply_text(final_message)
            else:
                await update.message.reply_text(final_message)
            return ConversationHandler.END

        keyword_to_categorize = uncategorized_list[index]["Keyword"]
        context.user_data["current_keyword_data"] = uncategorized_list[
            index
        ]  # Store the full row data
        context.user_data["current_keyword"] = (
            keyword_to_categorize  # For easier access to just the keyword string
        )

        buttons = [
            InlineKeyboardButton(cat, callback_data=f"cat_{cat}")
            for cat in context.user_data["existing_categories"]
        ]
        keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        keyboard.append([InlineKeyboardButton("➡️ Skip", callback_data="cat_skip")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"How would you like to categorize this merchant?\n\n👉 *{keyword_to_categorize}*"

        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                message_text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        return SELECTING_CATEGORY

    async def receive_category_choice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        query = update.callback_query
        await query.answer()  # Acknowledge the callback query

        choice = query.data.split("_", 1)[1]
        if choice == "skip":
            context.user_data["current_index"] += 1
            return await self.ask_to_categorize_keyword(update, context)

        context.user_data["chosen_category"] = choice

        keyboard = [
            [
                InlineKeyboardButton("✔️ Need", callback_data="type_Need"),
                InlineKeyboardButton("🛍️ Want", callback_data="type_Want"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=f"Categorizing *{context.user_data['current_keyword']}* as `{choice}`.\n\nIs it a Need or a Want?",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return SELECTING_TYPE

    async def receive_type_choice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        query = update.callback_query
        await query.answer()  # Acknowledge the callback query

        chosen_type = query.data.split("_", 1)[1]
        keyword = context.user_data["current_keyword"]
        category = context.user_data["chosen_category"]
        categories_ws = context.user_data["categories_ws"]

        try:
            # Find the row by keyword in column 1 and update Category (col 2) and Type (col 3)
            cell = categories_ws.find(keyword, in_column=1)
            # Update cells: Keyword is col 1, Category is col 2, Type is col 3
            self.sheets_service.update_cell(
                categories_ws, cell.row, 2, category
            )  # Update Category
            self.sheets_service.update_cell(
                categories_ws, cell.row, 3, chosen_type
            )  # Update Type (assuming it's col 3)

            logger.info(
                f"Updated '{keyword}' to Category: {category}, Type: {chosen_type}"
            )
            await query.edit_message_text(
                f"✅ *{keyword}* categorized as `{category}` (`{chosen_type}`)."
            )

        except Exception as e:
            logger.error(
                f"Failed to update sheet for keyword '{keyword}': {e}", exc_info=True
            )
            await query.edit_message_text(
                "❌ An error occurred while updating the sheet for categorization."
            )
            return ConversationHandler.END

        # Move to the next uncategorized keyword
        context.user_data["current_index"] += 1
        return await self.ask_to_categorize_keyword(update, context)

    async def cancel_conversation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        await self.telegram_service.send_message("Categorization cancelled.")
        context.user_data.clear()  # Clear all user_data for this conversation
        return ConversationHandler.END

    async def handle_text_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        command_query: str = None,
    ):
        chat_session = context.chat_data.get("ai_chat_session")
        user_query = command_query or update.message.text

        if not chat_session:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="typing"
            )
            await self.telegram_service.send_message(
                "Just a moment, I'm loading your budget data to start our conversation..."
            )
            chat_session = await self._create_new_ai_session(update, context)
            if not chat_session:
                # Error message already sent by _create_new_ai_session
                return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )

        response_text = await asyncio.to_thread(
            self.gemini_ai.send_chat_message, chat_session, user_query
        )

        await self.telegram_service.send_message(response_text, parse_mode="Markdown")
