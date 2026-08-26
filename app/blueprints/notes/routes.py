from datetime import datetime

from flask import jsonify, render_template, request, session

from app.blueprints.notes import notes_bp
from app.db import get_user_db
from app.decorators import login_required

MAX_NOTE_LENGTH = 200_000  # generous cap so a runaway paste can't blow up the db file
MAX_TITLE_LENGTH = 100


def _next_sort_order(cursor):
    cursor.execute('SELECT COALESCE(MAX(sort_order), -1) + 1 FROM notes')
    return cursor.fetchone()[0]


@notes_bp.route('/notes')
@login_required
def view():
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, updated_at FROM notes ORDER BY sort_order ASC, id ASC')
    notes = cursor.fetchall()

    requested_id = request.args.get('id', type=int)
    active = None
    if requested_id is not None:
        cursor.execute('SELECT id, title, content, updated_at FROM notes WHERE id = ?', (requested_id,))
        active = cursor.fetchone()

    if active is None and notes:
        first_id = notes[0][0]
        cursor.execute('SELECT id, title, content, updated_at FROM notes WHERE id = ?', (first_id,))
        active = cursor.fetchone()

    conn.close()

    return render_template(
        'notes/notes.html',
        username=username,
        notes=notes,
        active=active,
    )


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


@notes_bp.route('/notes/<int:note_id>')
@login_required
def get_note(note_id):
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, content, updated_at FROM notes WHERE id = ?', (note_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'message': 'Note not found.'}), 404

    return jsonify({
        'success': True,
        'note': {'id': row[0], 'title': row[1], 'content': row[2], 'updated_at': row[3]}
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

    cursor.execute('SELECT id, title, updated_at FROM notes ORDER BY sort_order ASC, id ASC LIMIT 1')
    next_row = cursor.fetchone()
    conn.close()

    next_note = None
    if next_row:
        next_note = {'id': next_row[0], 'title': next_row[1], 'updated_at': next_row[2]}

    return jsonify({'success': True, 'next_note': next_note})
