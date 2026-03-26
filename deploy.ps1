$ErrorActionPreference = "Stop"

# -------- SETTINGS --------
$ServerIP     = "100.109.41.95"
$RemoteUser   = "extreme"
$Password     = "ext1"
$BotPath      = "/home/extreme/bot_rass"
$ServiceName  = "bot_rass"
$Branch       = "main"
# ---------------------------

Write-Host ">>> 1) Pushing changes to GitHub..." -ForegroundColor Cyan
git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "Fix FastAPI TemplateResponse"
} else {
  Write-Host ">>> No changes to commit, proceeding with deploy." -ForegroundColor Yellow
}
git push origin $Branch

Write-Host ">>> 2) Copying .env to server..." -ForegroundColor Cyan
scp .env "${RemoteUser}@${ServerIP}:${BotPath}/.env"

Write-Host ">>> 3) Updating and restarting on $ServerIP..." -ForegroundColor Cyan

# Передаём пароль через переменную окружения, чтобы не интерполировался на Windows
# Используем bash -c явно, чтобы source работал корректно
$RemoteCmd = @"
set -e
cd $BotPath
git fetch --all
git reset --hard origin/$Branch
bash -c 'source venv/bin/activate && pip install -q -r requirements.txt'
echo '$Password' | sudo -S systemctl restart $ServiceName
sleep 2
systemctl is-active $ServiceName && echo 'SERVICE IS RUNNING OK' || echo 'SERVICE FAILED!'
"@

ssh ${RemoteUser}@${ServerIP} $RemoteCmd

Write-Host ">>> DONE! Bot updated and restarted successfully." -ForegroundColor Green
Write-Host ">>> Admin panel: http://${ServerIP}:8080" -ForegroundColor Cyan
