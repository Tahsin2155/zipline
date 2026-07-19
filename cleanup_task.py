"""
Retention cleanup for expired files, meant to be run as a PythonAnywhere
"Scheduled Task" (daily), NOT as an always-on background thread.

PythonAnywhere web apps run under uWSGI without thread support enabled,
so an in-process "while True: sleep(); cleanup()" loop like a typical
local Flask app might use will not work reliably there. Instead:

  1. Go to the "Tasks" tab on PythonAnywhere.
  2. Add a new scheduled task (e.g. daily at 03:00) running:
         python3.x /home/<youruser>/dti/cleanup_task.py
  3. That's it -- this script runs once, deletes expired files, and exits.

Run locally with:
    python cleanup_task.py --once
    python cleanup_task.py --retention-days 10 --once
"""
import argparse
import os
import sqlite3
from pathlib import Path

from app import create_app
from app.config import Config


def purge_expired_files_in_db(db_path, retention_days):
    """Delete files older than retention_days from disk and a specific user DB."""
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    deleted_count = 0

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, file_path FROM files WHERE upload_date <= datetime('now', ?)",
            (f'-{retention_days} days',)
        )
        expired_files = cursor.fetchall()
        if not expired_files:
            return 0

        ids_to_delete = []
        for file_id, file_path in expired_files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except OSError as e:
                print(f'Warning: failed to delete {file_path}: {e}')
            ids_to_delete.append((file_id,))
            deleted_count += 1

        cursor.executemany('DELETE FROM files WHERE id = ?', ids_to_delete)
        conn.commit()
        return deleted_count
    finally:
        conn.close()


def purge_expired_files_all_users(database_folder, retention_days):
    db_files = list(Path(database_folder).glob('*.db'))
    total_deleted = 0
    for db_file in db_files:
        total_deleted += purge_expired_files_in_db(str(db_file), retention_days)
    return total_deleted


def main():
    parser = argparse.ArgumentParser(description='Run retention cleanup once (for use with a scheduled task).')
    parser.add_argument('--retention-days', type=int, default=Config.FILE_RETENTION_DAYS)
    args = parser.parse_args()

    if args.retention_days < 1:
        raise SystemExit('--retention-days must be >= 1')

    app = create_app()
    with app.app_context():
        deleted = purge_expired_files_all_users(app.config['DATABASE_FOLDER'], args.retention_days)
        print(f'Cleanup completed. Deleted {deleted} expired file(s).')


if __name__ == '__main__':
    main()
