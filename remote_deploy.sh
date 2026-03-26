#!/bin/bash
set -e

BOT_PATH="/home/extreme/bot_rass"
SERVICE="bot_rass"
BRANCH="main"
PASSWORD="ext1"

echo "==> Pulling latest code..."
cd "$BOT_PATH"
git fetch --all
git reset --hard origin/$BRANCH

echo "==> Installing dependencies..."
source "$BOT_PATH/venv/bin/activate"
pip install -q -r "$BOT_PATH/requirements.txt"

echo "==> Restarting service..."
echo "$PASSWORD" | sudo -S systemctl restart "$SERVICE"

sleep 2

if systemctl is-active --quiet "$SERVICE"; then
    echo "==> SERVICE IS RUNNING OK"
else
    echo "==> SERVICE FAILED! Logs:"
    journalctl -u "$SERVICE" -n 30 --no-pager
fi
