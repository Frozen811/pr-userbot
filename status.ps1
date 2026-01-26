# --- НАСТРОЙКИ ---
$ServerIP = "46.101.251.219"
# -----------------

Write-Host ">>> Checking Bot Status..." -ForegroundColor Cyan
ssh -t root@$ServerIP "docker ps | grep telegram_userbot"
Write-Host " "
Write-Host ">>> If you see the container above, it's running." -ForegroundColor Green
