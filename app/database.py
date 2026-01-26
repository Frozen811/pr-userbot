import aiosqlite
import os
import logging
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'bot.db')
logger = logging.getLogger(__name__)

async def init_db():
    """Initialize DB and perform safe migrations using a fresh connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. Chats Table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT
            )
        ''')

        # MIGRATION: Check columns for chats
        async with db.execute("PRAGMA table_info(chats)") as cursor:
            columns = [row['name'] for row in await cursor.fetchall()]

        if 'status' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN status TEXT DEFAULT 'active'")
            logger.info("DB Migration: Added 'status' column to chats.")

        if 'next_run_at' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN next_run_at TIMESTAMP")
            logger.info("DB Migration: Added 'next_run_at' column to chats.")

        if 'last_error' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN last_error TEXT")
            logger.info("DB Migration: Added 'last_error' column to chats.")

        # 2. Settings Table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                message_template TEXT DEFAULT '',
                is_running BOOLEAN DEFAULT 0,
                log_channel_id INTEGER DEFAULT 0,
                daily_limit INTEGER DEFAULT 400
            )
        ''')

        # Ensure default settings
        async with db.execute("SELECT count(*) FROM settings") as cursor:
            count_result = await cursor.fetchone()
            count = count_result[0] if count_result else 0
            if count == 0:
                await db.execute("INSERT INTO settings (id) VALUES (1)")

        # MIGRATION: Settings
        async with db.execute("PRAGMA table_info(settings)") as cursor:
            cols = [row['name'] for row in await cursor.fetchall()]

        if 'daily_limit' not in cols:
            await db.execute("ALTER TABLE settings ADD COLUMN daily_limit INTEGER DEFAULT 400")

        # 3. Media Table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                file_path TEXT DEFAULT ''
            )
        ''')
        async with db.execute("SELECT count(*) FROM media") as cursor:
            count_result = await cursor.fetchone()
            if count_result and count_result[0] == 0:
                await db.execute("INSERT INTO media (id) VALUES (1)")

        # 4. Stats Table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Initialize default stats if missing
        defaults = {
            'total_sent': '0',
            'daily_sent': '0',
            'last_reset_date': datetime.now().strftime("%Y-%m-%d"),
            'start_date': datetime.now().strftime("%Y-%m-%d")
        }
        for k, v in defaults.items():
            await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, ?)", (k, v))

        await db.commit()
        logger.info("Database initialized and migrated safely.")

# --- DATA ACCESS METHODS ---

async def add_chat(chat_id, chat_title):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO chats (chat_id, chat_title) VALUES (?, ?)", (chat_id, chat_title))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_chat(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_chats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM chats") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def update_chat_status(chat_id, status, next_run_at=None, last_error=None):
    async with aiosqlite.connect(DB_PATH) as db:
        query = "UPDATE chats SET status = ?"
        params = [status]
        if next_run_at is not None:
            query += ", next_run_at = ?"
            params.append(next_run_at)
        if last_error is not None:
            query += ", last_error = ?"
            params.append(last_error)

        query += " WHERE chat_id = ?"
        params.append(chat_id)

        await db.execute(query, tuple(params))
        await db.commit()

async def get_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM settings WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}

async def update_settings(template=None, limit=None, running=None, log_channel=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if template is not None:
            await db.execute("UPDATE settings SET message_template = ? WHERE id = 1", (template,))
        if limit is not None:
            await db.execute("UPDATE settings SET daily_limit = ? WHERE id = 1", (limit,))
        if running is not None:
            await db.execute("UPDATE settings SET is_running = ? WHERE id = 1", (1 if running else 0,))
        if log_channel is not None:
            await db.execute("UPDATE settings SET log_channel_id = ? WHERE id = 1", (log_channel,))
        await db.commit()

async def get_media():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT file_path FROM media WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            return row['file_path'] if row else ""

async def set_media(path):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE media SET file_path = ? WHERE id = 1", (path,))
        await db.commit()

# --- STATS METHODS ---

async def get_stat(key, default='0'):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT value FROM stats WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row['value'] if row else default

async def set_stat(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("REPLACE INTO stats (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def increment_stat(key):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT value FROM stats WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            curr = int(row['value']) if row else 0
        await db.execute("REPLACE INTO stats (key, value) VALUES (?, ?)", (key, str(curr + 1)))
        await db.commit()
