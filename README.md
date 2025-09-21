# Personal Budget Agent

## A Telegram bot using LangChain, Gemini and GCP to automate expense tracking and provide AI-driven insights.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-white)](https://www.langchain.com/)
[![Docker](https://img.shields.io/badge/Docker-blue)](https://www.docker.com/)
[![Google Cloud](https://img.shields.io/badge/Google_Cloud-orange)](https://cloud.google.com/)

### Why 
I built this because I wanted to start tracking my expenses but I wanted to do as little of manual work as possible. 
I wanted to have a system always running in the background that would automatically parse my daily banking transaction emails, update my budget and dashboard, allow me to ask questions about my expenses in natural language and provide intelligent insights. I decided to use spreadsheets as the main storage of data because it feels best for a personal project with the ui and easy inspection and editing of data.

<!-- ## Demo 
Disclaimer: I used fake data for this demo.

![Demo] -->


## System Architecture 

### Main Architecture Overview
<img width="50%" height="80%" alt="Untitled diagram _ Mermaid Chart-2025-09-01-171258" src="https://github.com/user-attachments/assets/c98bbe2e-0ea7-4116-9d32-a017c5c2b5c9" />


### Natural Language Querying
<img width="3840" height="1512" alt="Untitled diagram _ Mermaid Chart-2025-09-01-171625" src="https://github.com/user-attachments/assets/b68500f6-2278-4cd8-aab7-470f95c51787" />


### Automated Daily ETL & Analytics Process
<img width="3840" height="1887" alt="Untitled diagram _ Mermaid Chart-2025-09-01-171800" src="https://github.com/user-attachments/assets/cb011c1a-dfa8-4e89-80a5-3bc8e28c7e11" />


### Main Features 

- **Automated ETL Pipeline**: The system runs a fully automated, daily workflow that acts as a ETL (Extract, Transform, Load) pipeline. It successfully:
  - Extracts raw data from mail attachments.
  - Transforms that data from raw html to clean, structured data using a custom parser.
  - Loads the transformed data into Google Sheets, which is the project's database.
- **Agent with tools and short-term memory**: Agent has access to tools and sheets data and responds to natural language queries. Each conversation/chat started with the agent is persisted for the duration of that conversation so the Agent has context of the conversation.
- **Chat commands**:
  - ```code /summary```: runs a query to the agent for summarizing the users current budget status
  - ```code /top5```: asks the agent for top5 merchants by spending for current month
  - ```code /newchat```: initializes new chat with the agent, clearing the memory
    
### Running the project 

#### Prerequisites:
- Docker
- Google Cloud Project with credentials.json
- Telegram Bot Token & Chat ID
- Gemini API Key

1. Create ```.env``` file, copy the contents of ```.env.template``` in there and fill out the variables.
2. Place your credentials.json in the root directory.
3. Authentication:
   The first time you run the container you will have to authenticate.
   ```code
   docker compose run --rm budget-bot
   ```
   This wil print a URL to the console. Open it in your browser, authenticate and authorize the application and a token.json will be created in the root directory which will be used for future runs.
4. Once ```token.json``` exists you can run the container like this in detached mode:
   ```code
   docker compose up -d --build
   ```