import asyncio
import datetime

import pandas as pd
from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import config
from services.google_sheets import GoogleSheetsService
from services.telegram_api import TelegramService
from data_processing.expense_data import ExpenseDataManager
from data_processing.transaction_parser import (
    TransactionParser,
)  # Used for categorization update
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
        self.transaction_parser = TransactionParser()  # Categorization needs this

    async def _create_new_ai_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Helper to fetch all dashboard data, construct the initial AI prompt,
        and initialize a new AI chat session with that prompt.
        """
        try:
            df = self.expense_data_manager.load_expenses_dataframe()

            if df.empty:
                await self.telegram_service.send_message(
                    "I can't start a session as there is no expense data. Please add some expenses first."
                )
                return None

            today = datetime.datetime.now()
            three_months_ago = today - datetime.timedelta(days=90)
            df_ai_context = df[df["Date"] >= three_months_ago].copy()

            if df_ai_context.empty:
                await self.telegram_service.send_message(
                    "I found data, but no recent transactions in the last 90 days to build the AI conversation. Please add some recent expenses."
                )
                context.chat_data["expenses_df"] = (
                    df  # Still store full df for other uses if needed
                )
                return None
            logger.info(
                f"AI context DataFrame sliced to {len(df_ai_context)} rows from the last 90 days."
            )

            # Fetch data required for AI prompt from sheets
            budget_ws = self.sheets_service.get_worksheet(config.BUDGET_WORKSHEET_NAME)
            summary_labels = self.sheets_service.get_values(budget_ws.title, "A5:A9")
            summary_values = self.sheets_service.get_values(budget_ws.title, "B5:B9")
            budget_context = {
                label[0]: value[0]
                for label, value in zip(summary_labels, summary_values)
            }

            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            daily_rows = self.sheets_service.get_values(budget_ws.title, "A11:D17")
            for row in daily_rows:
                if row and len(row) > 1 and row[1] == today_str:
                    budget_context["Safe to Spend Today"] = row[3]
                    break

            all_rh_values = self.sheets_service.get_values(
                budget_ws.title, "E:G"
            )  # Use worksheet name directly

            def extract_table_as_string(start_header: str):
                table_lines = []
                in_table = False
                for row in all_rh_values:
                    if not row or not row[0]:
                        if in_table:
                            break
                        else:
                            continue
                    if start_header in row[0]:
                        in_table = True
                    if in_table:
                        table_lines.append("\t".join(str(cell).strip() for cell in row))
                return "\n".join(table_lines)

            category_summary = extract_table_as_string("Category")
            needs_wants_summary = extract_table_as_string("Needs vs. Wants")

            if not self.gemini_ai.model:
                await self.telegram_service.send_message(
                    "AI model not configured. Cannot start AI conversation."
                )
                return None

            initial_prompt = self.gemini_ai.get_initial_prompt(
                df_ai_context, budget_context, category_summary, needs_wants_summary
            )
            chat_session = self.gemini_ai.model.start_chat(history=[])
            chat_session.send_message(initial_prompt)
            logger.info("AI chat session successfully started with budget context.")

            context.chat_data["ai_chat_session"] = chat_session
            context.chat_data["expenses_df"] = df
            return chat_session

        except Exception as e:
            logger.error(f"Error creating new chat session: {e}", exc_info=True)
            await self.telegram_service.send_message(
                "❌ Sorry, I encountered an error while trying to start a new AI conversation. Please try again later."
            )
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
        """Fetches and sends the budget summary with a mobile-friendly table."""
        await self.telegram_service.send_message("🔄 Fetching your weekly summary...")

        try:
            budget_ws = self.sheets_service.get_worksheet(config.BUDGET_WORKSHEET_NAME)
            values = self.sheets_service.get_values(budget_ws.title, "A1:D17")

            remaining_weekly_str = values[5][1]  # Cell B6
            bonus_savings_str = values[8][1]  # Cell B9

            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            safe_to_spend_today = "N/A"
            daily_rows = values[10:17]
            for row in daily_rows:
                if row and len(row) > 1 and row[1] == today_str:
                    safe_to_spend_today = row[3]
                    break

            summary_text = (
                f"📊 *Your Current Budget Summary*\n\n"
                f"💰 Remaining this week: *{remaining_weekly_str}*\n"
                f"💡 Safe to spend today: *{safe_to_spend_today}*\n"
                f"🏆 On-Pace savings: *{bonus_savings_str}*\n"
            )

            # Mobile-Friendly Table Formatting
            table_lines = ["```"]  # Start of code block
            table_lines.append("Day  |    Spent   |    Safe")
            table_lines.append("--------------------------")

            for row in daily_rows:
                if not row or len(row) < 4:
                    continue
                day, date, spent, safe_to_spend = row
                day_marker = "->" if date == today_str else "  "

                try:
                    # Clean the spent string for float conversion
                    spent_val = (
                        float(spent.replace("PLN", "").replace(",", "").strip())
                        if spent != "-"
                        else 0
                    )
                except ValueError:
                    spent_val = 0

                safe_val_str = (
                    safe_to_spend.replace(" PLN", "").strip()
                    if safe_to_spend != "-"
                    else "-"
                )

                # Ensure consistent padding for table
                table_lines.append(
                    f"{day_marker}{day[:3]:<4}| {spent_val:9.2f} | {safe_val_str:>8}"
                )

            table_lines.append("```")  # End of code block

            full_message = summary_text + "\n".join(table_lines)
            await self.telegram_service.send_message(
                full_message, parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Error in /summary command: {e}", exc_info=True)
            await self.telegram_service.send_message(
                "❌ Sorry, I couldn't fetch your summary. Please check the logs."
            )

    async def top5_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fetches and sends the top 5 merchants by spending."""
        await self.telegram_service.send_message("🏆 Fetching your top 5 merchants...")
        try:
            budget_ws = self.sheets_service.get_worksheet(config.BUDGET_WORKSHEET_NAME)
            rh_values = self.sheets_service.get_values(budget_ws.title, "E:G")

            start_row = -1
            for i, row in enumerate(rh_values):
                if row and "Top Merchants by Spending" in row[0]:
                    start_row = i + 1  # +1 for 1-based indexing in slice
                    break

            if start_row == -1:
                await self.telegram_service.send_message(
                    "🤔 Couldn't find the 'Top Merchants' table on your dashboard."
                )
                return

            # Adjust slice to get 5 merchants below the header
            top_merchants_raw = rh_values[start_row : start_row + 5]

            message_lines = ["🏆 *Top 5 Merchants by Spending This Month*\n"]
            for i, merchant_row in enumerate(top_merchants_raw):
                if not merchant_row or len(merchant_row) < 3:
                    continue  # Skip empty or malformed rows

                name = merchant_row[0]
                spent = merchant_row[1]
                visits = merchant_row[2]

                message_lines.append(
                    f"`{i+1}. {name:<20} {spent:<12} ({visits} visits)`"
                )

            if len(message_lines) == 1:  # Only header present
                await self.telegram_service.send_message(
                    "🤔 No top merchants data found in the table."
                )
            else:
                await self.telegram_service.send_message(
                    "\n".join(message_lines), parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error in /top5 command: {e}", exc_info=True)
            await self.telegram_service.send_message(
                "❌ Sorry, I couldn't fetch your top merchants."
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
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Handles all text messages. If no AI chat session exists, it attempts to create one
        before sending the user's query.
        """
        chat_session = context.chat_data.get("ai_chat_session")
        user_query = update.message.text

        # If no chat session, try to create one automatically
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

        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="typing"
            )
            response_text = await asyncio.to_thread(
                self.gemini_ai.send_chat_message, chat_session, user_query
            )
            await self.telegram_service.send_message(
                response_text, parse_mode=None
            )  # AI has specific formatting needs

        except Exception as e:
            logger.error(f"Error sending message to AI: {e}", exc_info=True)
            await self.telegram_service.send_message(
                "Sorry, I encountered an error. Please try asking in a different way or use `/newchat` to reset our conversation."
            )
