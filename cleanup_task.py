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
import sys
import time
from datetime import datetime
from pathlib import Path

from app import create_app
from app.config import Config


def _purge_expired_files_in_db(db_path, retention_days, display=True):
    """Delete files older than retention_days from disk and from one user's DB.

    Returns counts for deleted, missing, and failed files. Each user has their
    own SQLite file (see app/db.py), so this is called once per user DB file
    found.
    """
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    counts = {'deleted': 0, 'missing': 0, 'failed': 0}

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
            if display:
                print('    No expired files.')
            return counts

        ids_to_delete = []
        for file_id, file_path in expired_files:
            filename = Path(file_path).name if file_path else '<unknown>'
            if not file_path or not os.path.exists(file_path):
                counts['missing'] += 1
                if display:
                    print(f'    ! {filename} (file already missing)')
            else:
                try:
                    os.remove(file_path)
                except FileNotFoundError:
                    counts['missing'] += 1
                    if display:
                        print(f'    ! {filename} (file already missing)')
                except OSError as e:
                    counts['failed'] += 1
                    if display:
                        print(f'    x {filename} (delete failed: {e})')
                else:
                    counts['deleted'] += 1
                    if display:
                        print(f'    ✓ {filename}')
            ids_to_delete.append((file_id,))

        cursor.executemany('DELETE FROM files WHERE id = ?', ids_to_delete)
        conn.commit()
        return counts
    finally:
        conn.close()


def purge_expired_files_in_db(db_path, retention_days):
    """Delete expired files and return the number successfully deleted."""
    return _purge_expired_files_in_db(db_path, retention_days, display=False)['deleted']


def check_files_in_db(db_path):
    """Report whether every file recorded in one database exists on disk."""
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    counts = {'present': 0, 'missing': 0}

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT file_path FROM files')
        files = cursor.fetchall()
        if not files:
            print('    No files recorded.')
            return counts

        for (file_path,) in files:
            filename = Path(file_path).name if file_path else '<unknown>'
            if file_path and os.path.exists(file_path):
                counts['present'] += 1
                print(f'    ✓ {filename}')
            else:
                counts['missing'] += 1
                print(f'    ! {filename} (file missing)')
        return counts
    finally:
        conn.close()


def check_files_all_users(database_folder):
    """Report the on-disk state of every file recorded in every user DB."""
    db_files = list(Path(database_folder).glob('*.db'))
    totals = {'present': 0, 'missing': 0}
    for index, db_file in enumerate(db_files, start=1):
        print(f'[{index}/{len(db_files)}] {db_file.name}')
        counts = check_files_in_db(str(db_file))
        for key in totals:
            totals[key] += counts[key]
        print(f"    Summary: {counts['present']} present, {counts['missing']} missing")
        print()
    return totals


def purge_expired_files_all_users(database_folder, retention_days):
    """Run the cleanup across every user's .db file and return all counts."""
    db_files = list(Path(database_folder).glob('*.db'))
    totals = {'deleted': 0, 'missing': 0, 'failed': 0}
    for index, db_file in enumerate(db_files, start=1):
        print(f'[{index}/{len(db_files)}] {db_file.name}')
        counts = _purge_expired_files_in_db(str(db_file), retention_days)
        for key in totals:
            totals[key] += counts[key]
        summary = [f"{counts['deleted']} deleted"]
        if counts['missing']:
            summary.append(f"{counts['missing']} missing")
        if counts['failed']:
            summary.append(f"{counts['failed']} failed")
        print(f"    Summary: {', '.join(summary)}")
        print()
    return totals


def main():
    parser = argparse.ArgumentParser(description='Run retention cleanup once (for use with a scheduled task).')
    # Defaults to Config.FILE_RETENTION_DAYS (app/config.py) so this
    # script and the app agree unless you explicitly override it here
    # for a single run.
    parser.add_argument('--retention-days', type=int, default=Config.FILE_RETENTION_DAYS)
    parser.add_argument(
        '--check',
        action='store_true',
        help='report the state of all recorded files without deleting anything',
    )
    args = parser.parse_args()

    if args.retention_days < 1:
        raise SystemExit('--retention-days must be >= 1')

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # create_app() is used here (rather than talking to SQLite files
    # directly with hardcoded paths) purely to reuse the app's own
    # configured DATABASE_FOLDER, so this script and the running app
    # never disagree about where the per-user databases live.
    started = time.monotonic()
    started_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    app = create_app()
    with app.app_context():
        database_folder = Path(app.config['DATABASE_FOLDER'])
        db_count = len(list(database_folder.glob('*.db')))
        print('=' * 58)
        print(' ZIPLINE FILE CHECK' if args.check else ' ZIPLINE RETENTION CLEANUP')
        print('=' * 58)
        print(f' Retention period : {args.retention_days} days')
        print(f' Database folder  : {database_folder}')
        print(f' Started          : {started_at}')
        print()
        print(f'Found {db_count} database(s) to scan.')
        print()

        if args.check:
            totals = check_files_all_users(str(database_folder))
        else:
            totals = purge_expired_files_all_users(str(database_folder), args.retention_days)

        print('-' * 58)
        print(' FILE CHECK SUMMARY' if args.check else ' CLEANUP SUMMARY')
        print('-' * 58)
        print(f' Databases scanned : {db_count}')
        if args.check:
            print(f" Files present     : {totals['present']}")
            print(f" Files missing     : {totals['missing']}")
        else:
            print(f" Files deleted     : {totals['deleted']}")
            print(f" Files missing     : {totals['missing']}")
            print(f" Files failed      : {totals['failed']}")
        print(f' Duration          : {time.monotonic() - started:.2f}s')
        print()
        if not args.check and totals['failed']:
            print('Cleanup completed with failures.')
        elif args.check:
            print('File check completed.')
        else:
            print('Cleanup completed successfully.')


if __name__ == '__main__':
    main()
