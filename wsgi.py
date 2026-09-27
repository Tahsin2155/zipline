"""
WSGI entrypoint.

Any WSGI server (Gunicorn, uWSGI, PythonAnywhere's own web app hosting,
etc.) should point at the `application` object defined below, not run
this file's `__main__` block directly. That block only exists for quick
local testing.

Example for PythonAnywhere: on the "Web" tab, edit the auto-generated
WSGI configuration file it links to so it ends with:

    import sys
    path = '/home/<youruser>/zipline'
    if path not in sys.path:
        sys.path.insert(0, path)

    from wsgi import application

Example for Gunicorn on a normal Linux server:

    gunicorn --bind 127.0.0.1:8000 wsgi:application

See guide.md for full deployment instructions (both of the above, plus
environment variables and HTTPS).
"""
from app import create_app

# `application` is the name WSGI servers look for by convention (it's
# also literally what PythonAnywhere's own WSGI file expects to import).
# create_app() builds and configures the Flask app -- see app/__init__.py
# for what that includes (session cookie hardening, blueprint
# registration, error handlers, etc.).
application = create_app()

if __name__ == '__main__':
    # This block only runs when you execute `python wsgi.py` directly --
    # it's for local development, and is never used by a real WSGI
    # server (which imports `application` above instead).
    #
    # debug=False on purpose: Flask's debugger executes arbitrary code
    # from the browser when an error page is shown, which is fine on a
    # solo local machine but not something to enable by habit. Turn it
    # on temporarily and manually if you're debugging a crash and
    # understand the risk.
    #
    # host='0.0.0.0' binds to all network interfaces, not just
    # localhost, so other devices on your network can reach it too --
    # convenient for testing from a phone, but be aware of it if you're
    # on a network you don't fully trust while testing.
    application.run(host='0.0.0.0', debug=False)
