# --- НАСТРОЙКИ (Твой Дроплет) ---
$ServerIP = "46.101.251.219"      # Твой IP
$BotPath = "/root/pr-userbot"     # Путь на сервере
$Branch = "main"                  # Твоя ветка (main или master)
# --------------------------------

# 1. Отправляем изменения на GitHub (Локально)
Write-Host ">>> 1. Pushing to GitHub..." -ForegroundColor Cyan
git add .
git commit -m "Auto-deploy update"
git push origin $Branch

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Git push failed!" -ForegroundColor Red
    exit
}

# 2. Обновляем сервер + Docker Build (Удаленно)
Write-Host ">>> 2. Connecting to Droplet $ServerIP (Docker Deploy)..." -ForegroundColor Cyan

# Логика:
# 1. cd -> идем в папку
# 2. git pull -> качаем код
# 3. docker-compose down -> останавливаем старый контейнер (чтобы освободить файл сессии)
# 4. docker-compose up -d --build -> собираем и запускаем новый
$RemoteCommands = "cd $BotPath && git pull origin $Branch && docker-compose down && docker-compose up -d --build"

ssh root@$ServerIP $RemoteCommands

Write-Host ">>> DONE! Docker container rebuilt and started." -ForegroundColor Green