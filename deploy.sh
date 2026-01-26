#!/bin/bash

# --- НАСТРОЙКИ ---
SERVER_IP="46.101.251.219"
BOT_PATH="/root/pr-userbot"
BRANCH="main"
# -----------------

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. GitHub Push
echo -e "${CYAN}>>> 1. Pushing to GitHub...${NC}"
git add .
git commit -m "Auto-deploy update"
git push origin $BRANCH

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Git push failed!${NC}"
    exit 1
fi

# 2. Server Update + Docker Restart
echo -e "${CYAN}>>> 2. Connecting to Droplet (Docker)...${NC}"

# Эта команда: заходит в папку -> качает код -> пересобирает контейнер
REMOTE_COMMANDS="cd $BOT_PATH && git pull origin $BRANCH && docker-compose down && docker-compose up -d --build"

ssh root@$SERVER_IP "$REMOTE_COMMANDS"

echo -e "${GREEN}>>> DONE! Bot is updated and running in Docker.${NC}"
echo -e "${CYAN}>>> Admin Panel: http://admin.extr3me.me:8080${NC}"
echo " "
echo -e "${YELLOW}>>> 3. LIVE LOGS (For QR Code or Errors)${NC}"
echo -e "${YELLOW}>>> NOTE: Press CTRL+C to stop watching logs.${NC}"
echo -e "${YELLOW}>>>       The bot will CONTINUE running in the background!${NC}"
echo " "
sleep 2
ssh -t root@$SERVER_IP "docker logs -f telegram_userbot"
