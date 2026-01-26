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
    ''')

    # Create settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message_template TEXT DEFAULT '',
            is_running BOOLEAN DEFAULT 0,
            log_channel_id INTEGER DEFAULT 0
        )
    ''')

    # Create media table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            file_path TEXT DEFAULT ''
        )
    ''')

    # Create stats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_sent INTEGER DEFAULT 0,
            daily_sent INTEGER DEFAULT 0,
            last_reset_date TEXT DEFAULT '',
            start_date TEXT DEFAULT ''
        )
    ''')

    # Ensure default settings exist
    cursor.execute('SELECT count(*) FROM settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (id, message_template, is_running, log_channel_id) VALUES (1, "", 0, 0)')
    else:
        # Migration for existing settings to add log_channel_id if missing
        # Simple check: try to select log_channel_id, if fails, add column
        try:
             cursor.execute('SELECT log_channel_id FROM settings')
        except sqlite3.OperationalError:
             cursor.execute('ALTER TABLE settings ADD COLUMN log_channel_id INTEGER DEFAULT 0')

    # Ensure default media row exists
    cursor.execute('SELECT count(*) FROM media')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO media (id, file_path) VALUES (1, "")')

    # Ensure default stats row exists
    cursor.execute('SELECT count(*) FROM stats')
    if cursor.fetchone()[0] == 0:
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('INSERT INTO stats (id, total_sent, daily_sent, last_reset_date, start_date) VALUES (1, 0, 0, ?, ?)', (now, now))

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

def set_log_channel(chat_id):
    """Set the log channel ID."""
    conn = get_connection()
    conn.execute('UPDATE settings SET log_channel_id = ? WHERE id = 1', (chat_id,))
    conn.commit()
    conn.close()

def get_log_channel():
    """Get the log channel ID."""
    conn = get_connection()
    row = conn.execute('SELECT log_channel_id FROM settings WHERE id = 1').fetchone()
    conn.close()
    return row['log_channel_id'] if row else 0

def set_media(file_path):
    """Set the media file path."""
    conn = get_connection()
    conn.execute('UPDATE media SET file_path = ? WHERE id = 1', (file_path,))
    conn.commit()
    conn.close()

def get_media():
    """Get the media file path."""
    conn = get_connection()
    row = conn.execute('SELECT file_path FROM media WHERE id = 1').fetchone()
    conn.close()
    return row['file_path'] if row else ""

def clear_media():
    """Clear the media file path."""
    conn = get_connection()
    conn.execute('UPDATE media SET file_path = "" WHERE id = 1')
    conn.commit()
    conn.close()

def get_stats():
    """Get current stats."""
    conn = get_connection()
    row = conn.execute('SELECT total_sent, daily_sent, last_reset_date, start_date FROM stats WHERE id = 1').fetchone()
    conn.close()
    return dict(row) if row else {}

def increment_stats():
    """Increment total and daily sent counts."""
    conn = get_connection()
    conn.execute('UPDATE stats SET total_sent = total_sent + 1, daily_sent = daily_sent + 1 WHERE id = 1')
    conn.commit()
    conn.close()

def reset_daily_stats(date_str):
    """Reset daily stats if date changed."""
    conn = get_connection()
    conn.execute('UPDATE stats SET daily_sent = 0, last_reset_date = ? WHERE id = 1', (date_str,))
    conn.commit()
    conn.close()
