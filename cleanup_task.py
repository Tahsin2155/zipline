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

# ============================================================================================================

WIDTH = 64


def rule(char='-'):
    print(char * WIDTH)


def fit(text, width):
    return text if len(text) <= width else text[:width - 1] + '…'


def kv(label, value):
    print(f'  {label:<12}{value}')


def stat(label, value):
    print(f'  {label:<24}{str(value):>{WIDTH - 28}}')


def db_header(index, total, name):
    print(f'[{index}/{total}] {name}')


def file_line(symbol, name, size, note):
    size_txt = format_size(size) if size is not None else '-'
    print(f'  {symbol} {fit(name, 32):<32} {size_txt:>9}  {note}')

# ============================================================================================================

def format_size(num_bytes):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num_bytes < 1024 or unit == 'GB':
            return f'{num_bytes:.1f} {unit}' if unit != 'B' else f'{num_bytes} B'
        num_bytes /= 1024


def _purge_expired_files_in_db(db_path, retention_days, display=True, dry_run=False):
    """Delete files older than retention_days from disk and from one user's DB.

    Rows are only removed when the file is gone (deleted now, or already missing). 
    If the delete fails, the row stays so the next run retries it.
    """
    conn = sqlite3.connect(db_path, timeout=30) #wait if the webapp has the DB locked
    conn.execute('PRAGMA foreign_keys = ON')
    counts = {'deleted': 0, 'missing': 0, 'failed': 0, 'bytes': 0}

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
                print('  · nothing expired')
            return counts

        ids_to_delete = []
        for file_id, file_path in expired_files:
            filename = Path(file_path).name if file_path else '<unknown>'

            if not file_path or not os.path.exists(file_path):
                counts['missing'] += 1
                ids_to_delete.append((file_id,))
                if display:
                    print(f'    ! {filename} (file already missing)')
                continue

            try:
                size = os.path.getsize(file_path)
                if not dry_run:
                    os.remove(file_path)
            except FileNotFoundError:
                counts['missing'] += 1
                ids_to_delete.append((file_id,))
                if display:
                    print(f'    ! {filename} (file already missing)')
            except OSError as e:
                # FIX: do NOT add to ids_to_delete -- keep the row, retry next run
                counts['failed'] += 1
                if display:
                    file_line('✗', filename, size, 'failed')
                    print(f'      ↳ {e}')
            else:
                counts['deleted'] += 1
                counts['bytes'] += size
                ids_to_delete.append((file_id,))
                if display:
                    file_line('✓', filename, size, 'would delete' if dry_run else 'deleted')

        if ids_to_delete and not dry_run:
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

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute('PRAGMA foreign_keys = ON')
    counts = {'present': 0, 'missing': 0}

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT file_path FROM files')
        files = cursor.fetchall()
        if not files:
            print('  · no files recorded')
            return counts

        for (file_path,) in files:
            if file_path and os.path.exists(file_path):
                counts['present'] += 1
            else:
                counts['missing'] += 1
                name = Path(file_path).name if file_path else '<unknown>'
                file_line('!', name, None, 'file missing')

        if not counts['missing']:
            print(f"  · all {counts['present']} files present")
        return counts
    finally:
        conn.close()


def check_files_all_users(database_folder):
    """Report the on-disk state of every file recorded in every user DB."""
    db_files = list(Path(database_folder).glob('*.db'))
    totals = {'present': 0, 'missing': 0}
    for index, db_file in enumerate(db_files, start=1):
        db_header(index, len(db_files), db_file.name)
        counts = check_files_in_db(str(db_file))
        for key in totals:
            totals[key] += counts[key]
        if counts['missing']:
            print(f"  → {counts['present']} present · {counts['missing']} missing")
        print()
    return totals



def purge_expired_files_all_users(database_folder, retention_days, dry_run=False):
    """Run the cleanup across every user's .db file and return all counts."""
    
    db_files = list(Path(database_folder).glob('*.db'))
    totals = {'deleted': 0, 'missing': 0, 'failed': 0, 'bytes': 0, 'db_errors': 0}
    verb = 'would delete' if dry_run else 'deleted'

    for index, db_file in enumerate(db_files, start=1):
        db_header(index, len(db_files), db_file.name)
        try:
            counts = _purge_expired_files_in_db(str(db_file), retention_days, dry_run=dry_run)
        except sqlite3.Error as e:
            # one bad DB shouldn't stop everyone else's cleanup
            totals['db_errors'] += 1
            print(f'  ✗ database error: {e}')
            print()
            continue

        for key in counts:
            totals[key] += counts[key]

        parts = []
        if counts['deleted']:
            parts.append(f"{counts['deleted']} {verb}")
        if counts['missing']:
            parts.append(f"{counts['missing']} missing")
        if counts['failed']:
            parts.append(f"{counts['failed']} failed")
        if parts:
            if counts['bytes']:
                parts.append(format_size(counts['bytes']))
            print(f"  → {' · '.join(parts)}")
        
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
    parser.add_argument(
        '--dry-run',
        action = 'store_true',
        help = 'show what would be deleted (and how much space) without deleting anything',
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

        if args.check:
            title, tag = 'ZIPLINE · FILE CHECK', 'READ-ONLY'
        elif args.dry_run:
            title, tag = 'ZIPLINE · RETENTION CLEANUP', 'DRY RUN'
        else:
            title, tag = 'ZIPLINE · RETENTION CLEANUP', 'LIVE'

        rule('=')
        print(f'  {title}'.ljust(WIDTH - len(tag) - 2) + tag)
        rule('=')
        if not args.check:
            kv('Retention', f'{args.retention_days} days')
        kv('Folder', database_folder)
        kv('Databases', db_count)
        kv('Started', started_at)
        rule('=')
        print()

        if args.check:
            totals = check_files_all_users(str(database_folder))
        else:
            totals = purge_expired_files_all_users(
                str(database_folder), args.retention_days, dry_run=args.dry_run
            )

        rule('-')
        print('  SUMMARY')
        rule('-')
        stat('Databases scanned', db_count)
        if args.check:
            stat('Files present', totals['present'])
            stat('Files missing', totals['missing'])
        else:
            stat('Would delete' if args.dry_run else 'Deleted', totals['deleted'])
            stat('Already missing', totals['missing'])
            stat('Failed', totals['failed'])
            stat('Database errors', totals['db_errors'])
            stat('Space to free' if args.dry_run else 'Space freed', format_size(totals['bytes']))
        stat('Duration', f'{time.monotonic() - started:.2f} s')
        rule('=')

        if args.check:
            result = 'File check completed.'
        elif args.dry_run:
            result = 'Dry run finished. Nothing was deleted.'
        elif totals['failed'] or totals['db_errors']:
            result = 'Cleanup completed with failures. See ✗ lines above.'
        else:
            result = 'Cleanup completed successfully.'
        print(f'  RESULT  {result}')
        rule('=')

    if not args.check and (totals['failed'] or totals['db_errors']):
        sys.exit(1)


if __name__ == '__main__':
    main()
