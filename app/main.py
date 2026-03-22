import asyncio
import logging
import random
import os
import sys
import qrcode
from datetime import datetime
from pytz import timezone
import gc
from typing import Any, Awaitable, Callable, Optional

from telethon import TelegramClient, events
from telethon import functions, types
from telethon.errors import (
    FloodWaitError, PeerIdInvalidError, ChatWriteForbiddenError,
    SlowModeWaitError, ChatRestrictedError, UserBannedInChannelError,
    SessionPasswordNeededError, PasswordHashInvalidError
)
from telethon.extensions import html

from app import config, database, web_server, spintax

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def log(message):
    logger.info(message)
    web_server.add_log(f"{datetime.now().strftime('%H:%M:%S')} - {message}")

# --- Constants ---
SESSION_PATH = 'sessions/user_session' # Telethon adds .session automatically
TZ_KYIV = timezone('Europe/Kyiv')

# --- Client Init ---
client = TelegramClient(SESSION_PATH, config.API_ID, config.API_HASH)


def _extract_chatlist_slug(folder_url: str) -> str:
    url = (folder_url or "").strip()
    if not url:
        raise ValueError("Ссылка на папку не указана.")

    if "t.me/addlist/" in url:
        slug = url.split("t.me/addlist/", 1)[1]
    elif "telegram.me/addlist/" in url:
        slug = url.split("telegram.me/addlist/", 1)[1]
    else:
        slug = url

    slug = slug.split("?", 1)[0].split("#", 1)[0].strip("/").strip()
    if not slug:
        raise ValueError("Невалидная ссылка папки Telegram. Ожидается t.me/addlist/...")
    return slug


def _chat_title(chat_obj) -> str:
    title = getattr(chat_obj, "title", None)
    if title:
        return title
    first_name = getattr(chat_obj, "first_name", "") or ""
    last_name = getattr(chat_obj, "last_name", "") or ""
    full_name = (f"{first_name} {last_name}").strip()
    if full_name:
        return full_name
    username = getattr(chat_obj, "username", None)
    if username:
        return f"@{username}"
    return f"chat_{getattr(chat_obj, 'id', 'unknown')}"


async def import_folder_chats(
    folder_url: str,
    progress_cb: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None
) -> dict[str, Any]:
    """
    Imports chats from Telegram chat-folder invite link (t.me/addlist/...).
    Uses CheckChatlistInviteRequest first, then JoinChatlistInviteRequest.
    """
    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        raise RuntimeError("Telegram client is not authorized yet.")

    slug = _extract_chatlist_slug(folder_url)

    # 1) Inspect folder invite without joining.
    invite_info = await client(functions.chatlists.CheckChatlistInviteRequest(slug=slug))

    chats: list[Any] = []
    peers_to_join: list[Any] = []
    already_joined = False

    if isinstance(invite_info, types.chatlists.ChatlistInvite):
        chats = list(getattr(invite_info, "chats", []) or [])
        peers_to_join = list(getattr(invite_info, "peers", []) or [])
    elif isinstance(invite_info, types.chatlists.ChatlistInviteAlready):
        chats = list(getattr(invite_info, "chats", []) or [])
        peers_to_join = list(getattr(invite_info, "missing_peers", []) or [])
        already_joined = not bool(peers_to_join)
    else:
        raise RuntimeError("Не удалось обработать приглашение папки.")

    # 2) Join chat-folder invite using the peers returned by check request.
    if peers_to_join:
        input_peers = []
        for peer in peers_to_join:
            try:
                input_peers.append(await client.get_input_entity(peer))
            except Exception:
                continue

        if input_peers:
            await client(functions.chatlists.JoinChatlistInviteRequest(slug=slug, peers=input_peers))

    total = len(chats)
    added = 0
    duplicates = 0
    errors: list[str] = []

    for idx, chat in enumerate(chats, start=1):
        try:
            chat_id = int(chat.id)
            title = _chat_title(chat)
            is_added = await database.add_chat(chat_id, title)
            if is_added:
                added += 1
            else:
                duplicates += 1

            if progress_cb:
                await progress_cb({
                    "processed": idx,
                    "total": total,
                    "chat_id": chat_id,
                    "chat_title": title,
                    "added": is_added,
                    "already_joined": already_joined
                })
        except Exception as exc:
            errors.append(str(exc))
            if progress_cb:
                await progress_cb({
                    "processed": idx,
                    "total": total,
                    "chat_id": None,
                    "chat_title": None,
                    "added": False,
                    "error": str(exc),
                    "already_joined": already_joined
                })

        # Anti-flood pause while saving chats to DB.
        await asyncio.sleep(0.8)

    return {
        "slug": slug,
        "total": total,
        "added": added,
        "duplicates": duplicates,
        "errors": errors,
        "already_joined": already_joined
    }

# --- Commands ---

@client.on(events.NewMessage(outgoing=True, pattern=r'\.setmedia(.*)'))
async def cmd_setmedia(event):
    args = event.pattern_match.group(1).strip()

    if args == 'clear':
        current_path = await database.get_media_path()
        if current_path and os.path.exists(current_path):
            try:
                os.remove(current_path)
            except:
                pass
        await database.set_media_path("")
        await event.edit("🗑 Медиа удалено.")
        log("Медиа удалено пользователем.")
        return

    reply = await event.get_reply_message()
    if not reply or not reply.media:
        await event.edit("⚠️ Ответьте на фото/видео командой `.setmedia`")
        return

    await event.edit("📥 Скачиваю медиа...")
    try:
        # Download to app/data/broadcast_media (Telethon adds extension)
        path = await reply.download_media(file='app/data/broadcast_media')
        await database.set_media_path(path)
        await event.edit("✅ Медиа сохранено!")
        log(f"Медиа установлено: {path}")
    except Exception as e:
        await event.edit(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка загрузки медиа: {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.add'))
async def cmd_add(event):
    chat = await event.get_chat()
    chat_id = chat.id
    chat_title = getattr(chat, 'title', str(chat_id))

    success = await database.add_chat(chat_id, chat_title)
    if success:
        await event.edit(f"✅ Чат сохранён: **{chat_title}**")
        log(f"Добавлен чат: {chat_title} ({chat_id})")
        await asyncio.sleep(3)
        await event.delete()
    else:
        await event.edit(f"⚠️ Чат **{chat_title}** уже есть в базе.")
        await asyncio.sleep(3)
        await event.delete()

@client.on(events.NewMessage(outgoing=True, pattern=r'\.del'))
async def cmd_del(event):
    chat = await event.get_chat()
    await database.remove_chat(chat.id)
    await event.edit(f"🗑 Удалён: **{getattr(chat, 'title', chat.id)}**")
    log(f"Удалён чат: {getattr(chat, 'title', chat.id)}")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.set (.+)'))
async def cmd_set(event):
    if event.message.entities:
        # If message has formatting entities, convert key text to HTML
        full_html = html.unparse(event.message.message, event.message.entities)
        # Remove the command ".set " from the start
        # We split by the first space which separates cmd and args
        parts = full_html.split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else event.pattern_match.group(1)
    else:
        text = event.pattern_match.group(1)

    # Get current settings to preserve other values
    s = await database.get_settings()

    await database.update_settings(
        template=text,
        template_2=s.get('message_template_2', ''),
        template_3=s.get('message_template_3', ''),
        broadcast_mode=s.get('broadcast_mode', 1),
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    await event.edit("📝 **Шаблон 1 сохранён!**")
    log("Шаблон обновлён через команду.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.set2 (.+)'))
async def cmd_set2(event):
    if event.message.entities:
        # If message has formatting entities, convert key text to HTML
        full_html = html.unparse(event.message.message, event.message.entities)
        # Remove the command ".set2 " from the start
        parts = full_html.split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else event.pattern_match.group(1)
    else:
        text = event.pattern_match.group(1)

    s = await database.get_settings()

    await database.update_settings(
        template=s.get('message_template', ''),
        template_2=text,
        template_3=s.get('message_template_3', ''),
        broadcast_mode=s.get('broadcast_mode', 1),
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    await event.edit("📝 **Шаблон 2 сохранён!**")
    log("Шаблон 2 обновлён через команду.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.set3 (.+)'))
async def cmd_set3(event):
    if event.message.entities:
        full_html = html.unparse(event.message.message, event.message.entities)
        parts = full_html.split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else event.pattern_match.group(1)
    else:
        text = event.pattern_match.group(1)

    s = await database.get_settings()

    await database.update_settings(
        template=s.get('message_template', ''),
        template_2=s.get('message_template_2', ''),
        template_3=text,
        broadcast_mode=s.get('broadcast_mode', 1),
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    await event.edit("📝 **Шаблон 3 сохранён!**")
    log("Шаблон 3 обновлён через команду.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.dual (on|off)'))
async def cmd_dual(event):
    state = event.pattern_match.group(1).lower()
    enable = (state == 'on')

    s = await database.get_settings()
    new_mode = 2 if enable else 1
    await database.update_settings(
        template=s.get('message_template', ''),
        template_2=s.get('message_template_2', ''),
        template_3=s.get('message_template_3', ''),
        broadcast_mode=new_mode,
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    status_text = "включён" if enable else "выключен"
    await event.edit(f"🔄 **Двойной режим {status_text}!**")
    log(f"Двойной режим {status_text} через команду.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.mode ([123])'))
async def cmd_mode(event):
    mode = int(event.pattern_match.group(1))
    s = await database.get_settings()
    await database.update_settings(
        template=s.get('message_template', ''),
        template_2=s.get('message_template_2', ''),
        template_3=s.get('message_template_3', ''),
        broadcast_mode=mode,
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    mode_names = {1: "Одиночный", 2: "Двойной", 3: "Тройной"}
    web_server.bot_state["cycle_index"] = 0  # Reset cycle on mode change
    await event.edit(f"🔄 **Режим переключен: {mode_names.get(mode, mode)}!**")
    log(f"Режим рассылки изменён на {mode} через команду.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.list'))
async def cmd_list(event):
    chats = await database.get_chats()
    if not chats:
        await event.edit("Список чатов пуст.")
        return

    msg = ["📋 **Сохранённые чаты:**"]
    for i, c in enumerate(chats, 1):
        status = c['status']
        icon = "✅" if status == 'active' else "⚠️" if status == 'muted' else "❌"
        msg.append(f"{i}. {icon} {c['chat_title']} `{c['chat_id']}`")

    await event.edit("\n".join(msg))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.start'))
async def cmd_start(event):
    await database.set_running_status(True)
    await event.edit("🚀 **Рассылка запущена!**")
    log("Рассылка запущена вручную.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.stop'))
async def cmd_stop(event):
    await database.set_running_status(False)
    await event.edit("🛑 **Рассылка остановлена!**")
    log("Рассылка остановлена вручную.")

# --- Broadcast Loop ---

async def broadcast_loop():
    logger.info("Запуск цикла рассылки...")

    # Fetch User ID for Anti-Spam checks
    me = await client.get_me()
    my_id = me.id if me else None
    if not my_id:
        log("⚠️ Цикл рассылки запущен без 'my_id' (анти-дубль недоступен).")

    # cycle_index is stored in web_server.bot_state so it persists across loop iterations
    # and is accessible/resettable via Telegram commands

    while True:
        try:
            settings = await database.get_settings()
            if not settings['is_running']:
                log("⏸ Бот на паузе...")
                await asyncio.sleep(5)
                continue

            # Check Limit
            daily_limit = settings['daily_limit']

            # Reset Check
            now_kyiv = datetime.now(TZ_KYIV)
            last_reset_str = await database.get_stat('last_reset_date')
            today_str = now_kyiv.strftime('%Y-%m-%d')

            if last_reset_str != today_str:
                await database.update_stat('daily_sent', "0")
                await database.update_stat('last_reset_date', today_str)
                log(f"📅 Новый день! Дневной лимит сброшен. ({today_str})")

            total_sent_today = int(await database.get_stat('daily_sent') or 0)

            # FIX: Check limit dynamically inside the loop, not just once at start
            if total_sent_today >= daily_limit:
                # Re-check limit from DB in case user increased it
                settings = await database.get_settings()
                daily_limit = settings['daily_limit']
                
                if total_sent_today >= daily_limit:
                    log(f"🛑 Дневной лимит достигнут ({total_sent_today}/{daily_limit}). Пауза 60с...")
                    await asyncio.sleep(60)
                    continue
                else:
                    log(f"✅ Лимит увеличен! Продолжаю... ({total_sent_today}/{daily_limit})")

            # Get Chats
            chats = await database.get_chats()
            if not chats:
                log("В БД нет чатов. Пауза 60с...")
                await asyncio.sleep(60)
                continue

            active_chats = [c for c in chats if c['status'] != 'error']
            if not active_chats:
                log("Нет доступных активных чатов. Пауза 60с...")
                await asyncio.sleep(60)
                continue

            random.shuffle(active_chats)

            # Determine text for this cycle
            broadcast_mode = int(settings.get('broadcast_mode', 1))
            template_1 = settings.get('message_template', '') or ""
            template_2 = settings.get('message_template_2', '') or ""
            template_3 = settings.get('message_template_3', '') or ""

            cycle_index = web_server.bot_state["cycle_index"]
            mode_names = {1: "Single", 2: "Dual", 3: "Triple"}
            log(f"⚙️ Конфиг: Режим={mode_names.get(broadcast_mode, broadcast_mode)} | cycle_index={cycle_index}")
            log(f"📝 Шаблоны: T1={len(template_1)}ч | T2={len(template_2)}ч | T3={len(template_3)}ч")

            if broadcast_mode == 3:
                slot = cycle_index % 3
                slots = [template_1, template_2, template_3]
                template_to_use = slots[slot]
                log(f"{slot + 1}️⃣ Triple режим — отправка шаблона №{slot + 1}")
            elif broadcast_mode == 2:
                slot = cycle_index % 2
                template_to_use = template_1 if slot == 0 else template_2
                log(f"{slot + 1}️⃣ Dual режим — отправка шаблона №{slot + 1}")
            else:
                template_to_use = template_1
                log("1️⃣ Single режим — отправка шаблона №1")

            if not template_to_use:
                log(f"⚠️ Активный шаблон пуст (cycle_index={cycle_index})!")
                if broadcast_mode >= 2:
                    web_server.bot_state["cycle_index"] += 1
                    log(f"🔄 Переключено на следующий шаблон (index={web_server.bot_state['cycle_index']}).")
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(60)
                continue

            consecutive_errors = 0

            # Process chats
            for chat_row in active_chats:
                # Re-check settings inside loop (for stop command or limit change)
                settings = await database.get_settings()
                if not settings['is_running']:
                    break
                
                # Check limit inside inner loop too
                total_sent_today = int(await database.get_stat('daily_sent') or 0)
                if total_sent_today >= settings['daily_limit']:
                    log(f"🛑 Дневной лимит достигнут в цикле ({total_sent_today}/{settings['daily_limit']}). Ставлю паузу...")
                    break

                chat_id = chat_row['chat_id']
                chat_title = chat_row['chat_title']

                # --- Anti-Double-Post Protection (Global) ---
                if my_id:
                    try:
                        messages = await client.get_messages(chat_id, limit=1)
                        if messages and messages[0].sender_id == my_id:
                            log(f"✋ Пропуск {chat_title}: последнее сообщение моё")
                            continue
                    except Exception as e:
                        # If we can't read history (e.g. private channel), just proceed safe
                        # log(f"Could not check history for {chat_title}: {e}")
                        pass

                # Check Mute logic
                if chat_row['next_run_at']:
                    next_run_val = chat_row['next_run_at']
                    if next_run_val:
                        try:
                            # Parse date logic...
                            if isinstance(next_run_val, str):
                                next_run = datetime.fromisoformat(next_run_val)
                            elif isinstance(next_run_val, (int, float)):
                                next_run = datetime.fromtimestamp(next_run_val)
                            else:
                                next_run = next_run_val

                            current_dt = datetime.now(next_run.tzinfo) if next_run.tzinfo else datetime.now()

                            if current_dt < next_run:
                                continue
                            else:
                                await database.update_chat_status(chat_id, 'active', None, None)
                        except Exception as e:
                            logger.error(f"Ошибка разбора даты для {chat_id}: {e}")

                # Check Cooldown
                cooldown_until = await database.get_chat_cooldown(chat_id)
                if cooldown_until:
                    try:
                        # cooldown_until might be stored as string or int
                        if isinstance(cooldown_until, str):
                            cd_dt = datetime.fromisoformat(cooldown_until)
                        elif isinstance(cooldown_until, (int, float)):
                            cd_dt = datetime.fromtimestamp(cooldown_until)
                        else:
                            cd_dt = cooldown_until

                        # Ensure timezone awareness compatibility
                        current_dt = datetime.now(cd_dt.tzinfo) if cd_dt.tzinfo else datetime.now()

                        if current_dt < cd_dt:
                            log(f"⏳ Пропуск {chat_title} (кулдаун активен до {cd_dt})")
                            continue
                    except Exception as e:
                        logger.error(f"Ошибка разбора cooldown для {chat_id}: {e}")

                text = spintax.process_spintax(template_to_use)

                # Get Media
                media_path = await database.get_media_path()
                has_media = False
                if media_path and os.path.exists(media_path):
                    has_media = True

                try:
                    log(f"📢 Обработка: {chat_title}")

                    # 1. Human-Like: Mark as Read
                    await client.send_read_acknowledge(chat_id)

                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(random.randint(2, 5))

                    if has_media:
                        await client.send_message(chat_id, text, file=media_path, parse_mode='html', link_preview=True)
                    else:
                        await client.send_message(chat_id, text, parse_mode='html', link_preview=True)

                    log(f"✅ Отправлено в: {chat_title}")

                    # Update Stats
                    total_sent_today += 1
                    total_sent_all = int(await database.get_stat('total_sent') or 0) + 1
                    await database.update_stat('daily_sent', total_sent_today)
                    await database.update_stat('total_sent', total_sent_all)

                    consecutive_errors = 0

                    # 2. Schedule Delay (Normal)
                    if chat_row.get('is_custom'):
                        min_d = chat_row.get('custom_min_delay', 30)
                        max_d = chat_row.get('custom_max_delay', 60)
                        # Ensure safe values
                        min_d = min_d if min_d and min_d > 0 else 30
                        max_d = max_d if max_d and max_d > 0 else 60
                        if min_d > max_d: min_d, max_d = max_d, min_d
                        log(f"⏰ Кастомное расписание для {chat_title}: {min_d}-{max_d}с")
                    else:
                        min_d = settings.get('min_delay', 30)
                        max_d = settings.get('max_delay', 60)

                    delay_seconds = random.randint(min_d, max_d)

                    gc.collect()

                    log(f"⏳ Пауза {delay_seconds}с...")
                    await asyncio.sleep(delay_seconds)

                except FloodWaitError as e:
                    log(f"🌊 FLOOD WAIT ({chat_title}): {e.seconds}с. Добавляю кулдаун чата.")
                    # Set cooldown for this specific chat
                    cooldown_time = datetime.now().timestamp() + e.seconds + 3
                    await database.set_chat_cooldown(chat_id, cooldown_time)
                    await asyncio.sleep(random.randint(2, 5))

                except (PeerIdInvalidError, ChatWriteForbiddenError, UserBannedInChannelError) as e:
                    log(f"❌ Бан/невалидный чат ({chat_title}). Удаляю...")
                    try:
                        await client.delete_dialog(chat_id)
                    except:
                        pass
                    await database.remove_chat(chat_id)
                    consecutive_errors += 1

                except SlowModeWaitError as e:
                    log(f"🐌 Slowmode ({chat_title}): ожидание {e.seconds}с. Добавляю кулдаун чата.")
                    cooldown_time = datetime.now().timestamp() + e.seconds + 3
                    await database.set_chat_cooldown(chat_id, cooldown_time)

                except ChatRestrictedError:
                    log(f"🔇 Ограничения ({chat_title}). Ставлю паузу на 2ч.")
                    next_run = datetime.now().timestamp() + 7200
                    next_run_dt = datetime.fromtimestamp(next_run)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run_dt, last_error="Ограничение")

                except Exception as e:
                    log(f"⚠️ Ошибка отправки в {chat_title}: {e}")
                    await database.update_chat_status(chat_id, 'active', last_error=str(e))
                    consecutive_errors += 1
                    await asyncio.sleep(5)

                if consecutive_errors >= 5:
                    log("🚨 Слишком много ошибок подряд! Защитная пауза 10 минут...")
                    await asyncio.sleep(600)
                    consecutive_errors = 0
                    break

            # End of list cycle — advance cycle_index for multi-template modes
            if broadcast_mode >= 2:
                web_server.bot_state["cycle_index"] += 1
                log(f"🔄 Цикл завершён. cycle_index={web_server.bot_state['cycle_index']}")

            cycle_delay = settings.get('cycle_delay_seconds', 120)
            log(f"🏁 Конец цикла. Пауза {cycle_delay}с...")
            await asyncio.sleep(cycle_delay)

        except Exception as e:
            logger.error(f"Критическая ошибка цикла: {e}", exc_info=True)
            await asyncio.sleep(60)

# --- Telethon Background Task ---

async def init_telethon():
    try:
        await client.connect()

        if not await client.is_user_authorized():
            try:
                qr_login = await client.qr_login()
                print("Сессия не найдена. Генерирую QR-код...")
                qr = qrcode.QRCode()
                qr.add_data(qr_login.url)
                qr.print_ascii(invert=True)
                print("Сканируйте код выше!")
                await qr_login.wait()
                print("Вход выполнен!")
            except SessionPasswordNeededError:
                print("Включена двухэтапная проверка. Пробую пароль...")
                if config.PASSWORD:
                    try:
                        await client.sign_in(password=config.PASSWORD)
                        print("Вход выполнен по паролю!")
                    except PasswordHashInvalidError:
                        print("❌ CRITICAL: Invalid 2FA password in .env. Please update it and restart.")
                        return
                else:
                    print("ОШИБКА: включена 2FA, но 'PASSWORD' отсутствует в .env!")
                    return
            except Exception as e:
                print(f"Ошибка входа: {e}")
                return

        log("Telegram-клиент подключен!")

        log("Загружаю диалоги для кэша сущностей...")
        await client.get_dialogs()
        log("Диалоги синхронизированы!")

        # Start Broadcast Loop
        asyncio.create_task(broadcast_loop())
        
        # Run Client until disconnected
        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"Ошибка в фоновой задаче Telethon: {e}")

# --- Main Entry ---

async def main():
    # 1. Init DB
    await database.init_db()

    # Register Telegram folder import callback for web API.
    web_server.set_folder_importer(import_folder_chats)

    # 2. Start Telethon Background Task
    asyncio.create_task(init_telethon())

    # 3. Start Web Server and await it to keep the process running
    web_task = asyncio.create_task(web_server.run_server())
    log("Веб-сервер запущен на порту 8080.")
    await web_task

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановка...")
