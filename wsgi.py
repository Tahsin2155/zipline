"""
WSGI entrypoint for PythonAnywhere.

On the PythonAnywhere "Web" tab, point your WSGI configuration file to
import `application` from here, e.g. add near the bottom of the
auto-generated /var/www/<you>_pythonanywhere_com_wsgi.py:

    import sys
    path = '/home/<youruser>/dti'
    if path not in sys.path:
        sys.path.insert(0, path)

    from wsgi import application
"""
from app import create_app

application = create_app()

if __name__ == '__main__':
    # Local dev only. On PythonAnywhere this file is imported, not run directly.
    application.run(host='0.0.0.0', debug=True)
