from os import getenv
from dotenv import load_dotenv

load_dotenv()

# File Paths
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
ATTACHMENTS_DIR = "attachments"
LOG_FILE = "app.log"

# Google API Scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language.retriever",
]

# Google Sheets
SPREADSHEET_NAME = "Budget & Expenses Tracker"
WORKSHEETS = {
    "expenses": "Sheet1",
    "budget": "Budget",
    "categories": "Categories",
    "history": "History",
}
NAMED_RANGES = {
    "monthly_income": "MonthlyIncome",
    "budget_summary": "BudgetSummary",
    "dashboard_sidepanel": "DashboardSidePanel",
}
EXPENSE_HEADER = [
    "Time",
    "Description",
    "Expense",
    "Income",
    "Balance",
    "Date",
    "Category",
    "Type",
]
DF_COLUMNS = ["Date", "Description", "Expense", "Category", "Type"]

# Email
EMAIL_SENDER = "mBank"

# Telegram
TELEGRAM_BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = getenv("TELEGRAM_CHAT_ID")

# AI
GEMINI_API_KEY = getenv("GEMINI_API_KEY")

# Anomaly Detection
ANOMALY_THRESHOLD = 2.0
MIN_SPEND_ALERT = 50.0
MIN_WEEKS_DATA = 4
ARCHIVE_DAYS = 4  # Archive on first 4 days of month
