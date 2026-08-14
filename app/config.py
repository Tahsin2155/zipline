import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-only-change-this-in-production')

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    DATABASE_FOLDER = os.path.join(BASE_DIR, 'databases')
    USERS_FILE = os.path.join(BASE_DIR, 'users.json')

    MAX_FILE_SIZE = 100 * 1024 * 1024        # 100MB per file
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024   # 100MB per request
    USER_STORAGE_QUOTA = 100 * 1024 * 1024  # 75MB per user (adjust for your PA plan's disk quota)

    FILE_RETENTION_DAYS = 5
    FILES_PER_PAGE = 25

    # Extensions we refuse to store, regardless of who uploads them.
    # This is a blocklist, not a strict allowlist, since the app is meant
    # to transfer "any" file type for personal use.
    BLOCKED_EXTENSIONS = {
        'exe', 'bat', 'cmd', 'com', 'msi', 'msp', 'scr', 'ps1', 'psm1',
        'sh', 'bash', 'run',
        'jar', 'jse', 'vbs', 'vbe', 'wsf', 'wsh',
        'app', 'dmg', 'pkg',
    }

    # Extensions considered previewable as plain text/code in-browser.
    TEXT_PREVIEW_EXTENSIONS = {
        'txt', 'md', 'markdown', 'py', 'js', 'jsx', 'ts', 'tsx', 'html', 'htm',
        'css', 'json', 'xml', 'yml', 'yaml', 'ini', 'cfg', 'conf', 'toml',
        'c', 'h', 'cpp', 'hpp', 'java', 'rb', 'go', 'rs', 'php', 'sql',
        'sh', 'bash', 'log', 'csv', 'tsv', 'gitignore', 'env',
    }
    IMAGE_PREVIEW_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'}
    PDF_PREVIEW_EXTENSIONS = {'pdf'}

    # How much of a text file to read for preview (bytes)
    TEXT_PREVIEW_MAX_BYTES = 50 * 1024  # 50KB
