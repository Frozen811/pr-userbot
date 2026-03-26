$ErrorActionPreference = "Stop"

# -------- SETTINGS --------
$ServerIP     = "100.109.41.95"
$RemoteUser   = "extreme"
$BotPath      = "/home/extreme/bot_rass"
$ServiceName  = "bot_rass"
$Branch       = "main"
# ---------------------------

Write-Host ">>> 1) Pushing changes to GitHub..." -ForegroundColor Cyan
git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "Auto deploy"
} else {
  Write-Host ">>> No changes to commit, proceeding with deploy." -ForegroundColor Yellow
}
git push origin $Branch

Write-Host ">>> 2) Copying .env and deploy script to server..." -ForegroundColor Cyan
scp .env "${RemoteUser}@${ServerIP}:${BotPath}/.env"
scp remote_deploy.sh "${RemoteUser}@${ServerIP}:/home/${RemoteUser}/remote_deploy.sh"

Write-Host ">>> 3) Running deploy on $ServerIP..." -ForegroundColor Cyan
ssh "${RemoteUser}@${ServerIP}" "chmod +x ~/remote_deploy.sh && bash ~/remote_deploy.sh"

Write-Host ">>> DONE!" -ForegroundColor Green
Write-Host ">>> Admin panel: http://${ServerIP}:8080" -ForegroundColor Cyan
