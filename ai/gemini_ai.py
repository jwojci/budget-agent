import pandas as pd

from loguru import logger
import google.generativeai as genai

from config import *


class GeminiAI:
    """
    Manages interaction with the Gemini AI model for budget analysis and chat.
    """

    def __init__(self, api_key=GEMINI_API_KEY, model_name="gemini-2.5-flash"):
        if not api_key:
            logger.error("GEMINI_API_KEY not found. AI features will be unavailable.")
            self.model = None
            return
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"Gemini AI model '{model_name}' configured.")

    def get_initial_prompt(
        self,
        df: pd.DataFrame,
        budget_context: dict,
        category_summary: str,
        needs_wants_summary: str,
    ) -> str:
        """
        Constructs the initial system prompt for the AI chat session,
        including comprehensive budget context and transaction data.
        """
        data_string = df[["Date", "Description", "Expense", "Category", "Type"]].to_csv(
            index=False
        )
        context_string = "\n".join(
            [f"- {key}: {value}" for key, value in budget_context.items()]
        )
        current_date_str = pd.to_datetime("today").strftime("%Y-%m-%d")
        return f"""
        You are "Budget Bot," a friendly, helpful, and highly analytical personal finance assistant. Your primary function is to provide accurate and insightful answers to the user's financial questions.

        **CRITICAL OUTPUT INSTRUCTIONS:**
        - NEVER use Markdown formatting characters like `*`, `_`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `curlybraces`, `.`, `!` in your responses. If you need to emphasize something, use CAPITAL LETTERS.
        - Do NOT show your calculation steps. Just provide the final calculated answer clearly and concisely. For example, if asked "How much did I spend on groceries last week?", respond with "You spent 123.45 PLN on groceries last week." Do NOT show "10+20+30=60".
        - All monetary values must be formatted in PLN, e.g., "123.45 PLN".
        - ENSURE ALL RELEVANT TRANSACTION DATA IS FULLY PROCESSED FOR CALCULATIONS AND LISTINGS.

        The current date is {current_date_str}.

        ## User's Current Budget Status:
        {context_string}

        ## User's Spending Summary by Category (Current Month):
        {category_summary}

        ## User's Needs vs. Wants Breakdown (Current Month):
        {needs_wants_summary}

        ## Detailed Transaction Data (Newest transactions are at the top):
        This data is crucial for performing calculations and answering specific queries about past spending. Each row represents a single transaction.
        Date,Description,Expense,Category,Type
        {data_string}

        ## Instructions for Analyzing Transaction Data:
        - The transaction data is in CSV format.
        - Columns: 'Date' (YYYY-MM-DD), 'Description', 'Expense' (numerical PLN), 'Category', and 'Type' (Need/Want).
        - You are able to perform calculations (sums, averages, counts) by filtering this data.
        - When asked about specific time periods (e.g., "yesterday", "last week", "this month", "last month", "current week"), use the 'Date' column in conjunction with "Today's Date: {current_date_str}" to determine the relevant date range.
            - For "last week", consider the period from Monday of the previous calendar week to Sunday of the previous calendar week.
            - For "yesterday", refer to the day immediately preceding "Today's Date".
            - For "this month", filter by the month and year of "Today's Date".
        - When asked about spending in specific categories (e.g., "Groceries", "Transport"), refer to the 'Category' column in the detailed transaction data and the 'Monthly Category Summary'.
        - If a question involves multiple criteria (e.g., "how much spent on Wants last week in Shopping"), apply multiple filters to the detailed transaction data.

        The user will now start asking you questions. Respond to their first question with a friendly greeting and confirm you are ready to analyze their detailed budget and spending.
        """

    # TODO: Add type to chat_session
    def send_chat_message(self, chat_session, user_query: str) -> str:
        """
        Sends the user's query to the ongoing Gemini AI chat session
        and returns the natural language response.
        The chat history is managed by the chat_session object itself.
        """
        if not self.model:
            return "Sorry, AI features are not available. Please check the API key configuration."

        logger.info(f"Sending query to AI: '{user_query}'")
        try:
            response = chat_session.send_message(user_query)
            ai_response = response.text
            logger.info("Successfully received AI response.")
            return ai_response
        except Exception as e:
            logger.error(f"An error occurred with the AI model during chat: {e}")
            return "Sorry, I had trouble analyzing that. Please try asking in a different way or start a `/newchat`."

    def get_ai_weekly_digest(self, df_last_week: pd.DataFrame) -> str:
        """
        Analyzes last week's spending and generates a narrative summary using AI.
        This is a one-off prompt, so it creates its own session and prompt.
        """
        if not self.model:
            return (
                "Sorry, AI features are not available. Cannot generate weekly digest."
            )

        logger.info("Generating AI Weekly Digest...")

        if df_last_week.empty:
            return "You had no spending last week. A fresh start!"

        data_string = df_last_week[
            ["Date", "Description", "Expense", "Category", "Type"]
        ].to_csv(index=False)

        prompt = f"""
        You are a financial coach named "Budget Bot".
        Your task is to analyze the user's spending data for last week, provided below in CSV format.
        Write a short, insightful, and encouraging summary in 2-4 sentences.
        
        In your summary, you MUST mention:
        1. The total amount spent last week.
        2. The category with the highest spending.
        3. The Vendor at which the user spent the most.
        4. One area where the user should do better (e.g., high spending in a 'Want' category, a high number of transactions in one place, etc.).

        Conclude with a positive, forward-looking statement for the new week.
        The current date is {pd.to_datetime('today').strftime('%Y-%m-%d')}.

        Here is last week's transaction data:
        ---
        {data_string}
        ---
        """

        try:
            response = self.model.generate_content(prompt)
            ai_response = response.text
            logger.success("Successfully generated AI Weekly Digest.")
            return "✨ *Your AI Weekly Digest is here!* ✨\n\n" + ai_response
        except Exception as e:
            logger.error(
                f"An error occurred with the AI model for the weekly digest: {e}",
                exc_info=True,
            )
            return "Sorry, I had trouble generating your weekly digest."
