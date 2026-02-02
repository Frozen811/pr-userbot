$ErrorActionPreference = "Stop"

# -------- НАСТРОЙКИ --------
$ServerIP     = "64.226.96.158"
$BotPath      = "/opt/bots/pr-userbot"
$BotsRoot     = "/opt/bots"
$ServiceName  = "pr-userbot"
$Branch       = "main"
$KeyPath      = "$env:USERPROFILE\.ssh\id_ed25519_do"
# ---------------------------

Write-Host ">>> 1) Pushing changes to GitHub..." -ForegroundColor Cyan
git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "Deploy $ServiceName"
} else {
  Write-Host ">>> No changes to commit." -ForegroundColor Yellow
}
git push origin $Branch

Write-Host ">>> 2) Copying .env to server..." -ForegroundColor Cyan
scp -i "$KeyPath" -o IdentitiesOnly=yes .env "root@${ServerIP}:${BotPath}/.env"

Write-Host ">>> 3) Deploying on server $ServerIP..." -ForegroundColor Cyan

$RemoteCommands = @"
set -e

cd $BotPath
git fetch --all
git reset --hard origin/$Branch

cd $BotsRoot
docker compose build $ServiceName
docker compose up -d $ServiceName
docker compose ps $ServiceName
docker compose logs --tail=120 $ServiceName
"@

$RemoteCommands = $RemoteCommands -replace "`r",""
ssh -i "$KeyPath" -o IdentitiesOnly=yes root@$ServerIP "bash -lc '$RemoteCommands'"

Write-Host ">>> DONE! $ServiceName updated and restarted." -ForegroundColor Green
Write-Host ">>> Admin Panel: http://admin.extr3me.me:8080" -ForegroundColor Cyan