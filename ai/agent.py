import pandas as pd
from loguru import logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents import AgentExecutor, create_tool_calling_agent

import config
from .agent_tools import create_agent_tools
from auth.google_auth import GoogleAuthenticator


class BudgetAgent:
    """
    Manages interaction with the LangChain agent
    """

    def __init__(self, app_context):
        if not config.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not set")
            self.agent_executor = None
            return
        try:
            self.app_context = app_context

            auth = GoogleAuthenticator()
            creds = auth.get_creds()
            if not creds:
                raise ConnectionError("Failed to get Google credentials for LangChain.")

            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0,  # Lower temp for more predictable tool use
                credentials=creds,
            )

            self.tools = create_agent_tools(app_context)

            system_prompt = f"""
            You are "BudgetBot" an expert financial analyst and money advisor. The current date is {pd.to_datetime("today").strftime("%Y-%m-%d")}.
            Your goal is to help the user by calling your tools and answering the users questions.
            - Use 'get_dashboard_summary' for quick, high-level status checks.
            - Use 'get_filtered_aggregated_data' for any specific or detailed questions about transaction data.
            - Use 'categorize_merchant' to update a merchant's category.
            - Use 'get_weekly_spending_data' to get data for the weekly summary, then write a short, insightful digest based on that data in markdown format.
            Think step-by-step before calling a tool. Respond in a friendly, conversational tone. **When creating lists, use hyphens (-) instead of asterisks (*).** All monetary values are PLN
            """

            # create prompt template to invoke later
            self.prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="chat_history", optional=True),
                    ("human", "{input}"),
                    MessagesPlaceholder(variable_name="agent_scratchpad"),
                ]
            )
            # create the agent
            agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)

            self.agent_executor = AgentExecutor(
                agent=agent, tools=self.tools, verbose=True  # set to False in prod
            )

            self.chat_history: list[HumanMessage | AIMessage] = []
            logger.success("BudgetAgent started.")

        except Exception as e:
            logger.critical(f"Error during BudgetAgent initialization: {e}")
            self.agent_executor = None

    def start_new_chat(self):
        """Starts a new chat session by clearing the history."""
        logger.info("Starting new chat session.")
        self.chat_history = []
        return "New chat started."

    def invoke(self, user_query: str) -> str:
        """
        Sends the user's query to the agent and returns the response.
        Manages chat history for conversational context.
        """
        if not self.agent_executor:
            return "AI agent is not configured correctly."

        try:
            response = self.agent_executor.invoke(
                {"input": user_query, "chat_history": self.chat_history}
            )

            ai_response = response["output"]

            self.chat_history.append(HumanMessage(content=user_query))
            self.chat_history.append(AIMessage(content=ai_response))

            return ai_response
        except Exception as e:
            logger.critical(f"Error during invoke: {e}")
