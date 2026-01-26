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

def get_delay_and_mode(now_kyiv, settings):
    hour = now_kyiv.hour
    weekday = now_kyiv.weekday() # 0=Mon, 6=Sun

    # Night Mode
    night_start = settings.get('night_start', 22)
    night_end = settings.get('night_end', 7)

    # Normal Mode
    normal_min = settings.get('min_delay', 30)
    normal_max = settings.get('max_delay', 60)

    # Light Mode
    light_start = settings.get('light_start', 7)
    light_end = settings.get('light_end', 14)
    light_min = settings.get('light_min_delay', 60)
    light_max = settings.get('light_max_delay', 120)

    # 1. Check Sleep Mode (Configurable via Web)
    is_night = False
    if night_start > night_end:
        # e.g. Start 22, End 7. Night is 22..23, 0..6
        if hour >= night_start or hour < night_end:
            is_night = True
    else:
        # e.g. Start 1, End 5. Night is 1..4
        if night_start <= hour < night_end:
            is_night = True

    if is_night:
        return None, "Sleep"

    # 2. Check Light Mode
    # Light mode precedence over Normal mode
    is_light = False
    if light_start > light_end:
        if hour >= light_start or hour < light_end:
            is_light = True
    else:
         if light_start <= hour < light_end:
            is_light = True

    if is_light:
        return random.randint(light_min, light_max), "Light"

    # 3. Normal Mode (Default)
    return random.randint(normal_min, normal_max), "Normal"

# --- Client Init ---
client = TelegramClient(SESSION_PATH, config.API_ID, config.API_HASH)

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
        await event.edit("🗑 Media removed.")
        log("Media removed by user.")
        return

    reply = await event.get_reply_message()
    if not reply or not reply.media:
        await event.edit("⚠️ Reply to a photo/video with `.setmedia`")
        return

    await event.edit("📥 Downloading media...")
    try:
        # Download to app/data/broadcast_media (Telethon adds extension)
        path = await reply.download_media(file='app/data/broadcast_media')
        await database.set_media_path(path)
        await event.edit("✅ Media saved!")
        log(f"Media set: {path}")
    except Exception as e:
        await event.edit(f"❌ Error: {e}")
        logger.error(f"Media download error: {e}")

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
    await database.update_settings(
        text,
        settings['daily_limit'],
        # Normal
        settings.get('min_delay', 30),
        settings.get('max_delay', 60),
        # Night
        settings.get('night_start', 22),
        settings.get('night_end', 7),
        # Light
        settings.get('light_start', 7),
        settings.get('light_end', 14),
        settings.get('light_min_delay', 60),
        settings.get('light_max_delay', 120),
    )
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

# --- Event Listeners ---

@client.on(events.NewMessage(incoming=True))
async def on_new_reply(event):
    """
    Lead Catcher: Forwards replies to your broadcast messages to 'Saved Messages'.
    """
    try:
        if not event.is_reply:
            return

        # Check if the message replied to is OURS (outgoing=True)
        reply_to = await event.get_reply_message()
        if not reply_to or not reply_to.out:
            return

        # Get Chat Details
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', 'Private Chat')

        # Get Sender Details
        sender = await event.get_sender()
        sender_name = getattr(sender, 'first_name', 'Unknown')

        # Construct Notification
        log(f"🔔 New Reply detected in {chat_title} from {sender_name}")

        notification_text = (
            f"🔔 **Lead Detected!**\n\n"
            f"📍 **Chat:** {chat_title}\n"
            f"👤 **User:** {sender_name}\n\n"
            f"💬 **Message:**\n{event.text}"
        )

        # Send to Saved Messages (me)
        await client.send_message('me', notification_text)
        await event.forward_to('me') # Also forward the actual message context

    except Exception as e:
        logger.error(f"Error in Lead Catcher: {e}")

# --- Broadcast Loop ---

async def broadcast_loop():
    logger.info("Starting broadcast loop...")
    session_counter = 0

    while True:
        try:
            settings = await database.get_settings()
            if not settings['is_running']:
                await asyncio.sleep(5)
                continue

            # Schedule & Mode Check
            now_kyiv = datetime.now(TZ_KYIV)
            delay_seconds, mode = get_delay_and_mode(now_kyiv, settings)

            if mode == "Sleep":
                log(f"🌙 Sleep Mode active (Kyiv {now_kyiv.strftime('%H:%M')}). Sleeping 1h...")
                await asyncio.sleep(3600)
                continue

            # Check Limit
            daily_limit = settings['daily_limit']

            # Reset Check
            last_reset_str = await database.get_stat('last_reset_date')
            today_str = now_kyiv.strftime('%Y-%m-%d')

            if last_reset_str != today_str:
                await database.update_stat('daily_sent', "0")
                await database.update_stat('last_reset_date', today_str)
                log(f"📅 New day! Daily limit reset. ({today_str})")

            total_sent_today = int(await database.get_stat('daily_sent') or 0)

            if total_sent_today >= daily_limit:
                log(f"🛑 Daily limit reached ({daily_limit}). Sleeping until tomorrow...")
                await asyncio.sleep(3600)
                continue

            # Get Chats
            chats = await database.get_chats()
            if not chats:
                log("No chats in DB. Sleeping 60s...")
                await asyncio.sleep(60)
                continue

            active_chats = [c for c in chats if c['status'] != 'error']
            random.shuffle(active_chats)

            consecutive_errors = 0

            # Process chats
            for chat_row in active_chats:
                # Re-check settings/mode/limit inside loop for responsiveness
                settings = await database.get_settings()
                if not settings['is_running']:
                    break

                # Check mode again (e.g. if hour changed)
                now_kyiv = datetime.now(TZ_KYIV)
                delay_seconds, mode = get_delay_and_mode(now_kyiv, settings)
                if mode == "Sleep":
                    break # Break inner loop to go to outer loop sleep

                chat_id = chat_row['chat_id']
                chat_title = chat_row['chat_title']

                # Check Mute logic
                if chat_row['next_run_at']:
                    # Aiosqlite might return string or ints depending on logic, let's parse safely
                    next_run_val = chat_row['next_run_at']
                    if next_run_val:
                        try:
                            # It is stored as TIMESTAMP which usually comes back as string e.g., "2023-..." or int
                            if isinstance(next_run_val, str):
                                next_run = datetime.fromisoformat(next_run_val)
                            elif isinstance(next_run_val, (int, float)):
                                next_run = datetime.fromtimestamp(next_run_val)
                            else:
                                next_run = next_run_val # already datetime?

                            # Ensure timezone awareness if needed, but safe comparison:
                            # If next_run is naive, use naive now. If aware, use aware now.
                            # Standardize to naive UTC or local for comparison
                            current_dt = datetime.now(next_run.tzinfo) if next_run.tzinfo else datetime.now()

                            if current_dt < next_run:
                                continue
                            else:
                                # Unmute
                                await database.update_chat_status(chat_id, 'active', None, None)
                        except Exception as e:
                            logger.error(f"Date parse error for {chat_id}: {e}")

                template = settings['message_template']
                if not template:
                    log("⚠️ No message template set!")
                    await asyncio.sleep(60)
                    break

                text = spintax.process_spintax(template)

                # Get Media
                media_path = await database.get_media_path()
                has_media = False
                if media_path and os.path.exists(media_path):
                    has_media = True

                try:
                    log(f"📢 Processing: {chat_title}")

                    # 1. Human-Like: Mark as Read
                    await client.send_read_acknowledge(chat_id)

                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(random.randint(2, 5))

                    if has_media:
                        await client.send_message(chat_id, text, file=media_path)
                    else:
                        await client.send_message(chat_id, text)

                    log(f"✅ Sent to: {chat_title}")

                    # Update Stats
                    total_sent_today += 1
                    total_sent_all = int(await database.get_stat('total_sent') or 0) + 1
                    await database.update_stat('daily_sent', total_sent_today)
                    await database.update_stat('total_sent', total_sent_all)

                    consecutive_errors = 0

                    # 2. Coffee Break
                    session_counter += 1
                    if session_counter % random.randint(20, 35) == 0:
                        long_sleep = random.randint(300, 900)
                        log(f"☕ Coffee break for {long_sleep//60} mins...")
                        await asyncio.sleep(long_sleep)

                    gc.collect()

                    # 3. Schedule Delay
                    log(f"⏳ Sleeping {delay_seconds}s ({mode} Mode)...")
                    await asyncio.sleep(delay_seconds)

                except FloodWaitError as e:
                    log(f"🌊 FLOOD WAIT: Sleeping {e.seconds}s")
                    await asyncio.sleep(e.seconds)

                except (PeerIdInvalidError, ChatWriteForbiddenError, UserBannedInChannelError) as e:
                    log(f"❌ Banned/Invalid ({chat_title}). Deleting...")
                    # Auto-Leave
                    try:
                        await client.delete_dialog(chat_id)
                    except:
                        pass
                    # Delete from DB
                    await database.remove_chat(chat_id)
                    consecutive_errors += 1

                except SlowModeWaitError as e:
                    log(f"🐌 Slowmode ({chat_title}): Wait {e.seconds}s")
                    # Smart Slowmode: Mute, don't delete
                    next_run = datetime.now().timestamp() + e.seconds + 5
                    # Store as ISO string for SQLite
                    next_run_dt = datetime.fromtimestamp(next_run)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run_dt, last_error=f"Slowmode {e.seconds}s")

                except ChatRestrictedError:
                    log(f"🔇 Restricted ({chat_title}). Muting for 2h.")
                    next_run = datetime.now().timestamp() + 7200
                    next_run_dt = datetime.fromtimestamp(next_run)
                    await database.update_chat_status(chat_id, 'muted', next_run_at=next_run_dt, last_error="Restricted")

                except Exception as e:
                    log(f"⚠️ Error sending to {chat_title}: {e}")
                    await database.update_chat_status(chat_id, 'active', last_error=str(e))
                    consecutive_errors += 1
                    await asyncio.sleep(5)

                if consecutive_errors >= 5:
                    log("🚨 Too many consecutive errors! Safety sleep 60 mins...")
                    await asyncio.sleep(3600)
                    consecutive_errors = 0
                    break

            # End of list sleep
            cycle_sleep = random.randint(1500, 2700)
            log(f"End of list. Sleeping {cycle_sleep//60} mins...")
            await asyncio.sleep(cycle_sleep)

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
