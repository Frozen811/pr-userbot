import asyncio
import logging
import random
import os
import sys
import qrcode
from datetime import datetime
from pytz import timezone
import gc

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError, PeerIdInvalidError, ChatWriteForbiddenError,
    SlowModeWaitError, ChatRestrictedError, UserBannedInChannelError,
    SessionPasswordNeededError
)

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

# --- Commands ---

@client.on(events.NewMessage(outgoing=True, pattern=r'\.add'))
async def cmd_add(event):
    chat = await event.get_chat()
    chat_id = chat.id
    chat_title = getattr(chat, 'title', str(chat_id))

    success = await database.add_chat(chat_id, chat_title)
    if success:
        await event.edit(f"✅ Saved chat: **{chat_title}**")
        log(f"Added chat: {chat_title} ({chat_id})")
        await asyncio.sleep(3)
        await event.delete()
    else:
        await event.edit(f"⚠️ Chat **{chat_title}** is already saved.")
        await asyncio.sleep(3)
        await event.delete()

@client.on(events.NewMessage(outgoing=True, pattern=r'\.del'))
async def cmd_del(event):
    chat = await event.get_chat()
    await database.remove_chat(chat.id)
    await event.edit(f"🗑 Removed: **{getattr(chat, 'title', chat.id)}**")
    log(f"Removed chat: {getattr(chat, 'title', chat.id)}")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.set (.+)'))
async def cmd_set(event):
    text = event.pattern_match.group(1)
    # Get current limit to preserve it
    settings = await database.get_settings()
    await database.update_settings(text, settings['daily_limit'])
    await event.edit("📝 **Template Saved!**")
    log("Template updated via command.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.list'))
async def cmd_list(event):
    chats = await database.get_chats()
    if not chats:
        await event.edit("No chats saved.")
        return

    msg = ["📋 **Saved Chats:**"]
    for i, c in enumerate(chats, 1):
        status = c['status']
        icon = "✅" if status == 'active' else "⚠️" if status == 'muted' else "❌"
        msg.append(f"{i}. {icon} {c['chat_title']} `{c['chat_id']}`")

    await event.edit("\n".join(msg))

@client.on(events.NewMessage(outgoing=True, pattern=r'\.start'))
async def cmd_start(event):
    await database.set_running_status(True)
    await event.edit("🚀 **Broadcast Started!**")
    log("Broadcast started manually.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.stop'))
async def cmd_stop(event):
    await database.set_running_status(False)
    await event.edit("🛑 **Broadcast Stopped!**")
    log("Broadcast stopped manually.")

# --- Broadcast Loop ---

async def broadcast_loop():
    logger.info("Starting broadcast loop...")
    while True:
        try:
            settings = await database.get_settings()
            if not settings['is_running']:
                await asyncio.sleep(5)
                continue

            # Night Mode Check
            now_kyiv = datetime.now(TZ_KYIV)
            if now_kyiv.hour >= 23 or now_kyiv.hour < 7:
                log(f"🌙 Night Mode active (Kyiv {now_kyiv.strftime('%H:%M')}). Sleeping 1h...")
                await asyncio.sleep(3600)
                continue

            # Check Limit
            daily_limit = settings['daily_limit']
            total_sent_today = int(await database.get_stat('daily_sent') or 0)

            # Reset counter if new day (simplified check: update this logic if strictly needed,
            # ideally store 'last_reset_date' in stats and check against it)
            last_reset_str = await database.get_stat('last_reset_date')
            today_str = now_kyiv.strftime('%Y-%m-%d')
            if last_reset_str != today_str:
                await database.update_stat('daily_sent', "0")
                await database.update_stat('last_reset_date', today_str)
                total_sent_today = 0

            if total_sent_today >= daily_limit:
                log("🛑 Daily limit reached. Sleeping until tomorrow...")
                await asyncio.sleep(3600)
                continue

            # Get Chats
            chats = await database.get_chats()
            if not chats:
                log("No chats in DB. Sleeping 60s...")
                await asyncio.sleep(60)
                continue

            # Shuffle for randomness
            active_chats = [c for c in chats if c['status'] != 'error'] # Retry muted ones differently if needed
            random.shuffle(active_chats)

            for chat_row in active_chats:
                settings = await database.get_settings()
                if not settings['is_running']:
                    break

                chat_id = chat_row['chat_id']
                chat_title = chat_row['chat_title']

                # Check Mute/Slowmode status
                if chat_row['next_run_at']:
                    next_run = datetime.fromisoformat(chat_row['next_run_at'])
                    if datetime.now() < next_run:
                        # Skip silently or log debug
                        continue
                    else:
                        # Clear mute status
                        await database.update_chat_status(chat_id, 'active', None, None)

                # Send Message
                template = settings['message_template']
                if not template:
                    log("⚠️ No message template set!")
                    await asyncio.sleep(60)
                    break

                text = spintax.process_spintax(template)

                try:
                    log(f"📢 Processing: {chat_title}")

                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(random.randint(2, 5))

                    await client.send_message(chat_id, text)
                    log(f"✅ Sent to: {chat_title}")

                    # Update Stats
                    total_sent_today += 1
                    total_sent_all = int(await database.get_stat('total_sent') or 0) + 1
                    await database.update_stat('daily_sent', total_sent_today)
                    await database.update_stat('total_sent', total_sent_all)

                    # GC
                    gc.collect()

                    # Sleep
                    sleep_time = random.randint(30, 60)
                    log(f"⏳ Sleeping {sleep_time}s...")
                    await asyncio.sleep(sleep_time)

                except FloodWaitError as e:
                    log(f"🌊 FLOOD WAIT: Sleeping {e.seconds}s")
                    await asyncio.sleep(e.seconds)

                except (PeerIdInvalidError, ChatWriteForbiddenError, UserBannedInChannelError) as e:
                    log(f"❌ Banned/Invalid ({chat_title}). Removing...")
                    # await database.remove_chat(chat_id)
                    # Instead of removing, mark as error so user can see in dashboard
                    await database.update_chat_status(chat_id, 'error', last_error=str(e))
                    try:
                        await client.delete_dialog(chat_id)
                    except:
                        pass

                except SlowModeWaitError as e:
                    log(f"🐌 Slowmode ({chat_title}): Wait {e.seconds}s")
                    next_run = datetime.now().timestamp() + e.seconds + 5
                    # Convert to isoformat for storage? or just store timestamp?
                    # DB schema says TIMESTAMP. SQLite handles logic.
                    # Python datetime object is safer for aiosqlite adapters usually.
                    next_run_dt = datetime.fromtimestamp(next_run)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run_dt, last_error=f"Slowmode {e.seconds}s")

                except ChatRestrictedError:
                    log(f"🔇 Restricted ({chat_title}). Muting for 2h.")
                    # Mute for 2 hours default
                    next_run = datetime.now().timestamp() + 7200
                    next_run_dt = datetime.fromtimestamp(next_run)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run_dt, last_error="Restricted")

                except Exception as e:
                    log(f"⚠️ Error sending to {chat_title}: {e}")
                    await database.update_chat_status(chat_id, 'active', last_error=str(e)) # Keep active but log error
                    await asyncio.sleep(5)

            # End of cycle sleep (30 mins if loop completed)
            log("End of broadcast cycle. Sleeping 30 mins...")
            await asyncio.sleep(1800)

        except Exception as e:
            logger.error(f"Critical Loop Error: {e}", exc_info=True)
            await asyncio.sleep(60)

# --- Check Auth & QR ---
async def check_auth():
    if not await client.is_user_authorized():
        qr = await client.qr_login()
        print("Scanned QR Login detected. Generating QR...")
        qr_obj = qrcode.QRCode()
        qr_obj.add_data(qr.url)
        qr_obj.print_ascii(invert=True)
        print("Please scan the QR code using your Telegram app.")

        # Wait for login
        await qr.wait()
        print("Login successful!")

# --- Main Entry ---

async def main():
    # 1. Init DB
    await database.init_db()

    # 2. Start Web Server
    # uvicorn needs to run on the loop.
    # web_server.run_server() is an async func blocking? No, uvicorn.Server.serve() is blocking.
    # We should run it as a task.
    web_task = asyncio.create_task(web_server.run_server())
    log("Web Server started on port 8080.")

    # 3. Connect Client
    await client.connect()

    # 4. Check Auth
    if not await client.is_user_authorized():
        # Handle QR login manually because client.start() logic is tricky to customize for strictly QR
        # client.qr_login returns a QRLogin object with .url and .wait()
        try:
            qr_login = await client.qr_login()
            print("Session missing. Generating QR Code...")
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.print_ascii(invert=True)
            print("Scan above!")
            await qr_login.wait()
            print("Logged in!")
        except SessionPasswordNeededError:
            print("Two-step verification enabled. Trying password...")
            if config.PASSWORD:
                await client.sign_in(password=config.PASSWORD)
                print("Logged in with password!")
            else:
                print("ERROR: 2FA is enabled but 'PASSWORD' is missing in .env!")
                return
        except Exception as e:
            print(f"Login failed: {e}")
            return

    log("Telegram Client Connected!")

    # Fix for 'Could not find the input entity'
    # We must fetch dialogs once to populate Telethon's internal cache with access hashes
    log("Fetching dialogs to cache entities...")
    await client.get_dialogs()
    log("Dialogs synced!")

    # 5. Start Broadcast Loop
    broadcast_task = asyncio.create_task(broadcast_loop())
    
    # 6. Run Client until disconnected
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopping...")
