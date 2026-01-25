import asyncio
import logging
import random
import os
import sys

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

# -----------------------------------------------------------------------------
# 4. CONTROL COMMANDS (Saved Messages or Outgoing)
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
        await event.edit("🚀 Broadcast Started")

    elif msg == ".stop":
        database.set_status(False)
        logger.info("Broadcast Status: DISABLED via .stop")
        await event.edit("🛑 Broadcast Stopped")

# -----------------------------------------------------------------------------
# 5. REPLY FORWARDER (LEAD CATCHER)
# -----------------------------------------------------------------------------
@client.on(events.NewMessage(incoming=True))
async def handle_replies(event):
    """Forwards incoming replies in groups to Saved Messages."""
    try:
        # Check if it's a reply
        if not event.is_reply:
            return

        # Get the message it is replying to
        reply_message = await event.get_reply_message()
        if not reply_message:
            return

        # Check if the reply is to ME (the bot)
        me = await client.get_me()
        if reply_message.sender_id != me.id:
            return

        # Check if it's a Group or Supergroup (ignore private chats)
        if event.is_private:
            return

        # Get Chat Title and Sender for context
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', 'Unknown Group')

        sender = await event.get_sender()
        sender_name = getattr(sender, 'first_name', 'Unknown') or 'User'

        # Forward to Saved Messages
        logger.info(f"Broadcast Status: 🔔 Forwarded a reply from \"{chat_title}\"")
        await client.send_message(
            "me",
            f"🔔 **New Reply in** `{chat_title}`!\n**User:** {sender_name}\n**Message:** {event.message.message}"
        )
        # Also forward the actual message for context
        await event.forward_to("me")

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
            # NIGHT MODE (Safety Feature)
            # -----------------------------------------------------------------
            kyiv_tz = timezone('Europe/Kyiv')
            now = datetime.now(kyiv_tz)

            if now.hour >= 23 or now.hour < 7:
                 logger.info(f"Broadcast Status: 🌙 Night Mode active (Current Kyiv time: {now.strftime('%H:%M')}). Sleeping for 1 hour...")
                 await asyncio.sleep(3600)
                 continue
            # -----------------------------------------------------------------

            chats = database.get_chats()
            template = database.get_template()

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

                # Re-check status before every message to allow instant stop
                if not database.get_status():
                    logger.info("Broadcast Status: Broadcast paused mid-cycle.")
                    break

                logger.info(f"📢 Processing: \"{chat_title}\"...")

                # Step 2: Spintax
                text_to_send = spintax.process_spintax(template)

                try:
                    # Step 1: Typing simulation
                    logger.info(f"Broadcast Status: Simulating typing for chat \"{chat_title}\"...")
                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(random.randint(2, 4))

                    # Step 3: Sending
                    await client.send_message(chat_id, text_to_send)
                    logger.info(f"✉️ Message sent to \"{chat_title}\"!")

                    # Step 4: Safety Delay
                    sleep_time = random.randint(20, 50)
                    logger.info(f"⏳ Sleeping {sleep_time}s before next chat...")
                    await asyncio.sleep(sleep_time)

                except errors.FloodWaitError as e:
                    logger.warning(f"FLOOD WAIT! Sleeping {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)

                except (errors.UserDeactivatedError, errors.UserIsBlockedError, errors.InputUserDeactivatedError):
                     logger.error(f"Chat inaccessible: \"{chat_title}\". Removing from DB.")
                     database.remove_chat(chat_id)

                except (ValueError, errors.PeerIdInvalidError):
                     # Often happens if peer is invalid or chatwriteforbidden
                    logger.error(f"Chat inaccessible (Invalid Peer): \"{chat_title}\". Removing from DB.")
                    database.remove_chat(chat_id)

                except Exception as e:
                    logger.error(f"Broadcast Error for \"{chat_title}\": {e}")
                    # Don't break loop, just skip chat

            # Cycle finished
            logger.info("Broadcast Status: Cycle finished. Waiting a bit before restart...")
            await asyncio.sleep(10)

        except Exception as e:
            logger.critical(f"CRITICAL LOOP ERROR: {e}", exc_info=True)
            await asyncio.sleep(10)

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
