@echo off
rem This script runs the Personal Finance Tracker's main daily workflow.

rem Navigate to the project root directory
cd /d "C:\Rzeczy\jwojci\budget-1.0"

rem >>> IMPORTANT: Set your environment variables below. <<<
rem >>> Ensure there are NO SPACES around the '=' sign, and NO SPACES after the '=' sign. <<<
rem >>> Replace 'YOUR_ACTUAL_VALUE_HERE' with your exact tokens and IDs. <<<

set TELEGRAM_BOT_TOKEN=8170922411:AAHQZFqDAt_DAoTC_nQQeaEby5XETtYFdC8
set TELEGRAM_CHAT_ID=1301280361
set GEMINI_API_KEY=AIzaSyDCqV_aMSAiWxUSpRGPVjOjd2PeusCkvs0

rem Optional: Verify environment variables are set before running Python
echo Verifying environment variables:
echo TELEGRAM_BOT_TOKEN: %TELEGRAM_BOT_TOKEN%
echo TELEGRAM_CHAT_ID: %TELEGRAM_CHAT_ID%
echo GEMINI_API_KEY: %GEMINI_API_KEY%
echo.

rem Activate virtual environment (ensure this path is correct for your setup)
rem Call the activate.bat script, do NOT just set PYTHONHOME or PATH manually
call .venv\Scripts\activate.bat

rem Run the Python script, redirecting all output (stdout and stderr) to script_output.log
.venv\Scripts\python.exe main.py >> script_output.log 2>&1

rem Optional: Keep the command prompt window open after execution (for debugging)
rem pause