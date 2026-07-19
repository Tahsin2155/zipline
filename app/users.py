"""
users.json loading with mtime-based caching, and password verification.

Password storage format in users.json, per username:
    {
        "username": {
            "password": "<werkzeug hash>",
            "created_at": "...",
            "failed_logins": 0,
            "locked_until": null
        }
    }

A legacy format (plain string value = plaintext password) is migrated
in-place to a hash the first time that user logs in successfully, so
old users.json files (like the original single "me": "meme" entry)
keep working without manual intervention.
"""
import json
import os
import threading
import time

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

_CACHE_LOCK = threading.Lock()
_CACHE_MTIME = None
_CACHE_DATA = {}

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _users_file():
    return current_app.config['USERS_FILE']


def _load_raw():
    path = _users_file()
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump({}, f, indent=4)
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_users():
    """Load users.json with mtime-based cache to reduce disk IO."""
    global _CACHE_MTIME, _CACHE_DATA

    path = _users_file()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return _load_raw()

    with _CACHE_LOCK:
        if _CACHE_MTIME == mtime:
            return _CACHE_DATA

        data = _load_raw()
        _CACHE_MTIME = mtime
        _CACHE_DATA = data
        return _CACHE_DATA


def save_users(users):
    """Persist users.json and invalidate the cache."""
    global _CACHE_MTIME, _CACHE_DATA

    path = _users_file()
    with _CACHE_LOCK:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4)
        _CACHE_MTIME = os.path.getmtime(path)
        _CACHE_DATA = users


def _normalize_record(record):
    """Return a dict record regardless of legacy (string) or new (dict) shape."""
    if isinstance(record, str):
        return {'password': record, 'failed_logins': 0, 'locked_until': None, '_legacy_plain': True}
    if isinstance(record, dict):
        record.setdefault('failed_logins', 0)
        record.setdefault('locked_until', None)
        return record
    return None


def get_user_record(username):
    users = load_users()
    if username not in users:
        return None
    return _normalize_record(users[username])


def is_locked_out(record):
    locked_until = record.get('locked_until')
    if not locked_until:
        return False
    return time.time() < locked_until


def verify_password(username, supplied_password):
    """
    Verify credentials, migrating legacy plaintext entries to a hash on
    successful login. Returns True/False. Does not itself update
    failed-login counters -- callers handle that via record_login_result.
    """
    users = load_users()
    record = users.get(username)
    if record is None:
        return False

    normalized = _normalize_record(record)
    if normalized is None:
        return False

    stored = normalized.get('password', '')
    ok = False

    try:
        ok = check_password_hash(stored, supplied_password)
    except (ValueError, TypeError):
        ok = False

    if not ok and normalized.get('_legacy_plain'):
        # Legacy plaintext fallback comparison (constant-time not critical
        # here since this path only exists for old manually-edited files).
        ok = stored == supplied_password

    if ok and normalized.get('_legacy_plain'):
        # Migrate to a hash so plaintext never persists again.
        users[username] = {
            'password': generate_password_hash(supplied_password),
            'failed_logins': 0,
            'locked_until': None,
        }
        save_users(users)

    return ok


def record_login_result(username, success):
    """Update failed-login counters / lockout for basic brute-force protection."""
    users = load_users()
    record = users.get(username)
    if record is None:
        return

    normalized = _normalize_record(record)
    if normalized is None:
        return

    if success:
        normalized['failed_logins'] = 0
        normalized['locked_until'] = None
    else:
        normalized['failed_logins'] = normalized.get('failed_logins', 0) + 1
        if normalized['failed_logins'] >= LOGIN_MAX_ATTEMPTS:
            normalized['locked_until'] = time.time() + LOGIN_LOCKOUT_SECONDS

    normalized.pop('_legacy_plain', None)
    users[username] = normalized
    save_users(users)
