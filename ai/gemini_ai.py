import pandas as pd

from loguru import logger
import google.generativeai as genai

import config
from ai_tools import AgentTools


class GeminiAI:
    """
    Manages interaction with the Gemini AI model for budget analysis and chat.
    """

    def __init__(
        self, app_context, api_key=config.GEMINI_API_KEY, model_name="gemini-2.5-flash"
    ):
        if not config.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not found")
            self.model = None
            return

        genai.configure(api_key=config.GEMINI_API_KEY)
        self.tools = AgentTools(app_context)

        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=[
                self.tools.get_dashboard_summary,
                self.tools.execute_pandas_query,
                self.tools.categorize_merchant,
                self.tools.generate_weekly_digest,
            ],
            system_instruction=f"""
            You are "Budget Bot," an expert financial analyst. The current date is {pd.to_datetime("today").strftime("%Y-%m-%d")}.
            Your goal is to help the user by calling your tools.
            - Use 'get_dashboard_summary' for quick, high-level status checks.
            - Use 'get_filtered_aggregated_data' for any specific or detailed questions about transaction data. The DataFrame has columns: ['Date', 'Description', 'Expense', 'Income', 'Category', 'Type']. You MUST call this tool with structured arguments for filtering, grouping, and aggregation. DO NOT try to write pandas code. For example, to find top 5 grocery expenses, you would call it with filters=[{{'column': 'Category', 'operator': '==', 'value': 'Groceries'}}], sort_by='Expense', head=5.
            - Use 'categorize_merchant' to update a merchant's category.
            - Use 'get_weekly_spending_data' to get the data for the weekly summary, then write a short, insightful digest based on that data in markdown format.
            Think step-by-step before calling a tool. Respond in a friendly, conversational tone.
            """,
        )
        logger.info(f"Agent configured.")

    def start_new_chat(self) -> genai.ChatSession:
        """Starts a new chat session."""
        if not self.model:
            return None
        return self.model.start_chat(enable_automatic_function_calling=True)

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
