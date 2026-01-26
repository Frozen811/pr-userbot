import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'bot.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message_template TEXT,
            is_running BOOLEAN DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY
        )
    ''')
    
    # Initialize settings if not present
    cursor.execute('SELECT count(*) FROM settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (id, message_template, is_running) VALUES (1, "", 0)')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_template():
    conn = get_db_connection()
    row = conn.execute('SELECT message_template FROM settings WHERE id = 1').fetchone()
    conn.close()
    return row['message_template'] if row else ""

def set_template(template):
    conn = get_db_connection()
    conn.execute('UPDATE settings SET message_template = ? WHERE id = 1', (template,))
    conn.commit()
    conn.close()

def get_status():
    conn = get_db_connection()
    row = conn.execute('SELECT is_running FROM settings WHERE id = 1').fetchone()
    conn.close()
    return bool(row['is_running']) if row else False

def set_status(is_running):
    conn = get_db_connection()
    conn.execute('UPDATE settings SET is_running = ? WHERE id = 1', (is_running,))
    conn.commit()
    conn.close()

def add_chat(chat_id):
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO chats (chat_id) VALUES (?)', (chat_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_chat(chat_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM chats WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def get_chats():
    conn = get_db_connection()
    chats = conn.execute('SELECT chat_id FROM chats').fetchall()
    conn.close()
    return [chat['chat_id'] for chat in chats]
