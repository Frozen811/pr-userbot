# --- НАСТРОЙКИ ---
$ServerIP = "46.101.251.219"
# -----------------

Write-Host ">>> Connecting to Remote Logs..." -ForegroundColor Cyan
Write-Host ">>> Press CTRL+C to exit log viewer (Bot stays online)." -ForegroundColor Yellow
ssh -t root@$ServerIP "docker logs -f --tail 100 telegram_userbot"
