import asyncio
import logging
import random
import os
import sys
import gc
from datetime import datetime
from pytz import timezone

# Install and import libraries
try:
    from telethon import TelegramClient, events, errors
    import qrcode
except ImportError:
    print("Installing requirements...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "qrcode", "python-dotenv", "pytz"])
    from telethon import TelegramClient, events, errors
    import qrcode

from app import config, database, spintax

# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------
DAILY_LIMIT = 400
KYIV_TZ = timezone('Europe/Kyiv')

# -----------------------------------------------------------------------------
# 2. VERBOSE LOGGING
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 1. LIBRARY & AUTHENTICATION
# -----------------------------------------------------------------------------
SESSION_PATH = os.path.join(os.path.dirname(__file__), 'user_session')

# Initialize TelegramClient
client = TelegramClient(
    SESSION_PATH,
    config.API_ID,
    config.API_HASH
)

async def check_auth():
    """Current Authentication Logic with QR Code."""
    await client.connect()

    if not await client.is_user_authorized():
        while True:
            logger.info("Session not found or expired. Generating QR...")

            monitor_task = None
            try:
                qr_login = await client.qr_login()

                # Display QR Code in terminal
                qr = qrcode.QRCode()
                qr.add_data(qr_login.url)
                qr.print_ascii(invert=True)

                logger.info("Scan the QR code above with your Telegram App.")
                logger.info("IMPORTANT: If the script stops printing logs, press ENTER to unpause the console!")

                # Start a background task to print heartbeat
                monitor_task = asyncio.create_task(print_heartbeat())

                try:
                    await qr_login.wait() # Wait for user to scan
                finally:
                    if monitor_task:
                        monitor_task.cancel()

                logger.info("Login successful! Session loaded.")
                break # Exit loop on success

            except (asyncio.TimeoutError, TimeoutError):
                logger.warning("QR Code expired (too slow). Generating a new one... Please scan again.")
                continue # Retry

            except errors.SessionPasswordNeededError:
                if monitor_task:
                    monitor_task.cancel() # Stop heartbeat
                logger.info("Two-Step Verification enabled. Password required.")
                pw = input("Enter your 2FA Password: ")
                await client.sign_in(password=pw)
                logger.info("Login successful! Session loaded.")
                break

            except Exception as e:
                logger.error(f"Error during QR login: {e}")
                await asyncio.sleep(5)
                continue
    else:
        logger.info("Session loaded. Login successful!")

async def print_heartbeat():
    """Prints a message every few seconds to show the script is alive."""
    c = 0
    while True:
        await asyncio.sleep(2)
        c += 2
        if c % 10 == 0:
            logger.info(f"...waiting for scan confirmation ({c}s passed)...")

async def log_to_channel(text):
    """Logs a message to the defined Log Channel, if set."""
    log_channel_id = database.get_log_channel()
    if log_channel_id:
        try:
            await client.send_message(log_channel_id, f"ℹ️ {text}")
        except Exception:
            pass # Ignore errors in logging to avoid loops

# -----------------------------------------------------------------------------
# 4. CONTROL COMMANDS
# -----------------------------------------------------------------------------
@client.on(events.NewMessage(outgoing=True))
async def handle_commands(event):
    msg = event.message.message
    chat = await event.get_chat()
    chat_id = chat.id
    chat_title = getattr(chat, 'title', 'Unknown') or 'Private Chat'

    if msg == ".add":
        if database.add_chat(chat_id, chat_title):
            logger.info(f"DB Operations: ✅ Added chat: \"{chat_title}\" (ID: {chat_id})")
            await event.edit(f"✅ Saved: {chat_title}")
        else:
            logger.info(f"DB Operations: Chat \"{chat_title}\" already exists")
            await event.edit(f"⚠️ Already Saved: {chat_title}")

    elif msg == ".del":
        database.remove_chat(chat_id)
        logger.info(f"DB Operations: 🗑 Removed chat: \"{chat_title}\"")
        await event.edit(f"🗑 Removed: {chat_title}")

    elif msg == ".list":
        chats = database.get_chats()
        count = len(chats)
        logger.info(f"DB Operations: Fetched {count} chats")
        if not chats:
            await event.edit("📋 **Saved Chats:** 0 (None)")
            return
        response = f"📋 **Saved Chats:** {count}\n\n"
        for i, c in enumerate(chats, 1):
             response += f"{i}. {c['title']} (ID: `{c['id']}`)\n"
        await event.edit(response)

    elif msg.startswith(".set "):
        new_template = msg[5:].strip()
        database.set_template(new_template)
        logger.info(f"DB Operations: Template updated to: {new_template[:20]}...")
        await event.edit("📝 Template Saved")

    elif msg == ".start":
        database.set_status(True)
        logger.info("Broadcast Status: ENABLED via .start")
        await log_to_channel("Broadcast STARTED manually.")
        await event.edit("🚀 Broadcast Started")

    elif msg == ".stop":
        database.set_status(False)
        logger.info("Broadcast Status: DISABLED via .stop")
        await log_to_channel("Broadcast STOPPED manually.")
        await event.edit("🛑 Broadcast Stopped")

    elif msg == ".setmedia":
        reply = await event.get_reply_message()
        if reply and reply.media:
            await event.edit("📥 Downloading media...")
            path = os.path.join(os.path.dirname(__file__), 'data', 'media.jpg')
            await client.download_media(reply, file=path)
            database.set_media(path)
            await event.edit("✅ Media Saved & Linked!")
            logger.info("DB Operations: Media saved to " + path)
        else:
            await event.edit("❌ Reply to a photo/video to set it as media.")

    elif msg == ".clearmedia":
        database.clear_media()
        await event.edit("🗑 Media Removed.")
        logger.info("DB Operations: Media cleared.")

    elif msg == ".setlog":
        database.set_log_channel(chat_id)
        await event.edit(f"📝 Log Channel Set: {chat_title}")
        logger.info(f"DB Operations: Log channel set to {chat_title} ({chat_id})")
        await log_to_channel("Test log message.")

    elif msg == ".stats":
        stats = database.get_stats()
        uptime_str = stats.get('start_date', 'Unknown')

        # Calculate uptime days (simple)
        uptime_days = "0"
        if uptime_str:
            try:
                start_dt = datetime.strptime(uptime_str, "%Y-%m-%d")
                days = (datetime.now() - start_dt).days
                uptime_days = str(days)
            except:
                pass

        chats_count = len(database.get_chats())
        response = (
            f"📊 **Bot Statistics**\n"
            f"**Uptime:** {uptime_days} days\n"
            f"**Total Sent:** {stats.get('total_sent', 0)}\n"
            f"**Today:** {stats.get('daily_sent', 0)}/{DAILY_LIMIT}\n"
            f"**Chats in DB:** {chats_count}"
        )
        await event.edit(response)

# -----------------------------------------------------------------------------
# 5. REPLY FORWARDER (LEAD CATCHER)
# -----------------------------------------------------------------------------
@client.on(events.NewMessage(incoming=True))
async def handle_replies(event):
    """Forwards incoming replies in groups to Saved Messages."""
    try:
        if not event.is_reply:
            return
        reply_message = await event.get_reply_message()
        if not reply_message:
            return

        me = await client.get_me()
        if reply_message.sender_id != me.id:
            return

        if event.is_private:
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', 'Unknown Group')
        sender = await event.get_sender()
        sender_name = getattr(sender, 'first_name', 'Unknown') or 'User'

        logger.info(f"Broadcast Status: 🔔 Forwarded a reply from \"{chat_title}\"")
        log_text = f"🔔 **New Reply in** `{chat_title}`!\n**User:** {sender_name}\n**Message:** {event.message.message}"

        await client.send_message("me", log_text)
        await event.forward_to("me")
        await log_to_channel(log_text)

    except Exception as e:
        logger.error(f"Reply Forwarder Error: {e}")

# -----------------------------------------------------------------------------
# 6. SAFE "HUMAN-LIKE" BROADCASTING LOOP
# -----------------------------------------------------------------------------
async def broadcast_loop():
    logger.info("Broadcast Monitor: Started background loop.")

    while True:
        try:
            # Check is_running flag
            if not database.get_status():
                await asyncio.sleep(5)
                continue

            # -----------------------------------------------------------------
            # SCHEDULING & TIMEZONE
            # -----------------------------------------------------------------
            try:
                now = datetime.now(KYIV_TZ)
            except Exception as e:
                # If timezone fails (rare), fall back to system time but warn
                logger.error(f"Timezone Error: {e}")
                now = datetime.now()

            weekday = now.weekday() # 0 = Mon, 6 = Sun
            hour = now.hour

            mode = 'sleep'

            # Weekend (Sat, Sun)
            if weekday >= 5:
                if 7 <= hour < 12: mode = 'light'
                elif 12 <= hour < 24: mode = 'normal' # 12-00
                else: mode = 'sleep'
            # Weekday (Mon-Fri)
            else:
                if 7 <= hour < 14: mode = 'light'
                elif 14 <= hour < 22: mode = 'normal'
                else: mode = 'sleep'

            if mode == 'sleep':
                 logger.info(f"Broadcast Status: 🌙 Sleep Mode ({now.strftime('%H:%M')}). Sleeping for 30 mins...")
                 await asyncio.sleep(1800)
                 continue

            delay_multiplier = 2 if mode == 'light' else 1
            if mode == 'light':
                logger.info("Broadcast Status: 🌤 Light Mode Active (Slower speed)")

            # -----------------------------------------------------------------
            # DAILY LIMIT CHECK
            # -----------------------------------------------------------------
            stats = database.get_stats()
            today_str = now.strftime("%Y-%m-%d")

            # Reset if new day
            if stats.get('last_reset_date') != today_str:
                database.reset_daily_stats(today_str)
                stats = database.get_stats() # refresh
                logger.info("Stats: Daily limit counter reset.")

            if stats.get('daily_sent', 0) >= DAILY_LIMIT:
                logger.warning(f"Stats: 🛑 Daily Limit Reached ({DAILY_LIMIT}). Stopping until tomorrow.")
                await log_to_channel(f"⚠️ Daily Limit Reached ({DAILY_LIMIT}). Pausing broadcast.")
                await asyncio.sleep(3600) # Sleep 1 hour then recheck
                continue

            # -----------------------------------------------------------------
            # PREPARE BROADCAST
            # -----------------------------------------------------------------
            chats = database.get_chats()
            template = database.get_template()
            media_path = database.get_media()

            if not chats:
                logger.warning("Broadcast Status: No chats in DB. Sleeping 60s.")
                await asyncio.sleep(60)
                continue

            if not template:
                logger.warning("Broadcast Status: No template set. Sleeping 60s.")
                await asyncio.sleep(60)
                continue

            logger.info(f"Broadcast Status: Starting cycle for {len(chats)} chats.")

            for chat_data in chats:
                chat_id = chat_data['id']
                chat_title = chat_data['title']

                # Quick checks before sending
                if not database.get_status(): break

                # Check Limit again within loop
                stats = database.get_stats()
                if stats.get('daily_sent', 0) >= DAILY_LIMIT:
                    break

                logger.info(f"📢 Processing: \"{chat_title}\"...")

                # Spintax
                text_to_send = spintax.process_spintax(template)

                try:
                    # Action: Mark as Read & Type
                    await client.send_read_acknowledge(chat_id)

                    async with client.action(chat_id, 'typing'):
                        typing_time = random.randint(2, 5) * delay_multiplier
                        await asyncio.sleep(typing_time)

                    # Send Message (with media if available)
                    if media_path and os.path.exists(media_path):
                        await client.send_message(chat_id, text_to_send, file=media_path)
                    else:
                        await client.send_message(chat_id, text_to_send)

                    # Update Stats
                    database.increment_stats()
                    logger.info(f"✉️ Message sent to \"{chat_title}\"!")

                    # Memory Cleanup
                    gc.collect()

                    # Safety Delay
                    base_delay = random.randint(20, 50)
                    actual_delay = base_delay * delay_multiplier
                    logger.info(f"⏳ Sleeping {actual_delay}s before next chat...")
                    await asyncio.sleep(actual_delay)

                except errors.FloodWaitError as e:
                    logger.warning(f"FLOOD WAIT! Sleeping {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)

                except (errors.UserDeactivatedError, errors.UserIsBlockedError, errors.InputUserDeactivatedError):
                     logger.error(f"Chat inaccessible: \"{chat_title}\". Removing from DB.")
                     database.remove_chat(chat_id)

                except (ValueError, errors.PeerIdInvalidError, errors.ChatWriteForbiddenError):
                    logger.error(f"Chat inaccessible (Invalid Peer/Forbidden): \"{chat_title}\". Removing from DB.")
                    database.remove_chat(chat_id)

                except Exception as e:
                    logger.error(f"Broadcast Error for \"{chat_title}\": {e}")

            # Cycle finished
            logger.info("Broadcast Status: Cycle finished. Sleeping 30 mins...")
            await asyncio.sleep(1800)

        except Exception as e:
            logger.critical(f"CRITICAL LOOP ERROR: {e}", exc_info=True)
            await asyncio.sleep(60)

# -----------------------------------------------------------------------------
# MAIN ENTRY POINT
# -----------------------------------------------------------------------------
async def main():
    try:
        # Auth
        await check_auth()

        # Start Background Loop
        asyncio.create_task(broadcast_loop())

        logger.info("System: Bot is running. Send .start in Saved Messages to begin.")

        # Run forever
        await client.run_until_disconnected()

    except KeyboardInterrupt:
        logger.info("System: Bot stopped by user.")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
