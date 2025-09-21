import pandas as pd
from loguru import logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents import AgentExecutor, create_tool_calling_agent

import config
from .agent_tools import create_agent_tools
from .df_toolkit import DataFrameToolkit
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

            quick_tools = create_agent_tools(app_context)

            analytics_session = DataFrameToolkit(app_context["expense_data_manager"])
            advanced_tools = [
                analytics_session.load_data,
                analytics_session.filter_data,
                analytics_session.sort_data,
                analytics_session.group_and_aggregate,
                analytics_session.show_data,
            ]

            self.tools = quick_tools + advanced_tools

            system_prompt = f"""
            You are "BudgetBot", a budget tracking agent that analyzes transactions and helps with decisions and saving money. The current date is {pd.to_datetime("today").strftime("%Y-%m-%d")}.
            Your goal is to answer user questions by thinking step-by-step and using your tools efficiently.

            ---
            ### Tool Usage Strategy

            You have two types of tools: **Quick Tools** and the **Advanced Analyst Toolkit**.
            **Your primary rule is to ALWAYS try to use a Quick Tool first.** They are faster and more reliable for common questions.

            **1. QUICK TOOLS (Use these first!)**
            - `get_dashboard_summary`: Use for general status checks like "How am I doing?".
            - `get_monthly_spending_summary`: Use for any question about a specific month's performance, like "How was last month?" or "Show me my top merchants in August."
            - `get_weekly_spending_data`: Use to get a summary of last week's spending.
            - `categorize_merchant`: Use to update a merchant's category.

            **2. ADVANCED ANALYST TOOLKIT (Use as a last resort)**
            If, and ONLY IF, a question is too complex for any Quick Tool (e.g., comparing multiple categories, multi-step filtering), you must use the advanced toolkit. The workflow is ALWAYS: **Load -> Modify -> Show**.

            ---
            ### Detailed Advanced Workflow Example

            Here is how you should think when using the Advanced Toolkit.

            **User Query:** "Compare how much I spent on 'Groceries' versus 'Restaurants' last month."

            **Your Thought Process:**
            1. The user wants a comparison between two specific categories for last month. No Quick Tool can do this. I must use the Advanced Analyst Toolkit.
            2. First, I must load the data into my workspace.
            3. Next, I need to filter the data to only include transactions from last month. I will do this with two date filters.
            4. Then, I need to isolate only the 'Groceries' and 'Restaurants' categories. The 'isin' operator is perfect for this.
            5. Now that I have the correct data, I need to group it by 'Category' and sum the 'Expense' to get the totals for each.
            6. Finally, I will show the resulting summary table to the user.

            **Resulting Tool Calls:**
            1. `load_data()`
            2. `filter_data(column='Date', operator='>=', value='2025-08-01')`
            3. `filter_data(column='Date', operator='<=', value='2025-08-31')`
            4. `filter_data(column='Category', operator='isin', value=['Groceries', 'Restaurants'])`
            5. `group_and_aggregate(group_by=['Category'], aggregations={{'Expense': 'sum'}})`
            6. `show_data()`
            ---
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
