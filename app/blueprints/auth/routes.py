import time

from flask import flash, redirect, render_template, request, session, url_for

from app.blueprints.auth import auth_bp
from app.decorators import login_required
from app.users import get_user_record, is_locked_out, record_login_result, verify_password


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login page."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('auth.login'))

        record = get_user_record(username)

        if record is not None and is_locked_out(record):
            wait_minutes = max(1, int((record['locked_until'] - time.time()) // 60) + 1)
            flash(f'Too many failed attempts. Try again in about {wait_minutes} minute(s).', 'danger')
            return redirect(url_for('auth.login'))

        if record is not None and verify_password(username, password):
            record_login_result(username, success=True)
            session.clear()
            session['username'] = username
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('files.dashboard'))

        if record is not None:
            record_login_result(username, success=False)

        flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """User logout."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
