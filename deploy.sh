#!/bin/bash

# Configuration
DROPLET_USER="root"
DROPLET_IP="46.101.251.219"
PROJECT_DIR="~/pr-userbot"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Git Push
echo -e "${CYAN}>>> 1. Pushing to GitHub...${NC}"
git add .
git commit -m "Auto-deploy update"
git push origin main

# 2. SSH into Droplet and Deploy
echo -e "${CYAN}>>> 2. Connecting to Droplet (Docker)...${NC}"
ssh $DROPLET_USER@$DROPLET_IP << EOF
    mkdir -p $PROJECT_DIR
    cd $PROJECT_DIR

    echo ">>> Pulling latest changes..."
    git pull origin main

    echo ">>> Rebuilding Docker containers..."
    docker-compose down --remove-orphans
    docker-compose up -d --build

    echo ">>> Pruning unused images..."
    docker image prune -f
EOF

echo -e "${GREEN}>>> DONE! Bot is updated and running.${NC}"
echo -e "${CYAN}>>> Admin Panel: http://$DROPLET_IP:8080 (Wait 10-20s for the container to start)${NC}"
echo " "
echo -e "${YELLOW}>>> 3. LIVE LOGS (For QR Code or Errors)${NC}"
echo -e "${YELLOW}>>> NOTE: Press CTRL+C to stop watching logs.${NC}"
echo -e "${YELLOW}>>>       The bot will CONTINUE running in the background!${NC}"
echo " "
sleep 2
ssh -t $DROPLET_USER@$DROPLET_IP "docker logs -f telegram_userbot"
