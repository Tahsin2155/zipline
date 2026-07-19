from datetime import datetime

from flask import jsonify, render_template, request, session

from app.blueprints.notes import notes_bp
from app.db import get_user_db
from app.decorators import login_required

MAX_NOTE_LENGTH = 200_000  # generous cap so a runaway paste can't blow up the db file


@notes_bp.route('/notes')
@login_required
def view():
    username = session['username']
    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute('SELECT content, updated_at FROM notes WHERE id = 1')
    row = cursor.fetchone()
    conn.close()

    content = row[0] if row else ''
    updated_at = row[1] if row else None

    return render_template('notes/notes.html', username=username, content=content, updated_at=updated_at)


@notes_bp.route('/notes/save', methods=['POST'])
@login_required
def save():
    username = session['username']
    content = request.form.get('content', '')

    if len(content) > MAX_NOTE_LENGTH:
        return jsonify({'success': False, 'message': 'Note is too long.'}), 400

    conn = get_user_db(username)
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO notes (id, content, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(id) DO UPDATE SET content = excluded.content, updated_at = CURRENT_TIMESTAMP''',
        (content,)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'saved_at': datetime.now().strftime('%H:%M:%S')})
