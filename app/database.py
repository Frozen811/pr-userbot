import sqlite3
import os

# Define the database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'bot.db')

def get_connection():
    """Create a database connection and return it."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create chats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT
        )
    ''') # Stores chat_id (Integer) and chat_title (Text)

    # Create settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message_template TEXT DEFAULT '',
            is_running BOOLEAN DEFAULT 0
        )
    ''') # Stores message_template (Text), is_running (Boolean)

    # Ensure default settings exist
    cursor.execute('SELECT count(*) FROM settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (id, message_template, is_running) VALUES (1, "", 0)')

    conn.commit()
    conn.close()

# Initialize on module load or manually
init_db()

def add_chat(chat_id, chat_title):
    """Add a chat ID to the database. Returns True if added, False if already exists."""
    conn = get_connection()
    try:
        conn.execute('INSERT INTO chats (chat_id, chat_title) VALUES (?, ?)', (chat_id, chat_title))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_chat(chat_id):
    """Remove a chat ID from the database."""
    conn = get_connection()
    conn.execute('DELETE FROM chats WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def get_chats():
    """Return a list of all chats as dictionaries with id and title."""
    conn = get_connection()
    rows = conn.execute('SELECT chat_id, chat_title FROM chats').fetchall()
    conn.close()
    return [{'id': row['chat_id'], 'title': row['chat_title']} for row in rows]

def set_template(text):
    """Update the message template."""
    conn = get_connection()
    conn.execute('UPDATE settings SET message_template = ? WHERE id = 1', (text,))
    conn.commit()
    conn.close()

def get_template():
    """Get the current message template."""
    conn = get_connection()
    row = conn.execute('SELECT message_template FROM settings WHERE id = 1').fetchone()
    conn.close()
    return row['message_template'] if row else ""

def set_status(is_running):
    """Set the running status (True/False)."""
    conn = get_connection()
    val = 1 if is_running else 0
    conn.execute('UPDATE settings SET is_running = ? WHERE id = 1', (val,))
    conn.commit()
    conn.close()

def get_status():
    """Get the running status."""
    conn = get_connection()
    row = conn.execute('SELECT is_running FROM settings WHERE id = 1').fetchone()
    conn.close()
    return bool(row['is_running']) if row else False
