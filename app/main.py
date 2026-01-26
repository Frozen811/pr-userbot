import os
import asyncio
import logging
import random
import gc
from datetime import datetime, timedelta
import pytz
from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, SlowModeWaitError, ChatRestrictedError
from dotenv import load_dotenv
from app import database, web_server

# Настройка
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = "user_session"
TZ = pytz.timezone('Europe/Kyiv')

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pr_userbot")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def log(text):
    """Отправляет лог в консоль, на сайт и в Telegram канал"""
    # 1. Время для лога
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    full_text = f"[{timestamp}] {text}"

    # 2. В консоль
    print(full_text)

    # 3. В Веб-админку (в память)
    if "logs" in web_server.bot_state:
        web_server.bot_state["logs"].append(full_text)
        if len(web_server.bot_state["logs"]) > 100:
            web_server.bot_state["logs"].pop(0)

    # 4. В Телеграм канал (если задан в настройках)
    try:
        settings = await database.get_settings()
        log_channel = settings.get('log_channel_id')
        if log_channel:
            await client.send_message(int(log_channel), text)
    except Exception:
        pass


async def broadcast_loop():
    """Главный цикл рассылки"""
    await log("🚀 Broadcast loop started. Waiting for tasks...")

    while True:
        try:
            # Обновляем uptime для сайта
            web_server.bot_state["uptime"] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

            # 1. Получаем настройки из БД
            settings = await database.get_settings()
            DAILY_LIMIT = int(settings.get('daily_limit', 400))
            BROADCAST_TEXT = settings.get('broadcast_text', "Привет! Настрой текст через .set")

            # Обновляем статистику на сайте
            total = await database.get_stat('total_sent')
            web_server.bot_state["total_sent"] = int(total) if total else 0

            # 2. Проверяем ВРЕМЯ (Киев)
            now = datetime.now(TZ)
            hour = now.hour
            is_weekend = now.weekday() >= 5

            # --- НОЧНОЙ РЕЖИМ (С 22:00 до 07:00) ---
            if hour >= 22 or hour < 7:
                await log(f"🌙 Night Mode ({hour}:00). Sleeping 30 mins...")
                await asyncio.sleep(1800)  # Спим 30 минут
                continue

            # --- ЛАЙТ РЕЖИМ (Утро) ---
            # Будни: до 14:00, Выходные: до 12:00
            if (hour < 14 and not is_weekend) or (hour < 12 and is_weekend):
                delay_range = (60, 120)  # Медленно
                mode_name = "Light 🌤"
            else:
                delay_range = (30, 60)  # Быстро
                mode_name = "Normal 🚀"

            # 3. Получаем чаты
            chats = await database.get_chats()
            if not chats:
                await log("⚠️ No chats in DB. Add some via .add! Sleeping 5 mins.")
                await asyncio.sleep(300)
                continue

            # 4. Рассылка по списку
            sent_in_cycle = 0

            for chat in chats:
                chat_id = chat['chat_id']
                chat_name = chat['chat_name']

                # Проверка Mute/Slowmode
                if chat['next_run_at']:
                    unlock_time = datetime.fromisoformat(chat['next_run_at'])
                    if datetime.now() < unlock_time:
                        continue  # Рано писать
                    else:
                        await database.update_chat_status(chat_id, "active")  # Разбан

                # Проверка лимита
                current_daily = web_server.bot_state.get("daily_sent", 0)
                if current_daily >= DAILY_LIMIT:
                    await log("🛑 Daily limit reached. Sleeping until tomorrow...")
                    await asyncio.sleep(3600)
                    break

                try:
                    await client.send_read_acknowledge(chat_id)  # Читаем
                    await client.send_message(chat_id, BROADCAST_TEXT)  # Пишем

                    # Успех
                    sent_in_cycle += 1
                    current_total = web_server.bot_state["total_sent"] + 1
                    web_server.bot_state["total_sent"] = current_total
                    # Тут можно добавить логику счетчика на сегодня, пока просто +1
                    web_server.bot_state["daily_sent"] = web_server.bot_state.get("daily_sent", 0) + 1

                    await database.update_stat('total_sent', current_total)

                    await log(f"✅ [{mode_name}] Sent to: {chat_name}")
                    gc.collect()  # Чистим память

                    # Пауза между сообщениями
                    sleep_time = random.randint(*delay_range)
                    await asyncio.sleep(sleep_time)

                except ChatWriteForbiddenError:
                    await log(f"🚫 Banned in {chat_name}. Deleting.")
                    await database.remove_chat(chat_id)
                    try:
                        await client.delete_dialog(chat_id)
                    except:
                        pass

                except SlowModeWaitError as e:
                    wait_sec = e.seconds + 10
                    unlock = datetime.now() + timedelta(seconds=wait_sec)
                    await log(f"⏳ Slowmode {chat_name}: {wait_sec}s")
                    await database.update_chat_status(chat_id, "muted", next_run_at=unlock.isoformat(),
                                                      last_error=f"Slow {wait_sec}s")

                except ChatRestrictedError:
                    unlock = datetime.now() + timedelta(hours=2)
                    await log(f"🔇 Muted {chat_name}. Skip 2h.")
                    await database.update_chat_status(chat_id, "muted", next_run_at=unlock.isoformat(),
                                                      last_error="Muted")

                except Exception as e:
                    await log(f"❌ Error {chat_name}: {e}")
                    await database.update_chat_status(chat_id, "error", last_error=str(e))

            # Конец круга
            if sent_in_cycle > 0:
                await log(f"🏁 Cycle finished. Sent: {sent_in_cycle}. Sleeping 20 mins...")
                await asyncio.sleep(1200)
            else:
                await log("💤 No active chats or nothing sent. Sleeping 5 mins...")
                await asyncio.sleep(300)

        except Exception as e:
            # Если ошибка в самом цикле — пишем её и не падаем!
            await log(f"🔥 CRITICAL LOOP ERROR: {e}")
            await asyncio.sleep(60)


# --- КОМАНДЫ ---
@client.on(events.NewMessage(outgoing=True, pattern=r'\.set (.+)'))
async def set_text(event):
    text = event.pattern_match.group(1)
    await database.update_stat('broadcast_text', text)
    await event.edit("✅ Text updated in DB!")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.add'))
async def add_chat_cmd(event):
    chat = await event.get_chat()
    if await database.add_chat(chat.id, chat.title):
        await event.edit(f"✅ Added: {chat.title}")
    else:
        await event.edit("⚠️ Already added.")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.stats'))
async def stats_cmd(event):
    total = await database.get_stat('total_sent')
    chats = await database.get_chats()
    await event.edit(f"📊 **Stats:**\nChats: {len(chats)}\nTotal Sent: {total or 0}")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.setlog'))
async def set_log_cmd(event):
    await database.update_stat('log_channel_id', event.chat_id)
    await event.edit(f"✅ Log Channel Set: {event.chat.title}")


async def main():
    await database.init_db()
    await client.start()
    asyncio.create_task(web_server.run_server())
    asyncio.create_task(broadcast_loop())
    await client.run_until_disconnected()


if __name__ == '__main__':
    client.loop.run_until_complete(main())