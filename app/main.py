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
        dual_mode=s.get('use_dual_mode', False),
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    await event.edit("📝 **Template 1 Saved!**")
    log("Template updated via command.")

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
        dual_mode=s.get('use_dual_mode', False),
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    await event.edit("📝 **Template 2 Saved!**")
    log("Template 2 updated via command.")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.dual (on|off)'))
async def cmd_dual(event):
    state = event.pattern_match.group(1).lower()
    enable = (state == 'on')

    s = await database.get_settings()
    await database.update_settings(
        template=s.get('message_template', ''),
        template_2=s.get('message_template_2', ''),
        dual_mode=enable,
        limit=s['daily_limit'],
        min_delay=s.get('min_delay', 30),
        max_delay=s.get('max_delay', 60),
        cycle_delay=s.get('cycle_delay_seconds', 120)
    )
    status_text = "Enabled" if enable else "Disabled"
    await event.edit(f"🔄 **Dual Mode {status_text!}**")
    log(f"Dual mode {status_text.lower()} via command.")

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

    # Fetch User ID for Anti-Spam checks
    me = await client.get_me()
    my_id = me.id if me else None
    if not my_id:
        log("⚠️ Creating broadcast loop without 'my_id' (Anti-Double-Post unavailable).")

    # Track which message we are sending next. 1 or 2.
    current_message_index = 1

    while True:
        try:
            settings = await database.get_settings()
            if not settings['is_running']:
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
                log(f"📅 New day! Daily limit reset. ({today_str})")

            total_sent_today = int(await database.get_stat('daily_sent') or 0)

            # FIX: Check limit dynamically inside the loop, not just once at start
            if total_sent_today >= daily_limit:
                # Re-check limit from DB in case user increased it
                settings = await database.get_settings()
                daily_limit = settings['daily_limit']
                
                if total_sent_today >= daily_limit:
                    log(f"🛑 Daily limit reached ({total_sent_today}/{daily_limit}). Sleeping 60s...")
                    await asyncio.sleep(60)
                    continue
                else:
                    log(f"✅ Limit increased! Resuming... ({total_sent_today}/{daily_limit})")

            # Get Chats
            chats = await database.get_chats()
            if not chats:
                log("No chats in DB. Sleeping 60s...")
                await asyncio.sleep(60)
                continue

            active_chats = [c for c in chats if c['status'] != 'error']
            if not active_chats:
                log("No active chats available. Sleeping 60s...")
                await asyncio.sleep(60)
                continue

            random.shuffle(active_chats)

            # Determine text for this cycle
            use_dual = bool(settings.get('use_dual_mode', False))
            template_1 = settings.get('message_template', '') or ""
            template_2 = settings.get('message_template_2', '') or ""

            # Debug logs to verify config loading
            log(f"⚙️ Config: Dual={use_dual} | Index={current_message_index}")
            log(f"📝 Templates: T1(len)={len(template_1)} | T2(len)={len(template_2)}")

            if use_dual:
                if current_message_index == 1:
                    template_to_use = template_1
                    log("1️⃣ Cycle: Dual Mode - Sending Message #1")
                else:
                    template_to_use = template_2
                    log("2️⃣ Cycle: Dual Mode - Sending Message #2")
            else:
                # Single mode always uses template 1
                template_to_use = template_1
                current_message_index = 1 
                log("1️⃣ Cycle: Single Mode - Sending Message #1")

            if not template_to_use:
                log(f"⚠️ Template #{current_message_index} is empty!")
                if use_dual:
                    # Toggle index to try the other message next time
                    current_message_index = 2 if current_message_index == 1 else 1
                    log(f"🔄 Switched to Index {current_message_index} for next attempt.")
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
                    log(f"🛑 Daily limit hit during cycle ({total_sent_today}/{settings['daily_limit']}). Pausing...")
                    break

                chat_id = chat_row['chat_id']
                chat_title = chat_row['chat_title']

                # --- Anti-Double-Post Protection (Global) ---
                if my_id:
                    try:
                        messages = await client.get_messages(chat_id, limit=1)
                        if messages and messages[0].sender_id == my_id:
                            log(f"✋ Skip {chat_title}: Last message is mine")
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
                            logger.error(f"Date parse error for {chat_id}: {e}")

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
                            log(f"⏳ Skipping {chat_title} (cooldown active until {cd_dt})")
                            continue
                    except Exception as e:
                        logger.error(f"Cooldown parse error {chat_id}: {e}")

                text = spintax.process_spintax(template_to_use)

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
                        await client.send_message(chat_id, text, file=media_path, parse_mode='html')
                    else:
                        await client.send_message(chat_id, text, parse_mode='html')

                    log(f"✅ Sent to: {chat_title}")

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
                        log(f"⏰ Custom Schedule for {chat_title}: {min_d}-{max_d}s")
                    else:
                        min_d = settings.get('min_delay', 30)
                        max_d = settings.get('max_delay', 60)

                    delay_seconds = random.randint(min_d, max_d)

                    gc.collect()

                    log(f"⏳ Sleeping {delay_seconds}s...")
                    await asyncio.sleep(delay_seconds)

                except FloodWaitError as e:
                    log(f"🌊 FLOOD WAIT ({chat_title}): {e.seconds}s. Adding chat cooldown.")
                    # Set cooldown for this specific chat
                    cooldown_time = datetime.now().timestamp() + e.seconds + 3
                    await database.set_chat_cooldown(chat_id, cooldown_time)
                    # We do NOT sleep the whole loop here, just skip this chat next time
                    # But if it's a global floodwait, Telethon might auto-sleep or raise.
                    # FloodWaitError usually means per-request, but can be global.
                    # If it's very long, it might be better to sleep, but requirement says "per-chat cooldown".
                    # However, if we get FloodWait on one chat, we might get it on others if it's global.
                    # Assuming per-chat or short waits. If e.seconds is huge, we might want to respect it globally?
                    # The prompt says: "per-chat cooldown... sending to other chats should not stop".
                    # So we just save cooldown and continue.
                    await asyncio.sleep(random.randint(2, 5)) # small sleep before next chat

                except (PeerIdInvalidError, ChatWriteForbiddenError, UserBannedInChannelError) as e:
                    log(f"❌ Banned/Invalid ({chat_title}). Deleting...")
                    try:
                        await client.delete_dialog(chat_id)
                    except:
                        pass
                    await database.remove_chat(chat_id)
                    consecutive_errors += 1

                except SlowModeWaitError as e:
                    log(f"🐌 Slowmode ({chat_title}): Wait {e.seconds}s. Adding chat cooldown.")
                    cooldown_time = datetime.now().timestamp() + e.seconds + 3
                    await database.set_chat_cooldown(chat_id, cooldown_time)

                    # Also update status for UI visibility if needed, but cooldown table handles logic
                    # next_run = datetime.now().timestamp() + e.seconds + 5
                    # next_run_dt = datetime.fromtimestamp(next_run)
                    # await database.update_chat_status(chat_id, 'muted', next_run_at=next_run_dt, last_error=f"Slowmode {e.seconds}s")

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
                    log("🚨 Too many consecutive errors! Safety sleep 10 mins...")
                    await asyncio.sleep(600)
                    consecutive_errors = 0
                    break

            # End of list cycle
            # Toggle message index if Dual Mode is on
            if use_dual:
                current_message_index = 2 if current_message_index == 1 else 1
                log(f"🔄 Cycle Finished. Toggled Index to: {current_message_index}")

            cycle_delay = settings.get('cycle_delay_seconds', 120)
            log(f"🏁 End of cycle. Sleeping {cycle_delay}s...")
            await asyncio.sleep(cycle_delay)

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
