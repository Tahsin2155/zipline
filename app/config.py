"""
All tunable settings for Zipline, in one place.

Every setting below is a class attribute on Config, which Flask loads via
app.config.from_object(Config) in app/__init__.py. See guide.md ("5.
Configuration") for a summary table and deployment-specific guidance --
this file is the detailed, in-place reference for exactly what each
setting does.
"""
import os
from datetime import timedelta

# The project root (one level up from app/), used to build absolute
# paths below regardless of what directory you happen to run the app
# from.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    # Signs and verifies session cookies. The fallback string here is
    # ONLY for local development -- anyone who knows it could forge a
    # valid session cookie for your app. Before deploying anywhere
    # reachable over a network, set the FLASK_SECRET_KEY environment
    # variable to a real random value, e.g.:
    #     python -c "import secrets; print(secrets.token_hex(32))"
    # See guide.md, "Setting the secret key".
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-only-change-this-in-production')

    # Logged-in sessions expire after 30 minutes of inactivity. Session is
    # marked permanent at login (see auth/routes.py) so this applies; each
    # request that touches the session resets the 30-minute countdown
    # (SESSION_REFRESH_EACH_REQUEST defaults to True), so it's an idle
    # timeout, not a hard cutoff from login time.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)

    # Where uploaded files, per-user SQLite databases, and the users.json
    # credentials file live on disk. All three are auto-created on
    # startup if missing (see app/__init__.py).
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    DATABASE_FOLDER = os.path.join(BASE_DIR, 'databases')
    USERS_FILE = os.path.join(BASE_DIR, 'users.json')

    # Upload size limits. MAX_FILE_SIZE is used by the app's own
    # validation logic; MAX_CONTENT_LENGTH is a Flask/Werkzeug setting
    # that rejects oversized request bodies before they're even fully
    # read. Keep these in sync -- they're set to the same value here
    # deliberately. Raise both if you need to move bigger files and your
    # host has the disk/bandwidth for it.
    MAX_FILE_SIZE = 100 * 1024 * 1024        # 100MB per file
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024   # 100MB per request

    # Total storage allowed per user (sum of all their uploaded files),
    # not a per-file limit. Tune this to whatever disk quota your actual
    # host gives you -- the comment below is a reminder from when this
    # was tuned for a specific PythonAnywhere plan; adjust freely.
    USER_STORAGE_QUOTA = 100 * 1024 * 1024  # 100MB per user (adjust for your PA plan's disk quota)

    # How many days a file is kept before cleanup_task.py deletes it.
    # Only takes effect when that script is actually scheduled to run --
    # see guide.md, "Scheduling the cleanup task". Override for a single
    # run without editing this file via `python cleanup_task.py
    # --retention-days N`.
    FILE_RETENTION_DAYS = 5

    # How many files are shown per page on the dashboard listing.
    FILES_PER_PAGE = 25

    # Extensions we refuse to store, regardless of who uploads them.
    # This is a blocklist, not a strict allowlist, since the app is meant
    # to transfer "any" file type for personal use. Add to this set if
    # you want to be stricter about what can be uploaded.
    BLOCKED_EXTENSIONS = {
        'exe', 'bat', 'cmd', 'com', 'msi', 'msp', 'scr', 'ps1', 'psm1',
        'sh', 'bash', 'run',
        'jar', 'jse', 'vbs', 'vbe', 'wsf', 'wsh',
        'app', 'dmg', 'pkg',
    }

    # Extensions considered previewable as plain text/code in-browser
    # (rendered in a modal rather than downloaded).
    TEXT_PREVIEW_EXTENSIONS = {
        'txt', 'md', 'markdown', 'py', 'js', 'jsx', 'ts', 'tsx', 'html', 'htm',
        'css', 'json', 'xml', 'yml', 'yaml', 'ini', 'cfg', 'conf', 'toml',
        'c', 'h', 'cpp', 'hpp', 'java', 'rb', 'go', 'rs', 'php', 'sql',
        'sh', 'bash', 'log', 'csv', 'tsv', 'gitignore', 'env',
    }
    # Extensions rendered as inline <img> previews.
    IMAGE_PREVIEW_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'}
    # Extensions rendered as inline PDF previews (via the browser's own
    # PDF viewer, embedded in the page).
    PDF_PREVIEW_EXTENSIONS = {'pdf'}

    # How much of a text/code file is read for its inline preview before
    # it's truncated (with a download link shown for the rest). Keeps a
    # huge log or data file from making the preview modal unusably slow
    # or heavy to load.
    TEXT_PREVIEW_MAX_BYTES = 50 * 1024  # 50KB
