# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY entrypoint.sh .

RUN chmod +x entrypoint.sh

RUN mkdir -p /app/attachments
# --- How to run this container ---
#
# 1. Build the Docker image:
#    docker build -t budget-bot .
#
# 2. Run the Docker container, providing credentials and environment variables:
#    docker run -d --name my-budget-bot \
#      -v C:\path\to\your\credentials.json:/app/credentials.json \
#      -v C:\path\to\your\token.json:/app/token.json \
#      -v C:\path\to\your\attachments:/app/attachments \
#      -e GEMINI_API_KEY="YOUR_GEMINI_API_KEY" \
#      -e TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN" \
#      -e TELEGRAM_CHAT_ID="YOUR_TELEGRAM_CHAT_ID" \
#      budget-bot
#

# Command to run the bot when the container launches
ENTRYPOINT ["./entrypoint.sh"]