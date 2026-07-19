import os

from flask import Flask, redirect, render_template, url_for

from app.config import Config
from app.csrf import init_csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Session cookie hardening. PythonAnywhere serves over HTTPS, so
    # SESSION_COOKIE_SECURE=True is safe there. If you ever run this over
    # plain HTTP (e.g. bare localhost testing without a tunnel), set
    # FLASK_ENV=development to relax this -- see below.
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'development'

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DATABASE_FOLDER'], exist_ok=True)

    if not os.path.exists(app.config['USERS_FILE']):
        import json
        with open(app.config['USERS_FILE'], 'w') as f:
            json.dump({}, f, indent=4)

    init_csrf(app)

    from app.blueprints.auth import auth_bp
    from app.blueprints.files import files_bp
    from app.blueprints.notes import notes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(notes_bp)

    @app.route('/')
    def home():
        from flask import session
        if 'username' in session:
            return redirect(url_for('files.dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template('500.html'), 500

    @app.errorhandler(413)
    def request_entity_too_large(error):
        from flask import flash, redirect, url_for
        max_mb = app.config['MAX_FILE_SIZE'] / (1024 * 1024)
        flash(f'Request too large. Maximum upload size is {max_mb:.0f}MB.', 'danger')
        return redirect(url_for('files.dashboard'))

    return app
