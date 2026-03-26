"""
Unified runtime for Pyrogram userbot, web panel, and background worker.
"""

import asyncio
import logging
import os
import random
import re
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import pytz
from pyrogram import Client
from pyrogram.errors import RPCError

from app import anti_spam, client_manager, config, database, human_behavior, safe_handler, web_server

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client: Client = client_manager.ClientManager.create_client()

BROADCAST_CHATS: List[int] = []
FAILED_CHATS: Dict[int, str] = {}
TZ_KYIV = pytz.timezone(config.TIMEZONE)


def _log(message: str) -> None:
    logger.info(message)
    web_server.add_log(message)


def _extract_addlist_slug(url: str) -> str:
    match = re.search(r"(?:https?://)?t\.me/addlist/([A-Za-z0-9_-]+)", (url or "").strip())
    if not match:
        raise ValueError("Некорректная ссылка. Ожидается формат t.me/addlist/<slug>")
    return match.group(1)


def _resolve_template(settings: Dict[str, Any], cycle_index: int) -> str:
    mode = max(1, min(3, int(settings.get("broadcast_mode", 1) or 1)))
    templates = [
        settings.get("message_template", "") or "",
        settings.get("message_template_2", "") or "",
        settings.get("message_template_3", "") or "",
    ]

    if mode == 1:
        return templates[0]

    if mode == 2:
        return templates[cycle_index % 2]

    return templates[cycle_index % 3]


def _resolve_chat_delays(chat: Dict[str, Any], settings: Dict[str, Any]) -> tuple[int, int]:
    global_min = int(settings.get("min_delay", 30) or 30)
    global_max = int(settings.get("max_delay", 60) or 60)

    if global_min > global_max:
        global_min, global_max = global_max, global_min

    is_custom = int(chat.get("is_custom", 0) or 0) == 1
    custom_min = int(chat.get("custom_min_delay", 0) or 0)
    custom_max = int(chat.get("custom_max_delay", 0) or 0)

    if is_custom and custom_min >= 0 and custom_max >= 0 and custom_min <= custom_max and custom_max > 0:
        return custom_min, custom_max

    return global_min, global_max


async def _is_running() -> bool:
    settings = await database.get_settings()
    return bool(settings.get("is_running", 0))


async def add_chat_to_broadcast(chat_id: int, chat_title: Optional[str] = None) -> bool:
    if chat_id not in BROADCAST_CHATS:
        BROADCAST_CHATS.append(chat_id)
        await database.add_chat(chat_id, chat_title or str(chat_id))
        _log(f"Добавлен чат: {chat_title or chat_id}")
        return True
    return False


async def remove_chat_from_broadcast(chat_id: int) -> None:
    if chat_id in BROADCAST_CHATS:
        BROADCAST_CHATS.remove(chat_id)

    FAILED_CHATS[chat_id] = datetime.now(TZ_KYIV).isoformat()
    await database.update_chat_status(chat_id, "error", last_error="Removed by error handler")
    _log(f"Удален чат из рассылки: {chat_id}")


async def send_message_with_anti_spam(
    client: Client,
    chat_id: int,
    text: str,
    media_path: Optional[str] = None,
    min_delay: Optional[int] = None,
    max_delay: Optional[int] = None,
    should_continue: Optional[Callable[[], Awaitable[bool]]] = None,
) -> bool:
    if should_continue and not await should_continue():
        return False

    if await human_behavior.HumanBehaviorSimulator.enforce_night_mode(config.TIMEZONE, client=client):
        _log("Ночной режим активен, ожидание до утра")

    unique_text = anti_spam.uniqualize_text(text)

    await human_behavior.HumanBehaviorSimulator.simulate_pre_send_activity(client, chat_id, unique_text)

    try:
        if media_path and os.path.exists(media_path):
            await client.send_document(chat_id, media_path, caption=unique_text)
            _log(f"Сообщение отправлено в {chat_id} (с медиа)")
        else:
            await client.send_message(chat_id, unique_text)
            _log(f"Сообщение отправлено в {chat_id}")

        delay_min = float(min_delay) if min_delay is not None else float(config.MIN_DELAY)
        delay_max = float(max_delay) if max_delay is not None else float(config.MAX_DELAY)
        await human_behavior.HumanBehaviorSimulator.random_delay(delay_min, delay_max)
        return True

    except Exception as exc:
        await safe_handler.TelegramErrorHandler.handle_error(
            exc,
            chat_id=chat_id,
            remove_callback=remove_chat_from_broadcast,
        )
        if isinstance(exc, RPCError):
            logger.error("API error for chat %s: %s", chat_id, exc)
        else:
            logger.error("Unexpected error for chat %s: %s", chat_id, exc)
        return False


async def broadcast_to_chats(
    text: str,
    media_path: Optional[str] = None,
    randomize_chat_order: bool = True,
) -> Dict[str, int]:
    if not BROADCAST_CHATS:
        return {"sent": 0, "failed": 0, "skipped": 0}

    chats = BROADCAST_CHATS.copy()
    if randomize_chat_order:
        random.shuffle(chats)

    settings = await database.get_settings()
    stats = {"sent": 0, "failed": 0, "skipped": 0}

    for chat_id in chats:
        ok = await send_message_with_anti_spam(
            client,
            chat_id,
            text,
            media_path,
            int(settings.get("min_delay", 30) or 30),
            int(settings.get("max_delay", 60) or 60),
        )
        if ok:
            stats["sent"] += 1
        else:
            stats["failed"] += 1

    return stats


async def safe_get_chat_title(client: Client, chat_id: int) -> str:
    try:
        chat = await client.get_chat(chat_id)
        return chat.title or chat.first_name or str(chat_id)
    except Exception:
        return str(chat_id)


async def initialize_client_connection() -> bool:
    try:
        await client_manager.ClientManager.initialize_client(client)
        me = await client.get_me()
        _log(f"Клиент авторизован: {me.first_name} (@{me.username})")
        return True
    except Exception as exc:
        logger.error("Ошибка инициализации клиента: %s", exc)
        return False


async def close_client_connection() -> None:
    try:
        await client.stop()
        _log("Клиент остановлен")
    except Exception as exc:
        logger.error("Ошибка при остановке клиента: %s", exc)


async def get_broadcast_stats() -> Dict[str, Any]:
    return {
        "total_chats": len(BROADCAST_CHATS),
        "failed_chats": len(FAILED_CHATS),
        "broadcast_chats": BROADCAST_CHATS.copy(),
        "failed_chats_list": FAILED_CHATS.copy(),
    }


async def clear_failed_chats() -> int:
    count = len(FAILED_CHATS)
    FAILED_CHATS.clear()
    return count


async def get_current_time_kyiv() -> str:
    now = datetime.now(TZ_KYIV)
    return now.strftime("%H:%M:%S %Y-%m-%d")


async def import_folder_from_link(
    url: str,
    progress_cb: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    slug = _extract_addlist_slug(url)

    try:
        from pyrogram.raw.functions.chatlists import CheckChatlistInvite, JoinChatlistInvite
    except Exception as exc:
        raise RuntimeError("Эта версия Pyrogram не поддерживает chatlists API") from exc

    invite = await client.invoke(CheckChatlistInvite(slug=slug))

    peers = list(getattr(invite, "peers", []) or [])
    chats_raw = list(getattr(invite, "chats", []) or [])
    already_joined = bool(getattr(invite, "already_joined", False))

    if peers:
        try:
            await client.invoke(JoinChatlistInvite(slug=slug, peers=peers))
        except Exception as exc:
            # If already joined or partially joined, continue with discovered chats.
            logger.warning("JoinChatlistInvite warning: %s", exc)

    existing = {int(c["chat_id"]) for c in await database.get_chats()}
    added = 0
    duplicates = 0
    errors = 0

    total = len(chats_raw)
    processed = 0

    for raw_chat in chats_raw:
        processed += 1
        try:
            raw_id = int(getattr(raw_chat, "id"))
            title = getattr(raw_chat, "title", None) or str(raw_id)

            class_name = raw_chat.__class__.__name__.lower()
            if "channel" in class_name:
                chat_id = int(f"-100{raw_id}")
            elif "chat" in class_name:
                chat_id = -raw_id
            else:
                chat_id = raw_id

            if chat_id in existing:
                duplicates += 1
                if progress_cb:
                    await progress_cb(
                        {
                            "processed": processed,
                            "total": total,
                            "added": False,
                            "chat_id": chat_id,
                            "chat_title": title,
                            "already_joined": already_joined,
                        }
                    )
                continue

            ok = await database.add_chat(chat_id, title)
            if ok:
                added += 1
                existing.add(chat_id)
                if progress_cb:
                    await progress_cb(
                        {
                            "processed": processed,
                            "total": total,
                            "added": True,
                            "chat_id": chat_id,
                            "chat_title": title,
                            "already_joined": already_joined,
                        }
                    )
            else:
                duplicates += 1
                if progress_cb:
                    await progress_cb(
                        {
                            "processed": processed,
                            "total": total,
                            "added": False,
                            "chat_id": chat_id,
                            "chat_title": title,
                            "already_joined": already_joined,
                        }
                    )
        except Exception as exc:
            errors += 1
            if progress_cb:
                await progress_cb(
                    {
                        "processed": processed,
                        "total": total,
                        "error": str(exc),
                        "already_joined": already_joined,
                    }
                )

    return {
        "total": total,
        "added": added,
        "duplicates": duplicates,
        "errors": errors,
        "already_joined": already_joined,
    }


async def _sleep_with_pause_check(seconds: int) -> None:
    remaining = max(0, int(seconds))
    while remaining > 0:
        if not await _is_running():
            return
        step = min(2, remaining)
        await asyncio.sleep(step)
        remaining -= step


async def worker_loop() -> None:
    _log("Worker loop started")
    client_paused = False

    while True:
        try:
            settings = await database.get_settings()
            if not bool(settings.get("is_running", 0)):
                if client.is_connected and not client_paused:
                    await client.stop()
                    client_paused = True
                    _log("Клиент остановлен на паузе")
                await asyncio.sleep(2)
                continue

            if (client_paused or not client.is_connected):
                await client.start()
                client_paused = False
                _log("Клиент запущен после паузы")

            chats = [c for c in await database.get_chats() if c.get("status", "active") == "active"]
            if not chats:
                _log("Нет активных чатов для рассылки")
                await asyncio.sleep(5)
                continue

            cycle_index = int(web_server.bot_state.get("cycle_index", 0) or 0)
            template = _resolve_template(settings, cycle_index)
            if not template.strip():
                _log("Шаблон сообщения пустой, цикл пропущен")
                await asyncio.sleep(5)
                continue

            media_path = await database.get_media_path()
            random.shuffle(chats)

            sent = 0
            failed = 0

            for row in chats:
                if not await _is_running():
                    _log("Рассылка поставлена на паузу")
                    break

                chat_id = int(row["chat_id"])
                min_delay, max_delay = _resolve_chat_delays(row, settings)

                ok = await send_message_with_anti_spam(
                    client=client,
                    chat_id=chat_id,
                    text=template,
                    media_path=media_path,
                    min_delay=min_delay,
                    max_delay=max_delay,
                    should_continue=_is_running,
                )

                if ok:
                    sent += 1
                    await database.update_chat_status(chat_id, "active", last_error=None)
                else:
                    failed += 1

            if sent:
                total_sent = int(await database.get_stat("total_sent") or 0) + sent
                daily_sent = int(await database.get_stat("daily_sent") or 0) + sent
                await database.update_stat("total_sent", str(total_sent))
                await database.update_stat("daily_sent", str(daily_sent))
                if not await database.get_stat("start_date"):
                    await database.update_stat("start_date", datetime.now(TZ_KYIV).isoformat())

            _log(f"Цикл завершен: отправлено {sent}, ошибок {failed}")
            web_server.bot_state["cycle_index"] = cycle_index + 1

            cycle_delay = int(settings.get("cycle_delay_seconds", 120) or 120)
            await _sleep_with_pause_check(cycle_delay)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            await asyncio.sleep(3)


async def main() -> None:
    await database.init_db()
    web_server.set_folder_importer(import_folder_from_link)

    if not await initialize_client_connection():
        return

    worker_task = asyncio.create_task(worker_loop(), name="broadcast-worker")
    server_task = asyncio.create_task(web_server.run_server(), name="web-server")

    try:
        await asyncio.gather(worker_task, server_task)
    except asyncio.CancelledError:
        raise
    finally:
        for task in (worker_task, server_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(worker_task, server_task, return_exceptions=True)
        await close_client_connection()


if __name__ == "__main__":
    asyncio.run(main())
