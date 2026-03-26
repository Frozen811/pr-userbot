$ErrorActionPreference = "Stop"

# -------- НАСТРОЙКИ --------
$ServerIP     = "100.109.41.95"
$RemoteUser   = "extreme"
$Password     = "ext1"
$BotPath      = "/home/extreme/bot_rass"
$ServiceName  = "bot_rass"
$Branch       = "main"
# ---------------------------

Write-Host ">>> 1) Отправка изменений на GitHub..." -ForegroundColor Cyan
git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "Fix FastAPI TemplateResponse kwargs"
} else {
  Write-Host ">>> Нет изменений для коммита, продолжаем деплой." -ForegroundColor Yellow
}
git push origin $Branch

Write-Host ">>> 2) Копирование .env на сервер..." -ForegroundColor Cyan
scp .env "${RemoteUser}@${ServerIP}:${BotPath}/.env"

Write-Host ">>> 3) Обновление и перезапуск на $ServerIP..." -ForegroundColor Cyan

# Run all remote commands in one line to avoid quoting conflicts with sudo
$SshCommand = "cd $BotPath && git fetch --all && git reset --hard origin/$Branch && source venv/bin/activate && pip install -r requirements.txt && echo '$Password' | sudo -S systemctl restart $ServiceName"

ssh ${RemoteUser}@${ServerIP} $SshCommand

Write-Host ">>> DONE! Bot updated and restarted successfully." -ForegroundColor Green
Write-Host ">>> Admin panel: http://${ServerIP}:8080" -ForegroundColor Cyan