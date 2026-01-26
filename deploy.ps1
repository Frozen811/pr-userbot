# --- НАСТРОЙКИ ---
$ServerIP = "46.101.251.219"
$BotPath = "/root/pr-userbot"
$Branch = "main"
# -----------------

# 1. GitHub Push
Write-Host ">>> 1. Pushing to GitHub..." -ForegroundColor Cyan
git add .
git commit -m "Auto-deploy update"
git push origin $Branch

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Git push failed!" -ForegroundColor Red
    exit
}

# 2. Server Update + Docker Restart
Write-Host ">>> 2. Connecting to Droplet (Docker)..." -ForegroundColor Cyan

# Мы используем 'docker compose' (новый стандарт) или 'docker-compose' (старый).
# Эта команда: заходит в папку -> качает код -> пересобирает контейнер в фоне
$RemoteCommands = "cd $BotPath && git pull origin $Branch && docker-compose down && docker-compose up -d --build"

ssh root@$ServerIP $RemoteCommands

Write-Host ">>> DONE! Bot is updated and running in Docker." -ForegroundColor Green
Write-Host ">>> Admin Panel: http://admin.extr3me.me:8080" -ForegroundColor Cyan
Write-Host ">>> 3. Fetching logs (Scan QR Code below)..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
ssh -t root@$ServerIP "docker logs -f telegram_userbot"

