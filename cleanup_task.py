"""
Retention cleanup for expired files.

This script deletes files older than FILE_RETENTION_DAYS (from
app/config.py, overridable with --retention-days) once, across every
user's database, and then exits. It is meant to be triggered by an
external scheduler (a cron job, or PythonAnywhere's "Scheduled Task"
system) -- NOT run as an always-on background thread inside the web
process.

Why not a background thread: some hosting setups (PythonAnywhere's web
apps in particular) run under a WSGI server without reliable thread
support, so a typical "while True: sleep(); cleanup()" loop living
inside the Flask app won't run reliably there. A one-shot script you
schedule externally sidesteps that entirely and works the same way
everywhere.

Scheduling examples (see guide.md for the full walkthrough):

  PythonAnywhere -- Tasks tab, daily task running:
      python3.x /home/<youruser>/zipline/cleanup_task.py

  A normal Linux server -- cron entry:
      0 3 * * * cd /home/you/zipline && /home/you/zipline/.venv/bin/python cleanup_task.py

Run it manually / locally with:
    python cleanup_task.py
    python cleanup_task.py --retention-days 10
"""
import argparse
import os
import sqlite3
from pathlib import Path

from app import create_app
from app.config import Config


def purge_expired_files_in_db(db_path, retention_days):
    """Delete files older than retention_days from disk and from one user's DB.

    Returns the number of files deleted. Each user has their own SQLite
    file (see app/db.py), so this is called once per user DB file found.
    """
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    deleted_count = 0

    try:
        cursor = conn.cursor()
        # SQLite's datetime('now', '-N days') does the age comparison in
        # the query itself, so we only fetch rows that are actually
        # expired rather than pulling everything and filtering in Python.
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
                # Don't let one bad file (permissions, already gone,
                # etc.) abort the whole cleanup run -- log it and keep
                # going, but still remove its DB row below so it doesn't
                # get retried forever if the underlying issue can't be
                # fixed automatically.
                print(f'Warning: failed to delete {file_path}: {e}')
            ids_to_delete.append((file_id,))
            deleted_count += 1

        cursor.executemany('DELETE FROM files WHERE id = ?', ids_to_delete)
        conn.commit()
        return deleted_count
    finally:
        conn.close()


def purge_expired_files_all_users(database_folder, retention_days):
    """Run purge_expired_files_in_db() across every user's .db file."""
    db_files = list(Path(database_folder).glob('*.db'))
    total_deleted = 0
    for db_file in db_files:
        total_deleted += purge_expired_files_in_db(str(db_file), retention_days)
    return total_deleted


def main():
    parser = argparse.ArgumentParser(description='Run retention cleanup once (for use with a scheduled task).')
    # Defaults to Config.FILE_RETENTION_DAYS (app/config.py) so this
    # script and the app agree unless you explicitly override it here
    # for a single run.
    parser.add_argument('--retention-days', type=int, default=Config.FILE_RETENTION_DAYS)
    args = parser.parse_args()

    if args.retention_days < 1:
        raise SystemExit('--retention-days must be >= 1')

    # create_app() is used here (rather than talking to SQLite files
    # directly with hardcoded paths) purely to reuse the app's own
    # configured DATABASE_FOLDER, so this script and the running app
    # never disagree about where the per-user databases live.
    app = create_app()
    with app.app_context():
        deleted = purge_expired_files_all_users(app.config['DATABASE_FOLDER'], args.retention_days)
        print(f'Cleanup completed. Deleted {deleted} expired file(s).')


if __name__ == '__main__':
    main()
