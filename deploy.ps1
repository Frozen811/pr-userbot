$ErrorActionPreference = "Stop"

# -------- НАСТРОЙКИ --------
$ServerIP     = "100.109.41.95"
$RemoteUser   = "extreme"
$Password     = "ext1"
$BotPath      = "/home/extreme/bot_rass"
$ServiceName = "bot_rass"  # Проверь, что твоя служба называется именно так
$Branch       = "main"
# ---------------------------

Write-Host ">>> 1) Отправка изменений на GitHub..." -ForegroundColor Cyan
git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "Deploy update"
} else {
  Write-Host ">>> Нет изменений для коммита, продолжаем деплой." -ForegroundColor Yellow
}
git push origin $Branch

Write-Host ">>> 2) Копирование .env на ноутбук (введи пароль ext1, если попросит)..." -ForegroundColor Cyan
scp .env "${RemoteUser}@${ServerIP}:${BotPath}/.env"

Write-Host ">>> 3) Обновление и перезапуск на $ServerIP (введи пароль ext1, если попросит)..." -ForegroundColor Cyan

$RemoteCommands = @"
set -e

# Переходим в папку бота и жестко подтягиваем свежий код
cd $BotPath
git fetch --all
git reset --hard origin/$Branch

# Активируем виртуальное окружение и обновляем библиотеки
source venv/bin/activate
pip install -r requirements.txt

# Перезапускаем системную службу (автоматически передаем пароль для sudo)
echo "$Password" | sudo -S systemctl restart $ServiceName
"@

$RemoteCommands = $RemoteCommands -replace "`r",""
$RemoteCommands | ssh ${RemoteUser}@${ServerIP} "bash -s"

Write-Host ">>> DONE! Bot updated and restarted successfully." -ForegroundColor Green
Write-Host ">>> Admin panel: http://${ServerIP}:8080" -ForegroundColor Cyan