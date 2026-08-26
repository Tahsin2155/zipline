"""
Per-user SQLite database helpers.

Each user gets their own SQLite file under DATABASE_FOLDER, containing:
  - folders: nested folder structure (self-referencing parent_id)
  - files:   uploaded file metadata, optionally inside a folder
  - notes:   scratchpad notes, one row per note, per user

Schema creation is idempotent (CREATE TABLE IF NOT EXISTS) and is checked
once per db file per process, cached in _SCHEMA_INITIALIZED_DBS to avoid
re-running the checks on every request.
"""
import os
import sqlite3
import threading

from flask import current_app
from werkzeug.utils import secure_filename

_SCHEMA_INIT_LOCK = threading.Lock()
_SCHEMA_INITIALIZED_DBS = set()


def sanitize_username(username):
    """Return a filesystem-safe username for path usage."""
    cleaned = secure_filename(username)
    return cleaned or 'user'


def _db_path_for(username):
    safe_username = sanitize_username(username)
    return os.path.join(current_app.config['DATABASE_FOLDER'], f'{safe_username}.db')


def _notes_table_is_legacy(cursor):
    """True if a `notes` table exists but predates the multi-note upgrade
    (i.e. it's the old single-row id=1 schema without a `title` column)."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes'")
    if cursor.fetchone() is None:
        return False
    cursor.execute("PRAGMA table_info(notes)")
    columns = {row[1] for row in cursor.fetchall()}
    return 'title' not in columns


def ensure_schema(conn):
    """Create required tables/indexes for a user DB (idempotent)."""
    cursor = conn.cursor()

    # The `notes` table changed shape (single-row scratchpad -> one row per
    # note). Old DB files predate this and would otherwise sit around with
    # the incompatible schema forever, since CREATE TABLE IF NOT EXISTS
    # skips a table that already exists. There's no real user data riding
    # on the old single-note table, so just drop and recreate it.
    if _notes_table_is_legacy(cursor):
        cursor.execute('DROP TABLE notes')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES folders(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            folder_id INTEGER,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_size INTEGER,
            file_type TEXT,
            FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Untitled',
            content TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_upload_date ON files(upload_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_folder_id ON files(folder_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_folders_parent_id ON folders(parent_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_sort_order ON notes(sort_order)')

    conn.commit()


def get_user_db(username):
    """Get a connection to a user's SQLite database, creating schema if needed."""
    db_path = _db_path_for(username)
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')

    if db_path not in _SCHEMA_INITIALIZED_DBS:
        with _SCHEMA_INIT_LOCK:
            if db_path not in _SCHEMA_INITIALIZED_DBS:
                ensure_schema(conn)
                _SCHEMA_INITIALIZED_DBS.add(db_path)

    return conn


def user_db_path(username):
    return _db_path_for(username)
