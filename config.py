import os
from dotenv import load_dotenv

load_dotenv()

# --- File Paths ---
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
ATTACHMENTS_DIR = "attachments"
LOG_FILE = "app.log"  # Centralized log file name

# --- Google API Scopes ---
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language.retriever",
]

# --- Google Sheets Config ---
SPREADSHEET_NAME = "Budget & Expenses Tracker"
EXPENSES_WORKSHEET_NAME = "Sheet1"
BUDGET_WORKSHEET_NAME = "Budget"
CATEGORIES_WORKSHEET_NAME = "Categories"
HISTORY_WORKSHEET_NAME = "History"  # Added for clarity in MonthlyArchiver

# --- Google Sheets Named Ranges ---
# These names must match the named ranges defined in the spreadsheet.
NR_MONTHLY_INCOME = "MonthlyIncome"
NR_BUDGET_SUMMARY = "BudgetSummary"
NR_DASHBOARD_SIDEPANEL = "DashboardSidePanel"

# Expected header for Expenses worksheet
EXPECTED_EXPENSE_HEADER = [
    "Time",
    "Description",
    "Expense",
    "Income",
    "Balance",
    "Date",
    "Category",
    "Type",
]
# Expected columns for DataFrames in general processing
REQUIRED_DF_COLUMNS = ["Date", "Description", "Expense", "Category", "Type"]


# --- Email Config ---
EMAIL_SENDER = "mBank"

# --- Telegram Config ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)  # It's better to get this from env or a DB for production

# --- AI Config ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Anomaly Detection Config ---
ANOMALY_THRESHOLD = 2.0
MINIMUM_SPEND_FOR_ALERT = 50.0
MINIMUM_WEEKS_OF_DATA = 4

MONTHLY_ARCHIVE_RUN_DAYS = 4  # Run archiving on the first 4 days of the month
