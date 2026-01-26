import asyncio
import logging
import random
import os
import sys
import qrcode

# Fix for Pyrogram's "There is no current event loop" error on import
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, enums, idle
from pyrogram.errors import FloodWait, PeerIdInvalid, InputUserDeactivated, UserBannedInChannel
from app.config import API_ID, API_HASH
from app.database import init_db, add_chat, remove_chat, set_template, get_template, set_status, get_status, get_chats
from app.spintax import process_spintax

# --- Basic Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Globals & Events ---
broadcast_event = asyncio.Event() 
broadcast_task = None

# --- Database & Initialization ---
init_db()

# --- Pyrogram Client Initialization ---
app = Client(
    "user_session", 
    workdir="/app/sessions",
    api_id=API_ID, 
    api_hash=API_HASH,
    device_model="Desktop PC",
    system_version="Windows 10",
    app_version="4.16.3",
    lang_code="en"
)

# --- Commands ---

@app.on_message(filters.me & filters.command("add", prefixes="."))
async def cmd_add(client, message):
    chat_id = message.chat.id
    if add_chat(chat_id):
        await message.edit("✅ Chat saved")
    else:
        await message.edit("⚠️ Chat already saved")

@app.on_message(filters.me & filters.command("del", prefixes="."))
async def cmd_del(client, message):
    chat_id = message.chat.id
    remove_chat(chat_id)
    await message.edit("🗑 Chat removed")

@app.on_message(filters.me & filters.command("set", prefixes="."))
async def cmd_set(client, message):
    if len(message.command) < 2:
        await message.edit("⚠️ Usage: `.set [text]`")
        return
    text = message.text.split(maxsplit=1)[1]
    set_template(text)
    await message.edit("📝 Template updated")

@app.on_message(filters.me & filters.command("list", prefixes="."))
async def cmd_list(client, message):
    chats = get_chats()
    if not chats:
        await message.edit("No chats saved.")
        return
    chat_list = "\n".join([f"`{c}`" for c in chats])
    await message.edit(f"📋 **Saved Chats:**\n{chat_list}")

@app.on_message(filters.me & filters.command("start", prefixes="."))
async def cmd_start(client, message):
    set_status(True)
    if not broadcast_event.is_set():
        broadcast_event.set()
        logger.info("Broadcasting started by user.")
        await message.edit("🚀 **Sending started!**")
    else:
        await message.edit("✅ **Sending is already running.**")

@app.on_message(filters.me & filters.command("stop", prefixes="."))
async def cmd_stop(client, message):
    set_status(False)
    if broadcast_event.is_set():
        broadcast_event.clear()
        logger.info("Broadcasting stopped by user.")
        await message.edit("🛑 **Sending stopped!**")
    else:
        await message.edit("✅ **Sending is already stopped.**")

# --- Broadcast Loop ---

async def broadcast_loop():
    logger.info("Broadcast loop initialized.")
    while True:
        await broadcast_event.wait() 
        
        logger.info("Starting new broadcast cycle.")
        
        chats = get_chats()
        template = get_template()

        if not chats or not template:
            logger.warning("No chats or template found. Stopping broadcast.")
            set_status(False)
            broadcast_event.clear()
            await app.send_message("me", "⚠️ **Broadcast stopped:** No chats or template found.")
            continue

        sent_count, failed_count = 0, 0
        
        for chat_id in chats:
            if not broadcast_event.is_set():
                logger.info("Broadcast was stopped mid-cycle.")
                break

            message_text = process_spintax(template)
            
            try:
                await app.send_chat_action(chat_id, enums.ChatAction.TYPING)
                await asyncio.sleep(random.uniform(2, 4))
                
                await app.send_message(chat_id, message_text)
                sent_count += 1
                logger.info(f"Sent to {chat_id}")
                
                await asyncio.sleep(random.randint(20, 50))

            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value + 5}s")
                await asyncio.sleep(e.value + 5)
            except (PeerIdInvalid, InputUserDeactivated, UserBannedInChannel) as e:
                logger.error(f"Removing chat {chat_id} due to: {e}")
                remove_chat(chat_id)
                failed_count += 1
            except Exception as e:
                logger.error(f"Unexpected error sending to {chat_id}: {e}")
                failed_count += 1

        if sent_count > 0 or failed_count > 0:
            report = f"📊 **Cycle Done**\n- Sent: {sent_count}\n- Failed: {failed_count}"
            logger.info(report)
            await app.send_message("me", report)

        if broadcast_event.is_set():
            cycle_sleep = 600 + random.randint(60, 180)
            logger.info(f"Cycle finished. Sleeping for {cycle_sleep // 60} minutes.")
            await asyncio.sleep(cycle_sleep)

# --- Main Execution ---

async def main():
    global broadcast_task
    
    # Check if session exists by trying to connect
    try:
        is_authorized = await app.connect()
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return

    if not is_authorized:
        logger.info("Session not found. Generating QR Code...")
        try:
            # This generates and prints the QR code to the terminal
            user = await app.authorize()
            logger.info(f"Login successful! User: {user.first_name}")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return
    else:
        logger.info("Session found. Logging in...")

    me = await app.get_me()
    logger.info(f"Logged in as {me.first_name} ({me.username})")

    broadcast_task = asyncio.create_task(broadcast_loop())
    
    if get_status():
        broadcast_event.set()
        logger.info("Broadcasting was enabled on startup. Resuming...")
    
    logger.info("UserBot is running. Use commands in 'Saved Messages'.")
    await idle()

async def shutdown():
    logger.info("Shutting down...")
    if broadcast_task:
        broadcast_task.cancel()
    if app.is_connected:
        await app.stop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
    finally:
        if app.is_initialized:
            asyncio.run(shutdown())
        logger.info("Shutdown complete.")
