from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for

from app.blueprints.notes import notes_bp
from app.db import get_user_db
from app.decorators import login_required

MAX_NOTE_LENGTH = 200_000  # generous cap so a runaway paste can't blow up the db file
MAX_TITLE_LENGTH = 100
PREVIEW_LENGTH = 140


def _next_sort_order(cursor):
    cursor.execute('SELECT COALESCE(MAX(sort_order), -1) + 1 FROM notes')
    return cursor.fetchone()[0]


def _make_preview(content):
    snippet = content.strip().replace('\n', ' ')
    if len(snippet) > PREVIEW_LENGTH:
        snippet = snippet[:PREVIEW_LENGTH].rstrip() + '...'
    return snippet


@notes_bp.route('/notes')
@login_required
def view():
    """Grid view of all notes, or the single-note editor when ?id=<id> is given."""
    username = session['username']
    requested_id = request.args.get('id', type=int)

    conn = get_user_db(username)
    cursor = conn.cursor()

    if requested_id is not None:
        cursor.execute(
            'SELECT id, title, content, created_at, updated_at FROM notes WHERE id = ?',
            (requested_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return redirect(url_for('notes.view'))

        note = {
            'id': row[0], 'title': row[1], 'content': row[2],
            'created_at': row[3], 'updated_at': row[4],
        }
        return render_template('notes/note_editor.html', username=username, note=note)

    cursor.execute(
        'SELECT id, title, content, created_at, updated_at FROM notes ORDER BY sort_order ASC, id ASC'
    )
    rows = cursor.fetchall()
    conn.close()

    notes = [
        {
            'id': r[0], 'title': r[1], 'preview': _make_preview(r[2]),
            'created_at': r[3], 'updated_at': r[4],
        }
        for r in rows
    ]

    return render_template('notes/notes.html', username=username, notes=notes)


@notes_bp.route('/notes/new', methods=['POST'])
@login_required
def new():
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    order = _next_sort_order(cursor)
    cursor.execute(
        'INSERT INTO notes (title, content, sort_order) VALUES (?, ?, ?)',
        ('Untitled', '', order)
    )
    note_id = cursor.lastrowid
    conn.commit()

    cursor.execute('SELECT id, title, updated_at FROM notes WHERE id = ?', (note_id,))
    row = cursor.fetchone()
    conn.close()

    return jsonify({
        'success': True,
        'note': {'id': row[0], 'title': row[1], 'updated_at': row[2]}
    })


@notes_bp.route('/notes/<int:note_id>/save', methods=['POST'])
@login_required
def save(note_id):
    username = session['username']
    content = request.form.get('content', '')

    if len(content) > MAX_NOTE_LENGTH:
        return jsonify({'success': False, 'message': 'Note is too long.'}), 400

    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notes SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (content, note_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Note not found.'}), 404

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'saved_at': datetime.now().strftime('%H:%M:%S')})


@notes_bp.route('/notes/<int:note_id>/rename', methods=['POST'])
@login_required
def rename(note_id):
    username = session['username']
    title = request.form.get('title', '').strip()

    if not title:
        title = 'Untitled'
    title = title[:MAX_TITLE_LENGTH]

    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notes SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (title, note_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Note not found.'}), 404

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'title': title})


@notes_bp.route('/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def delete(note_id):
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Note not found.'}), 404

    conn.commit()
    conn.close()

    return jsonify({'success': True})
