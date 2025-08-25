#!/bin/bash

echo "Starting Telegram bot..."
python bot_runner.py &

sleep 5

# Loop indefinitely to run the budget script once a day
while true; do
    echo "Running daily budget script..."
    python main.py
    echo "Budget script finished. Sleeping for 24 hours."
    sleep 86400 # 86400 seconds = 24 hours
done