import hmac
import secrets

from flask import abort, request, session


def generate_csrf_token():
    """Create/reuse a session-scoped CSRF token."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def init_csrf(app):
    @app.before_request
    def protect_from_csrf():
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return

        token_from_session = session.get('_csrf_token')
        token_from_request = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')

        if not token_from_session or not token_from_request:
            abort(400)
        if not hmac.compare_digest(token_from_session, token_from_request):
            abort(400)

    @app.context_processor
    def inject_csrf_token():
        return {'csrf_token': generate_csrf_token}
