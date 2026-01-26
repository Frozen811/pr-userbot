import aiosqlite
import os
import logging

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'bot.db')
logger = logging.getLogger(__name__)

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                message_template TEXT DEFAULT "",
                daily_limit INTEGER DEFAULT 400,
                is_running BOOLEAN DEFAULT 0
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT,
                status TEXT DEFAULT 'active',
                next_run_at TIMESTAMP,
                last_error TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Initialize settings
        async with db.execute('SELECT count(*) FROM settings') as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                await db.execute('INSERT INTO settings (id, message_template, daily_limit, is_running) VALUES (1, "", 400, 0)')

        # Migration: Check columns in settings
        async with db.execute("PRAGMA table_info(settings)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

        if 'is_running' not in columns:
            await db.execute("ALTER TABLE settings ADD COLUMN is_running BOOLEAN DEFAULT 0")

        # Migration: Check columns in chats
        async with db.execute("PRAGMA table_info(chats)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

        if 'chat_title' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN chat_title TEXT")
        if 'status' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN status TEXT DEFAULT 'active'")
        if 'next_run_at' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN next_run_at TIMESTAMP")
        if 'last_error' not in columns:
            await db.execute("ALTER TABLE chats ADD COLUMN last_error TEXT")

        await db.commit()

async def get_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT message_template, daily_limit, is_running FROM settings WHERE id = 1') as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {"message_template": "", "daily_limit": 400, "is_running": 0}

async def update_settings(template: str, limit: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE settings SET message_template = ?, daily_limit = ? WHERE id = 1', (template, limit))
        await db.commit()

async def set_running_status(is_running: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE settings SET is_running = ? WHERE id = 1', (is_running,))
        await db.commit()

async def add_chat(chat_id: int, chat_title: str):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('INSERT INTO chats (chat_id, chat_title, status) VALUES (?, ?, ?)', (chat_id, chat_title, 'active'))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM chats WHERE chat_id = ?', (chat_id,))
        await db.commit()

async def get_chats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM chats') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def update_chat_status(chat_id: int, status: str, next_run_at=None, last_error=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE chats 
            SET status = ?, next_run_at = ?, last_error = ? 
            WHERE chat_id = ?
        ''', (status, next_run_at, last_error, chat_id))
        await db.commit()

async def update_stat(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO stats (key, value) VALUES (?, ?)', (key, str(value)))
        await db.commit()

async def get_stat(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM stats WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_media_path(path: str):
    await update_stat('media_path', path)

async def get_media_path():
    return await get_stat('media_path')
