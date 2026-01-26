import asyncio
import logging
import random
import os
import sys
import gc
from datetime import datetime, timedelta
from pytz import timezone

# Install and import libraries
try:
    from telethon import TelegramClient, events, errors
    import qrcode
except ImportError:
    print("Installing requirements...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "qrcode", "python-dotenv", "pytz", "fastapi", "uvicorn", "jinja2", "python-multipart", "aiofiles", "aiosqlite"])
    from telethon import TelegramClient, events, errors
    import qrcode

from app import config, database, spintax, web_server

# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------
KYIV_TZ = timezone('Europe/Kyiv')

# -----------------------------------------------------------------------------
# LOGGING SETUP
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Pipe logs to Web Interface
class WebQueueHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            web_server.add_log(msg)
        except:
            pass

web_handler = WebQueueHandler()
web_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(web_handler)

# -----------------------------------------------------------------------------
# TELEGRAM CLIENT SETUP
# -----------------------------------------------------------------------------
SESSION_PATH = os.path.join(os.path.dirname(__file__), 'user_session')

client = TelegramClient(
    SESSION_PATH,
    config.API_ID,
    config.API_HASH
)

async def check_auth():
    """Auth using QR Login."""
    await client.connect()
    if not await client.is_user_authorized():
        qr_login = await client.qr_login()
        qr = qrcode.QRCode()
        qr.add_data(qr_login.url)
        qr.print_ascii(invert=True)
        logger.info("Scan the QR Code to login.")
        await qr_login.wait()
        logger.info("Login successful!")
    else:
        logger.info("Session loaded. Login successful!")

async def log_to_channel(text):
    """Optional remote logging."""
    try:
        settings = await database.get_settings()
        chan_id = settings.get('log_channel_id')
        if chan_id:
            await client.send_message(chan_id, f"ℹ️ {text}")
    except:
        pass

# -----------------------------------------------------------------------------
# BROADCAST LOGIC
# -----------------------------------------------------------------------------
async def broadcast_loop():
    logger.info("Broadcast Monitor: Started.")
    while True:
        try:
            settings = await database.get_settings()
            if not settings.get('is_running'):
                await asyncio.sleep(5)
                continue

            # Check Timezone (Sleep at night)
            now = datetime.now(KYIV_TZ)
            if now.hour >= 23 or now.hour < 7:
                 logger.info(f"🌙 Night Mode ({now.strftime('%H:%M')}). Sleeping 1h.")
                 await asyncio.sleep(3600)
                 continue

            # Check Limits
            limit = settings.get('daily_limit', 400)
            daily_sent = int(await database.get_stat('daily_sent', '0'))
            today_str = now.strftime("%Y-%m-%d")
            last_reset = await database.get_stat('last_reset_date')

            if last_reset != today_str:
                await database.set_stat('daily_sent', 0)
                await database.set_stat('last_reset_date', today_str)
                daily_sent = 0
                logger.info("Stats: Daily limit reset.")

            if daily_sent >= limit:
                logger.warning(f"Stats: 🛑 Daily Limit Reached ({limit}). Pausing 1h.")
                await asyncio.sleep(3600)
                continue

            # Get Content
            chats = await database.get_chats()
            template = settings.get('message_template', '')
            media_path = await database.get_media()

            if not chats or not template:
                await asyncio.sleep(60)
                continue

            logger.info(f"Broadcast: Scanning {len(chats)} chats...")

            for chat in chats:
                # Refresh status check inside loop
                settings = await database.get_settings()
                if not settings.get('is_running'): break

                chat_id = chat['chat_id']
                chat_title = chat['chat_title']
                status = chat.get('status', 'active')
                next_run_val = chat.get('next_run_at')

                # SMART HANDLING: Check Status & Timer
                if status == 'error':
                    continue

                if next_run_val:
                    try:
                        next_run_dt = datetime.fromisoformat(next_run_val)
                        if datetime.now() < next_run_dt:
                            # Too early
                            continue
                        else:
                            # Timer expired, un-mute in DB if needed, but we just proceed
                            pass
                    except ValueError:
                        pass # Ignore parsing errors

                logger.info(f"📢 Processing: {chat_title}")
                text = spintax.process_spintax(template)

                try:
                    await client.send_read_acknowledge(chat_id)
                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(random.randint(2, 5))

                    if media_path and os.path.exists(media_path):
                        await client.send_message(chat_id, text, file=media_path)
                    else:
                        await client.send_message(chat_id, text)

                    await database.increment_stat('total_sent')
                    await database.increment_stat('daily_sent')

                    # Success: Reset status
                    await database.update_chat_status(chat_id, 'active', next_run_at=None, last_error=None)
                    logger.info(f"✅ Sent to {chat_title}")

                    gc.collect()

                    await asyncio.sleep(random.randint(20, 50))

                except errors.FloodWaitError as e:
                    logger.warning(f"🌊 FLOOD WAIT: {e.seconds}s")
                    await asyncio.sleep(e.seconds)

                except errors.SlowModeWaitError as e:
                    wait_sec = e.seconds + 5
                    logger.warning(f"🐢 Slowmode: {wait_sec}s")
                    next_run = datetime.now() + timedelta(seconds=wait_sec)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run.isoformat())

                except errors.ChatWriteForbiddenError:
                    logger.error(f"🚫 BANNED in {chat_title}. Leaving.")
                    await database.remove_chat(chat_id)
                    try:
                        await client.delete_dialog(chat_id)
                    except:
                        pass

                except errors.ChatRestrictedError:
                    logger.warning(f"🤐 Restricted/Muted in {chat_title}. Pausing 2h.")
                    next_run = datetime.now() + timedelta(hours=2)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run.isoformat())

                except Exception as e:
                    logger.error(f"❌ Error in {chat_title}: {e}")
                    await database.update_chat_status(chat_id, 'error', last_error=str(e))

            logger.info("Cycle finished. Sleeping 30m.")
            await asyncio.sleep(1800)

        except Exception as e:
            logger.critical(f"Loop Error: {e}", exc_info=True)
            await asyncio.sleep(60)

# -----------------------------------------------------------------------------
# TELEGRAM COMMANDS
# -----------------------------------------------------------------------------
@client.on(events.NewMessage(outgoing=True))
async def handler(event):
    msg = event.message.message
    if not msg.startswith('.'): return

    chat = await event.get_chat()
    chat_id = chat.id
    chat_title = getattr(chat, 'title', 'Unknown')

    if msg == '.add':
        if await database.add_chat(chat_id, chat_title):
            await event.edit(f"✅ Saved: {chat_title}")
        else:
            await event.edit("⚠️ Already saved.")

    elif msg == '.del':
        await database.remove_chat(chat_id)
        await event.edit("🗑 Removed.")

    elif msg == '.list':
        chats = await database.get_chats()
        await event.edit(f"📋 Saved Chats: {len(chats)}")

    elif msg == '.start':
        await database.update_settings(running=True)
        await event.edit("🚀 Started")

    elif msg == '.stop':
        await database.update_settings(running=False)
        await event.edit("🛑 Stopped")

    elif msg.startswith('.set '):
        txt = msg[5:]
        await database.update_settings(template=txt)
        await event.edit("📝 Template saved.")

    elif msg == '.setmedia':
        reply = await event.get_reply_message()
        if reply and reply.media:
            path = os.path.join(os.path.dirname(__file__), 'data', 'media.jpg')
            await client.download_media(reply, file=path)
            await database.set_media(path)
            await event.edit("🖼 Media saved.")
        else:
            await event.edit("❌ Reply to a media.")

# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
async def main():
    # 1. Init DB
    await database.init_db()

    # 2. Start Telethon
    await check_auth()

    # 3. Start Web Server
    asyncio.create_task(web_server.run_server())
    logger.info("🌍 Web Admin running on port 8080")

    # 4. Start Broadcast Loop
    asyncio.create_task(broadcast_loop())

    # 5. Run Forever
    logger.info("Bot is running...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
