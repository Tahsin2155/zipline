# Data Transfer Interface (DTI)

A personal, self-hosted file transfer app: login, per-user storage, nested
folders, search, inline previews (images / PDFs / text-code), and a
free-text scratchpad. Built with Flask + SQLite, no external services.

## What changed from the original single-file version

- **Blueprints**: split into `auth`, `files`, `notes` instead of one `app.py`.
- **Real nested folders**: create/rename/delete, breadcrumbs, move files between folders.
- **Search**: instant filename search across all folders.
- **Previews**: images and PDFs render inline, text/code files show in a
  modal (truncated with a download link if the file is large).
- **Scratchpad**: a `/notes` page — one big autosaving textarea per user,
  not tied to any file, with a copy button.
- **Security hardening**: login lockout after repeated failures, a
  blocklist of dangerous file extensions, per-user storage quota, legacy
  plaintext passwords in `users.json` auto-migrate to hashes on first login.
- **PythonAnywhere-ready**: no in-process background thread for cleanup
  (PythonAnywhere doesn't support that in web apps — see below). Cleanup is
  now a standalone script meant for PythonAnywhere's Scheduled Tasks.

## Local setup

```bash
pip install -r requirements.txt
python manage_users.py yourname            # prompts for a password
FLASK_ENV=development python wsgi.py       # http://127.0.0.1:5000
```

`FLASK_ENV=development` relaxes the secure-cookie flag so login works over
plain HTTP locally. Don't set it in production.

## Deploying on PythonAnywhere

1. Upload/clone this project to somewhere like `/home/<you>/dti`.
2. In a Bash console: `pip install --user -r requirements.txt`.
3. Create at least one user: `python manage_users.py yourname`.
4. On the **Web** tab, create a new web app (manual config, any Python version 3.10+).
5. Set the **source code** directory to `/home/<you>/dti`.
6. Edit the auto-generated WSGI file (linked from the Web tab) so it ends with:
   ```python
   import sys
   path = '/home/<you>/dti'
   if path not in sys.path:
       sys.path.insert(0, path)

   from wsgi import application
   ```
7. Set `FLASK_SECRET_KEY` as an environment variable on the Web tab (or edit
   `app/config.py` directly) — don't leave the default in production.
8. Reload the web app.

### Cleanup (expired file retention)

PythonAnywhere web apps run under uWSGI **without thread support**, so an
always-running "loop forever and sleep" cleanup thread inside the Flask app
won't work reliably there — this is a platform limitation, not a bug in this
app. Instead, use PythonAnywhere's **Tasks** tab:

1. Go to the **Tasks** tab.
2. Add a scheduled task (daily, e.g. 03:00) running:
   ```
   python3.x /home/<you>/dti/cleanup_task.py
   ```
3. That script runs once, deletes files older than `FILE_RETENTION_DAYS`
   (default 5, override with `--retention-days N`), and exits.

## Managing users

```bash
python manage_users.py alice                     # prompts for password
python manage_users.py alice --password foo123    # set directly
python manage_users.py alice --force               # overwrite existing user
python manage_users.py alice --remove              # delete a user
```

## Project layout

```
app/
  __init__.py          # app factory
  config.py            # all settings in one place
  db.py                # per-user SQLite connection + schema
  users.py             # users.json loading, password verify, lockout
  csrf.py              # CSRF protection
  decorators.py         # login_required
  blueprints/
    auth/              # login/logout
    files/             # dashboard, folders, upload, download, preview, delete
    notes/             # scratchpad
  templates/
  static/css/main.css
cleanup_task.py         # run via PythonAnywhere Scheduled Task, not a thread
manage_users.py         # CLI user management
wsgi.py                 # entrypoint for PythonAnywhere / any WSGI server
users.json               # {username: {password, failed_logins, locked_until}}
databases/                # one SQLite file per user (auto-created)
uploads/                  # one subfolder per user (auto-created)
```

## Notes on limits

- `MAX_FILE_SIZE` / `USER_STORAGE_QUOTA` in `app/config.py` — tune the quota
  to whatever your PythonAnywhere plan's disk allowance actually is.
- `BLOCKED_EXTENSIONS` is a blocklist (not an allowlist) since the app is
  meant to move "any" file type around for personal use — add to it if you
  want to be stricter.
- This app has no built-in HTTPS; PythonAnywhere terminates TLS for you, so
  `SESSION_COOKIE_SECURE=True` (the default outside `FLASK_ENV=development`)
  is correct there.
