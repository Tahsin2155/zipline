import os
from datetime import datetime

from flask import (
    abort, current_app, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for
)
from werkzeug.utils import secure_filename

from app.blueprints.files import files_bp
from app.blueprints.files.helpers import (
    compute_user_storage_bytes, folder_breadcrumbs, get_extension,
    is_blocked_extension, preview_kind, read_text_preview,
    subfolder_ids_recursive,
)
from app.db import get_user_db, sanitize_username
from app.decorators import login_required


def _user_upload_dir(username):
    safe_username = sanitize_username(username)
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_username)
    os.makedirs(path, exist_ok=True)
    return path


def _save_streamed_file(uploaded_file, destination_path, max_size):
    """Stream file to disk and enforce per-file max size without loading whole file in memory."""
    bytes_written = 0
    chunk_size = 1024 * 1024

    with open(destination_path, 'wb') as out_file:
        while True:
            chunk = uploaded_file.stream.read(chunk_size)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_size:
                out_file.close()
                os.remove(destination_path)
                raise ValueError(
                    f'File too large. Maximum size is {max_size / (1024 * 1024):.0f}MB.'
                )
            out_file.write(chunk)

    return bytes_written


@files_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard - browse current folder, upload, search."""
    username = session['username']
    page = request.args.get('page', 1, type=int) or 1
    folder_id = request.args.get('folder', type=int)  # None = root
    search_query = request.args.get('q', '').strip()

    per_page = current_app.config['FILES_PER_PAGE']
    conn = get_user_db(username)
    cursor = conn.cursor()

    # Validate folder_id exists (if given), else silently fall back to root.
    if folder_id is not None:
        cursor.execute('SELECT id FROM folders WHERE id = ?', (folder_id,))
        if cursor.fetchone() is None:
            folder_id = None

    if search_query:
        # Search across ALL folders by filename, ignore folder scoping.
        like_query = f'%{search_query}%'
        cursor.execute('SELECT COUNT(*) FROM files WHERE original_filename LIKE ?', (like_query,))
        total_files = cursor.fetchone()[0]
        total_pages = max(1, (total_files + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page
        cursor.execute(
            '''SELECT id, original_filename, upload_date, file_size, folder_id
               FROM files WHERE original_filename LIKE ?
               ORDER BY upload_date DESC LIMIT ? OFFSET ?''',
            (like_query, per_page, offset)
        )
        rows = cursor.fetchall()
        subfolders = []
        breadcrumbs = []
    else:
        if folder_id is None:
            cursor.execute('SELECT COUNT(*) FROM files WHERE folder_id IS NULL')
        else:
            cursor.execute('SELECT COUNT(*) FROM files WHERE folder_id = ?', (folder_id,))
        total_files = cursor.fetchone()[0]
        total_pages = max(1, (total_files + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        if folder_id is None:
            cursor.execute(
                '''SELECT id, original_filename, upload_date, file_size, folder_id
                   FROM files WHERE folder_id IS NULL
                   ORDER BY upload_date DESC LIMIT ? OFFSET ?''',
                (per_page, offset)
            )
        else:
            cursor.execute(
                '''SELECT id, original_filename, upload_date, file_size, folder_id
                   FROM files WHERE folder_id = ?
                   ORDER BY upload_date DESC LIMIT ? OFFSET ?''',
                (folder_id, per_page, offset)
            )
        rows = cursor.fetchall()

        if folder_id is None:
            cursor.execute('SELECT id, name FROM folders WHERE parent_id IS NULL ORDER BY name COLLATE NOCASE')
        else:
            cursor.execute('SELECT id, name FROM folders WHERE parent_id = ? ORDER BY name COLLATE NOCASE', (folder_id,))
        subfolders = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]

        breadcrumbs = folder_breadcrumbs(cursor, folder_id) if folder_id is not None else []

    total_size_bytes = compute_user_storage_bytes(cursor)
    quota_bytes = current_app.config['USER_STORAGE_QUOTA']
    conn.close()

    formatted_files = []
    for file_id, filename, upload_date, file_size, f_folder_id in rows:
        size_mb = file_size / (1024 * 1024) if file_size else 0
        formatted_files.append({
            'id': file_id,
            'filename': filename,
            'upload_date': upload_date,
            'size': f"{size_mb:.2f} MB",
            'extension': get_extension(filename),
            'previewable': preview_kind(filename) is not None,
            'folder_id': f_folder_id,
        })

    return render_template(
        'files/dashboard.html',
        username=username,
        files=formatted_files,
        subfolders=subfolders,
        breadcrumbs=breadcrumbs,
        current_folder_id=folder_id,
        file_count=total_files,
        total_size_mb=round(total_size_bytes / (1024 * 1024), 2),
        quota_mb=round(quota_bytes / (1024 * 1024), 2),
        quota_percent=min(100, round((total_size_bytes / quota_bytes) * 100, 1)) if quota_bytes else 0,
        page=page,
        total_pages=total_pages,
        search_query=search_query,
    )


@files_bp.route('/folders/create', methods=['POST'])
@login_required
def create_folder():
    username = session['username']
    name = request.form.get('name', '').strip()
    parent_id = request.form.get('parent_id', type=int)

    if not name:
        flash('Folder name cannot be empty.', 'warning')
        return redirect(url_for('files.dashboard', folder=parent_id))

    if len(name) > 100:
        flash('Folder name is too long.', 'warning')
        return redirect(url_for('files.dashboard', folder=parent_id))

    conn = get_user_db(username)
    cursor = conn.cursor()

    if parent_id is not None:
        cursor.execute('SELECT id FROM folders WHERE id = ?', (parent_id,))
        if cursor.fetchone() is None:
            parent_id = None

    cursor.execute('INSERT INTO folders (name, parent_id) VALUES (?, ?)', (name, parent_id))
    conn.commit()
    conn.close()

    flash(f'Folder "{name}" created.', 'success')
    return redirect(url_for('files.dashboard', folder=parent_id))


@files_bp.route('/folders/<int:folder_id>/rename', methods=['POST'])
@login_required
def rename_folder(folder_id):
    username = session['username']
    new_name = request.form.get('name', '').strip()

    if not new_name:
        return jsonify({'success': False, 'message': 'Name cannot be empty'}), 400
    if len(new_name) > 100:
        return jsonify({'success': False, 'message': 'Name is too long'}), 400

    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT id, parent_id FROM folders WHERE id = ?', (folder_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return jsonify({'success': False, 'message': 'Folder not found'}), 404

    cursor.execute('UPDATE folders SET name = ? WHERE id = ?', (new_name, folder_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'name': new_name})


@files_bp.route('/folders/<int:folder_id>/delete', methods=['POST'])
@login_required
def delete_folder(folder_id):
    """Delete a folder and everything nested inside it, including files on disk."""
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()

    cursor.execute('SELECT id, parent_id FROM folders WHERE id = ?', (folder_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return jsonify({'success': False, 'message': 'Folder not found'}), 404

    parent_id = row[1]
    all_ids = subfolder_ids_recursive(cursor, folder_id)

    placeholder = ','.join('?' * len(all_ids))
    cursor.execute(f'SELECT file_path FROM files WHERE folder_id IN ({placeholder})', list(all_ids))
    paths = [r[0] for r in cursor.fetchall()]

    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            current_app.logger.warning('Failed to delete file on disk during folder delete: %s', path)

    # ON DELETE CASCADE handles files + nested folders once the top folder is removed,
    # since foreign_keys pragma is enabled per-connection in get_user_db.
    cursor.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'redirect': url_for('files.dashboard', folder=parent_id)})


def _wants_json():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@files_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    """Handle file upload into the current folder.

    Supports two callers:
      - The dashboard's XHR-based uploader (sends X-Requested-With header),
        which gets a JSON response so it can show per-file progress/result.
      - A plain HTML form fallback (e.g. JS disabled), which gets the
        original flash+redirect behavior.
    """
    username = session['username']
    folder_id = request.form.get('folder_id', type=int)
    wants_json = _wants_json()

    def respond(success, message, status=200):
        if wants_json:
            return jsonify({'success': success, 'message': message}), status
        flash(message, 'success' if success else 'warning')
        return redirect(url_for('files.dashboard', folder=folder_id))

    if 'file' not in request.files:
        return respond(False, 'No file selected.', 400)

    files_to_upload = request.files.getlist('file')
    if not files_to_upload or all(f.filename == '' for f in files_to_upload):
        return respond(False, 'No file selected.', 400)

    conn = get_user_db(username)
    cursor = conn.cursor()

    if folder_id is not None:
        cursor.execute('SELECT id FROM folders WHERE id = ?', (folder_id,))
        if cursor.fetchone() is None:
            folder_id = None

    quota_bytes = current_app.config['USER_STORAGE_QUOTA']
    current_usage = compute_user_storage_bytes(cursor)

    successful_uploads = 0
    rejected = []

    try:
        user_dir = _user_upload_dir(username)

        for file in files_to_upload:
            if file.filename == '':
                continue

            original_filename = secure_filename(file.filename)
            if not original_filename:
                continue

            if is_blocked_extension(original_filename):
                rejected.append(f'{original_filename} (blocked file type)')
                continue

            if current_usage >= quota_bytes:
                rejected.append(f'{original_filename} (storage quota exceeded)')
                continue

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f_')
            unique_filename = timestamp + original_filename
            file_path = os.path.join(user_dir, unique_filename)

            remaining_quota = quota_bytes - current_usage
            max_allowed = min(current_app.config['MAX_FILE_SIZE'], remaining_quota)

            try:
                file_size = _save_streamed_file(file, file_path, max_allowed)
            except ValueError as e:
                rejected.append(f'{original_filename} ({e})')
                continue

            cursor.execute('''
                INSERT INTO files (filename, original_filename, file_path, folder_id, file_size, file_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (unique_filename, original_filename, file_path, folder_id, file_size, file.content_type))
            successful_uploads += 1
            current_usage += file_size

        conn.commit()
        conn.close()

        if successful_uploads and not rejected:
            return respond(True, f'Uploaded {successful_uploads} file(s) successfully.')
        if successful_uploads and rejected:
            return respond(True, f'Uploaded, but skipped: {"; ".join(rejected)}')
        if rejected:
            return respond(False, 'Skipped: ' + '; '.join(rejected), 400)
        return respond(False, 'No valid files were uploaded.', 400)

    except Exception:
        current_app.logger.exception('Upload failed')
        conn.close()
        return respond(False, 'Upload failed. Please try again.', 500)


@files_bp.route('/download/<int:file_id>')
@login_required
def download(file_id):
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path, original_filename FROM files WHERE id = ?', (file_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        flash('File not found.', 'danger')
        return redirect(url_for('files.dashboard'))

    file_path, original_filename = result

    if not os.path.exists(file_path):
        flash('File not found on server.', 'danger')
        return redirect(url_for('files.dashboard'))

    return send_file(file_path, as_attachment=True, download_name=original_filename)


@files_bp.route('/preview/<int:file_id>')
@login_required
def preview(file_id):
    """Serve inline preview data for images, PDFs, and text/code files."""
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path, original_filename, file_type FROM files WHERE id = ?', (file_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        abort(404)

    file_path, original_filename, file_type = result
    if not os.path.exists(file_path):
        abort(404)

    kind = preview_kind(original_filename)
    if kind is None:
        abort(415)

    if kind == 'image':
        return send_file(file_path, mimetype=file_type or 'application/octet-stream')

    if kind == 'pdf':
        return send_file(file_path, mimetype='application/pdf')

    if kind == 'text':
        content, truncated = read_text_preview(file_path)
        return jsonify({'content': content, 'truncated': truncated, 'filename': original_filename})

    abort(415)


@files_bp.route('/delete/<int:file_id>', methods=['POST'])
@login_required
def delete(file_id):
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path, original_filename FROM files WHERE id = ?', (file_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({'success': False, 'message': 'File not found'}), 404

    file_path, original_filename = result

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'File "{original_filename}" deleted successfully'})
    except Exception:
        current_app.logger.exception('Delete failed for file_id=%s', file_id)
        conn.close()
        return jsonify({'success': False, 'message': 'Delete failed. Please try again.'}), 500


@files_bp.route('/files/<int:file_id>/move', methods=['POST'])
@login_required
def move_file(file_id):
    """Move a file into a different folder (or root if folder_id omitted)."""
    username = session['username']
    folder_id = request.form.get('folder_id', type=int)

    conn = get_user_db(username)
    cursor = conn.cursor()

    if folder_id is not None:
        cursor.execute('SELECT id FROM folders WHERE id = ?', (folder_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'success': False, 'message': 'Target folder not found'}), 404

    cursor.execute('SELECT id FROM files WHERE id = ?', (file_id,))
    if cursor.fetchone() is None:
        conn.close()
        return jsonify({'success': False, 'message': 'File not found'}), 404

    cursor.execute('UPDATE files SET folder_id = ? WHERE id = ?', (folder_id, file_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@files_bp.route('/folders/<int:folder_id>/move', methods=['POST'])
@login_required
def move_folder(folder_id):
    """
    Move a folder (and everything nested inside it) into a different
    parent folder, or to root if target_id is omitted.

    Guards against:
      - moving a folder into itself
      - moving a folder into one of its own descendants (which would
        create a cycle / orphan the branch)
    """
    username = session['username']
    target_id = request.form.get('target_id', type=int)  # None = move to root

    conn = get_user_db(username)
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM folders WHERE id = ?', (folder_id,))
    if cursor.fetchone() is None:
        conn.close()
        return jsonify({'success': False, 'message': 'Folder not found'}), 404

    if target_id == folder_id:
        conn.close()
        return jsonify({'success': False, 'message': 'A folder cannot be moved into itself'}), 400

    if target_id is not None:
        cursor.execute('SELECT id FROM folders WHERE id = ?', (target_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'success': False, 'message': 'Target folder not found'}), 404

        # Prevent moving a folder into one of its own descendants.
        descendant_ids = subfolder_ids_recursive(cursor, folder_id)
        if target_id in descendant_ids:
            conn.close()
            return jsonify({'success': False, 'message': 'Cannot move a folder into its own subfolder'}), 400

    cursor.execute('UPDATE folders SET parent_id = ? WHERE id = ?', (target_id, folder_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@files_bp.route('/folders/list')
@login_required
def list_folders():
    """
    Return a flat list of all folders (id, name, parent_id) for the
    current user, used to populate the "move to..." folder picker in the UI.
    """
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, parent_id FROM folders ORDER BY name COLLATE NOCASE')
    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        'folders': [{'id': r[0], 'name': r[1], 'parent_id': r[2]} for r in rows]
    })
