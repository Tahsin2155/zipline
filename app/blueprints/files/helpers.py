import os

from flask import current_app


def get_extension(filename):
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def is_blocked_extension(filename):
    return get_extension(filename) in current_app.config['BLOCKED_EXTENSIONS']


def preview_kind(filename):
    """Return 'image' | 'pdf' | 'text' | None based on extension."""
    ext = get_extension(filename)
    cfg = current_app.config
    if ext in cfg['IMAGE_PREVIEW_EXTENSIONS']:
        return 'image'
    if ext in cfg['PDF_PREVIEW_EXTENSIONS']:
        return 'pdf'
    if ext in cfg['TEXT_PREVIEW_EXTENSIONS']:
        return 'text'
    return None


def read_text_preview(file_path):
    """
    Read up to TEXT_PREVIEW_MAX_BYTES of a text file for inline preview.
    Returns (content, was_truncated). Falls back gracefully on decode errors.
    """
    max_bytes = current_app.config['TEXT_PREVIEW_MAX_BYTES']
    try:
        with open(file_path, 'rb') as f:
            raw = f.read(max_bytes + 1)
    except OSError:
        return '', False

    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]

    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('utf-8', errors='replace')

    return text, truncated


def folder_breadcrumbs(cursor, folder_id):
    """Return list of {id, name} from root down to folder_id (inclusive)."""
    crumbs = []
    current_id = folder_id
    # Cap iterations defensively in case of any data corruption creating a cycle.
    for _ in range(100):
        if current_id is None:
            break
        cursor.execute('SELECT id, name, parent_id FROM folders WHERE id = ?', (current_id,))
        row = cursor.fetchone()
        if row is None:
            break
        crumbs.append({'id': row[0], 'name': row[1]})
        current_id = row[2]
    crumbs.reverse()
    return crumbs


def subfolder_ids_recursive(cursor, folder_id):
    """Return a set of all folder ids nested (at any depth) under folder_id, inclusive."""
    ids = {folder_id}
    frontier = [folder_id]
    while frontier:
        placeholder = ','.join('?' * len(frontier))
        cursor.execute(f'SELECT id FROM folders WHERE parent_id IN ({placeholder})', frontier)
        found = [r[0] for r in cursor.fetchall()]
        new_ids = [i for i in found if i not in ids]
        ids.update(new_ids)
        frontier = new_ids
    return ids


def compute_user_storage_bytes(cursor):
    cursor.execute('SELECT COALESCE(SUM(file_size), 0) FROM files')
    return cursor.fetchone()[0] or 0


def user_upload_dir(username, safe_username_fn):
    safe_username = safe_username_fn(username)
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_username)
    os.makedirs(path, exist_ok=True)
    return path
