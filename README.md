# Personal Budget Agent

## A Telegram bot using LangChain, Gemini and GCP to automate expense tracking and provide AI-driven insights.

![Python](https://img.shields.io/badge/Python-3.11-blue) 
![LangChain](https://img.shields.io/badge/LangChain-white) 
![Docker](https://img.shields.io/badge/Docker-blue) 
![Google Cloud](https://img.shields.io/badge/Google_Cloud-orange)

### Why 
I built this because I wanted to start tracking my expenses but I wanted to do as little of manual work as possible. 
I wanted to have a system always running in the background that would automatically parse my daily banking transaction emails, update my budget and dashboard, allow me to ask questions about my expenses in natural language and provide intelligent insights. I decided to use spreadsheets as the main storage of data because it feels best for a personal project with the ui and easy inspection and editing of data.


## Demo 
Disclaimer: I used fake data for this demo.

![Demo]

## System Architecture 

### Main Architecture Overview
```mermaid
---
config:
  layout: elk
---
flowchart TD
 subgraph subGraph0["External Services"]
        Telegram_API["Telegram API"]
        Gmail_API["Gmail API"]
        Google_Sheets_API["Google Sheets API"]
        Google_Gemini_API["Google Gemini API"]
  end
 subgraph subGraph1["Budget Bot Application (Docker Container)"]
        App_Interface["Interface (bot_runner, handlers)"]
        AI_Logic["AI & Logic (agent, tools)"]
        Analytics_ETL["Analytics & ETL (analytics, data_processing)"]
        Services["Services (API wrappers, auth)"]
  end
    User["User"] --> Telegram_API
    Telegram_API --> App_Interface
    App_Interface -- Manages --> AI_Logic
    App_Interface -- Schedules --> Analytics_ETL
    AI_Logic -- Uses --> Services
    Analytics_ETL -- Uses --> Services
    Services --> Gmail_API & Google_Sheets_API & Telegram_API & Google_Gemini_API

```

### Natural Language Querying
===

```mermaid
sequenceDiagram
    participant User
    participant Telegram
    participant Handlers as telegram_handlers.py
    participant Agent as ai/agent.py
    participant Gemini as Gemini LLM
    participant Tools as agent_tools.py
    participant GSS as GoogleSheetsService

    User->>Telegram: Sends message ("How much did I spend on groceries?")
    Telegram->>Handlers: handle_text_query(update)
    Handlers->>Agent: invoke(user_query)
    Agent->>Gemini: Prompt with query & available tools
    Gemini-->>Agent: Decision: Must use 'get_filtered_aggregated_data' tool
    Agent->>Tools: execute('get_filtered_aggregated_data', filters=[...])
    Tools->>GSS: load_expenses_dataframe()
    GSS-->>Tools: Returns pandas DataFrame
    Note right of Tools: Filters DataFrame for 'Groceries'<br/>and sums 'Expense' column
    Tools-->>Agent: Returns result as text ("Total: 123.45 PLN")
    Agent->>Gemini: Prompt with tool result ("The data is: 'Total: 123.45 PLN'. Formulate a friendly response.")
    Gemini-->>Agent: Generates final response ("You spent 123.45 PLN on groceries this month.")
    Agent-->>Handlers: Returns final response text
    Handlers->>Telegram: send_message(response_text)
    Telegram-->>User: Displays final answer
```

### Automated Daily ETL & Analytics Process
```mermaid
sequenceDiagram
    participant Scheduler
    participant DailyTaskRunner
    participant EmailProcessor
    participant GmailService
    participant Parser
    participant GoogleSheetsService
    participant AnomalyDetector
    participant DashboardUpdater
    participant TelegramService

    Scheduler->>DailyTaskRunner: Trigger daily run
    DailyTaskRunner->>EmailProcessor: Process new transactions
    EmailProcessor->>GmailService: Get new emails
    GmailService-->>EmailProcessor: Email list
    EmailProcessor->>Parser: Parse attachments from emails
    Parser-->>EmailProcessor: Transaction data
    EmailProcessor->>GoogleSheetsService: Append new transactions
    EmailProcessor->>TelegramService: Notify: "Transactions added"

    DailyTaskRunner->>AnomalyDetector: Check for spending anomalies
    AnomalyDetector->>GoogleSheetsService: Load expense data
    AnomalyDetector-->>DailyTaskRunner: Anomaly reports
    DailyTaskRunner->>TelegramService: Send anomaly alerts

    DailyTaskRunner->>DashboardUpdater: Update dashboard
    DashboardUpdater->>GoogleSheetsService: Calculate metrics & update sheet
    DashboardUpdater-->>DailyTaskRunner: Update successful

    DailyTaskRunner->>TelegramService: Notify: "Daily run finished"

```
### Main Features 

### Running the project 


