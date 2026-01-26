import aiosqlite
import os
from datetime import datetime

# Путь к базе данных
DB_PATH = "app/data/bot.db"


async def init_db():
    """Инициализация базы и миграции"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Таблица чатов
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS chats
                         (
                             chat_id
                             INTEGER
                             PRIMARY
                             KEY,
                             chat_name
                             TEXT,
                             status
                             TEXT
                             DEFAULT
                             'active',
                             next_run_at
                             TIMESTAMP,
                             last_error
                             TEXT
                         )
                         """)

        # 2. Таблица настроек/статистики
        # (Удаляем старую, если она была кривая)
        await db.execute("DROP TABLE IF EXISTS stats")
        await db.execute("""
                         CREATE TABLE stats
                         (
                             key   TEXT PRIMARY KEY,
                             value TEXT
                         )
                         """)

        # 3. Устанавливаем дефолтные настройки (если их нет)
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('daily_limit', '400')")
        await db.execute(
            "INSERT OR IGNORE INTO stats (key, value) VALUES ('broadcast_text', 'Привет! Настрой меня через админку.')")
        await db.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_sent', '0')")

        # 4. МИГРАЦИЯ ЧАТОВ
        cursor = await db.execute("PRAGMA table_info(chats)")
        columns_info = await cursor.fetchall()
        columns = [col[1] for col in columns_info]

        if "status" not in columns:
            print("🛠 Migrating DB: Adding 'status' column...")
            await db.execute("ALTER TABLE chats ADD COLUMN status TEXT DEFAULT 'active'")

        if "next_run_at" not in columns:
            print("🛠 Migrating DB: Adding 'next_run_at' column...")
            await db.execute("ALTER TABLE chats ADD COLUMN next_run_at TIMESTAMP")

        if "last_error" not in columns:
            print("🛠 Migrating DB: Adding 'last_error' column...")
            await db.execute("ALTER TABLE chats ADD COLUMN last_error TEXT")

        await db.commit()


async def add_chat(chat_id, chat_name):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                             INSERT
                             OR IGNORE INTO chats (chat_id, chat_name, status) 
                VALUES (?, ?, 'active')
                             """, (chat_id, chat_name))
            await db.commit()
            return True
        except Exception:
            return False


async def get_chats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM chats")
        return await cursor.fetchall()


async def remove_chat(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def update_chat_status(chat_id, status, next_run_at=None, last_error=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
                         UPDATE chats
                         SET status      = ?,
                             next_run_at = ?,
                             last_error  = ?
                         WHERE chat_id = ?
                         """, (status, next_run_at, last_error, chat_id))
        await db.commit()


async def update_stat(key, value):
    """Обновить одну настройку"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO stats (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()


async def get_stat(key):
    """Получить одну настройку"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM stats WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_settings():
    """Получить ВСЕ настройки словарем (ВОТ ЭТОЙ ФУНКЦИИ НЕ ХВАТАЛО)"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM stats")
        rows = await cursor.fetchall()
        # Превращаем [('limit', '400'), ...] в {'limit': '400', ...}
        return {row[0]: row[1] for row in rows}