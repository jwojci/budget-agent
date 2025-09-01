import asyncio

from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from services.google_sheets import GoogleSheetsService
from services.telegram_api import TelegramService
from data_processing.expense_data import ExpenseDataManager
from analytics.dashboard_metrics import DashboardMetricsCalculator
from ai.agent import BudgetAgent

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
        budget_agent: BudgetAgent,
    ):
        self.sheets_service = sheets_service
        self.telegram_service = telegram_service
        self.expense_data_manager = expense_data_manager
        self.metrics_calculator = metrics_calculator
        self.budget_agent_prototype = budget_agent

    def _get_or_create_agent_for_chat(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> BudgetAgent:
        """
        Retrieves the agent for the current chat, or creates a new one if it doesn't exist.
        This ensures each user chat has its own separate memory.
        """
        if "budget_agent_instance" not in context.chat_data:
            # Create a new instance from the prototype to ensure a fresh start
            context.chat_data["budget_agent_instance"] = BudgetAgent(
                self.budget_agent_prototype.app_context
            )

        return context.chat_data["budget_agent_instance"]

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
        """Clears the previous AI conversation by removing the agent instance."""
        if "budget_agent_instance" in context.chat_data:
            del context.chat_data["budget_agent_instance"]
            await self.telegram_service.send_message(
                "My short-term memory has been cleared."
            )
        else:
            await self.telegram_service.send_message("What can I help you with?")

    async def start_categorization(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Starts the conversation by fetching data and calling the main UI function."""
        await update.message.reply_text("🔍 Searching for uncategorized merchants...")
        try:
            uncategorized, existing_categories, categories_ws = (
                self.expense_data_manager.get_category_data()
            )
        except Exception as e:
            logger.error(f"Error fetching category data: {e}", exc_info=True)
            await update.message.reply_text("❌ Error loading category data.")
            return ConversationHandler.END

        if not uncategorized:
            await update.message.reply_text(
                "✨ All merchants are categorized. Great job!"
            )
            return ConversationHandler.END

        # Store all session data in one place
        context.user_data.update(
            {
                "uncategorized": uncategorized,
                "categories": existing_categories,
                "worksheet": categories_ws,
                "index": 0,
                "total": len(uncategorized),
            }
        )

        # Prepare and send the first message, which will be edited from now on
        text, reply_markup = self._get_category_question(context)
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )

        return SELECTING_CATEGORY

    async def ask_to_categorize_keyword(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """
        The master function that displays the current item and its buttons.
        It either sends a new message (on first run) or edits an existing one.
        It is the single source of truth for returning the next state.
        """
        uncategorized_list = context.user_data["uncategorized_keywords"]
        index = context.user_data["current_index"]
        query = update.callback_query

        # Check if the conversation is over
        if index >= len(uncategorized_list):
            final_message = "🎉 All done! Everything is now categorized."
            if query:
                # If we are in a callback, edit the message to its final state
                await query.edit_message_text(text=final_message)
            else:
                # This case should rarely happen, but as a fallback
                await update.message.reply_text(final_message)
            context.user_data.clear()
            return ConversationHandler.END

        # Prepare the message content for the current item
        keyword = uncategorized_list[index]["Keyword"]
        context.user_data["current_keyword"] = keyword

        buttons = [
            InlineKeyboardButton(cat, callback_data=f"cat_{cat}")
            for cat in context.user_data["existing_categories"]
        ]
        keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        keyboard.append([InlineKeyboardButton("➡️ Skip", callback_data="cat_skip")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cat_cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"({index + 1}/{len(uncategorized_list)}) How would you categorize this merchant?\n\n👉 *{keyword}*"

        # If this is a callback, edit the message. Otherwise, send a new one.
        if query:
            await query.edit_message_text(
                text=message_text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text=message_text, reply_markup=reply_markup, parse_mode="Markdown"
            )

        # Keep the conversation in the category selection state
        return SELECTING_CATEGORY

    async def receive_category_choice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handles a button press for category, skip, or cancel."""
        query = update.callback_query
        await query.answer()

        choice = query.data.split("_", 1)[1]

        if choice == "cancel":
            await query.edit_message_text("👍 Categorization cancelled.")
            context.user_data.clear()
            return ConversationHandler.END

        if choice == "skip":
            # Just move to the next item
            context.user_data["index"] += 1
            text, reply_markup = self._get_category_question(context)
            await query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )

            # If reply_markup is None, it means we're done. End the conversation.
            return SELECTING_CATEGORY if reply_markup else ConversationHandler.END

        # User selected a category. Store it and move to the "Need/Want" question.
        context.user_data["chosen_category"] = choice
        text, reply_markup = self._get_type_question(context)
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )

        return SELECTING_TYPE

    async def receive_type_choice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handles the Need/Want button press."""
        query = update.callback_query
        await query.answer()

        # Get all data from context
        chosen_type = query.data.split("_", 1)[1]
        keyword = context.user_data["uncategorized"][context.user_data["index"]][
            "Keyword"
        ]
        category = context.user_data["chosen_category"]
        worksheet = context.user_data["worksheet"]

        # Update the spreadsheet
        try:
            cell = worksheet.find(keyword, in_column=1)
            if cell:
                self.sheets_service.update_cell(worksheet, cell.row, 2, category)
                self.sheets_service.update_cell(worksheet, cell.row, 3, chosen_type)
        except Exception as e:
            logger.error(f"Failed to update sheet for '{keyword}': {e}", exc_info=True)
            await query.edit_message_text(
                "❌ An error occurred while updating the sheet. Cancelling."
            )
            return ConversationHandler.END

        # Move to the next item and display it
        context.user_data["index"] += 1
        text, reply_markup = self._get_category_question(context)
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )

        # If reply_markup is None, we're done. Otherwise, go back to the category selection state.
        return SELECTING_CATEGORY if reply_markup else ConversationHandler.END

    async def cancel_conversation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Fallback for the /cancel command, in case the user types it."""
        await update.message.reply_text("👍 Categorization cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    def _get_category_question(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        """Generates the text and buttons for the category selection screen."""
        idx = context.user_data["index"]
        total = context.user_data["total"]

        if idx >= total:
            return "🎉 All done! Everything is now categorized.", None

        keyword = context.user_data["uncategorized"][idx]["Keyword"]
        categories = context.user_data["categories"]

        buttons = [
            InlineKeyboardButton(cat, callback_data=f"cat_{cat}") for cat in categories
        ]
        keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        keyboard.append([InlineKeyboardButton("➡️ Skip", callback_data="cat_skip")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cat_cancel")])

        text = f"**({idx + 1}/{total})** How do you categorize this merchant?\n\n👉 **{keyword}**"
        return text, InlineKeyboardMarkup(keyboard)

    def _get_type_question(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> tuple[str, InlineKeyboardMarkup]:
        """Generates the text and buttons for the "Need vs Want" screen."""
        idx = context.user_data["index"]
        keyword = context.user_data["uncategorized"][idx]["Keyword"]
        category = context.user_data["chosen_category"]

        keyboard = [
            [
                InlineKeyboardButton("✔️ Need", callback_data="type_Need"),
                InlineKeyboardButton("🛍️ Want", callback_data="type_Want"),
            ]
        ]

        text = f"Got it. You categorized **{keyword}** as **{category}**.\n\nIs this a **Need** or a **Want**?"
        return text, InlineKeyboardMarkup(keyboard)

    async def handle_text_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        command_query: str = None,
    ):
        user_query = command_query or update.message.text

        # Show a "typing..." indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )

        agent = self._get_or_create_agent_for_chat(context)

        # Run the agent's invoke method in a separate thread to avoid blocking asyncio
        response_text = await asyncio.to_thread(agent.invoke, user_query)

        await self.telegram_service.send_message(response_text, parse_mode="Markdown")
