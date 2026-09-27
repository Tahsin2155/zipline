# Zipline

A personal, self-hosted file transfer and mini-drive app: log in, get
per-user storage with nested folders, instant filename search, inline
previews for images/PDFs/text-code, and a free-text scratchpad for notes.
Built with Flask + SQLite — no external services, no third-party accounts,
no database server to run.

Zipline is meant to be **self-hosted**: clone it, run it on your own
machine or your own server, and it's yours. There's no hosted version and
no accounts system beyond the users you create yourself.

## Features

- **Per-user storage** — every user gets their own SQLite database and
  upload folder; users can't see each other's files.
- **Real nested folders** — create, rename, delete, breadcrumb navigation,
  and move files between folders.
- **Search** — instant filename search across all of a user's folders.
- **Inline previews** — images and PDFs render in the browser; text/code
  files open in a modal (large files are truncated with a download link).
- **Scratchpad** — a `/notes` page for free-text notes, autosaving, not
  tied to any uploaded file.
- **Security basics built in** — hashed passwords, login lockout after
  repeated failed attempts, CSRF protection on all mutating requests, a
  blocklist of dangerous file extensions, and a per-user storage quota.
- **Automatic retention cleanup** — files older than a configurable number
  of days are purged by a standalone script you schedule yourself (see
  [`guide.md`](guide.md)) — there's no always-on background thread, so it
  works even on hosts that don't support one.

## Quick start

```bash
git clone https://github.com/Tahsin2155/zipline.git
cd zipline
pip install -r requirements.txt
python manage_users.py yourname        # creates your first login, prompts for a password
FLASK_ENV=development python wsgi.py   # http://127.0.0.1:5000
```

`FLASK_ENV=development` relaxes the secure-cookie flag so login works over
plain HTTP on localhost. Don't set it once you're running for real, over
HTTPS — see [`guide.md`](guide.md) for why, and for everything else
involved in running this somewhere other than your own laptop
(environment variables, HTTPS, the cleanup task, backups, and
troubleshooting).

## Project layout

```
zipline/
├── app
│   ├── blueprints
│   │   ├── auth/           # login / logout
│   │   ├── files/          # dashboard, folders, upload, download, preview, delete
│   │   └── notes/          # scratchpad
│   │
│   ├── static
│   │   ├── css
│   │   │   └── main.css    # app styling
│   │   └── .../
│   │
│   ├── templates/          # Jinja templates
│   ├── __init__.py         # application factory: config, security headers, blueprints, error pages
│   ├── config.py           # every tunable setting in one place (documented inline)
│   ├── csrf.py             # CSRF token generation + request-level enforcement
│   ├── db.py               # per-user SQLite connection + schema management
│   ├── decorators.py       # @login_required
│   └── users.py            # users.json loading, password verification, login lockout
│
├── cleanup_task.py         # one-shot retention cleanup, run on a schedule (documented inline)
├── manage_users.py         # CLI for adding/updating/removing users (documented inline)
├── wsgi.py                 # WSGI entrypoint for any WSGI server, and local dev runner (documented inline)
├── requirements.txt        # dependencies
│
├── databases/              # one SQLite file per user — auto-created
├── uploads/                # one subfolder per user — auto-created
├── users.json              # {username: {password, failed_logins, locked_until}} — auto-created
│
├── guide.md                # the full self-hosting guide
└── README.md               # README
```


## Documentation

- **[`guide.md`](guide.md)** — the full self-hosting guide: local setup,
  environment variables, deploying behind your own web server or on a
  platform like PythonAnywhere, scheduling the cleanup task, backups, and
  troubleshooting. Start here if you're setting this up for yourself.
- `app/config.py`, `wsgi.py`, `manage_users.py`, and `cleanup_task.py` are
  all commented in place — read them directly if you want to know exactly
  what a setting or script does.

## Why self-hosted, and what that means for you

The code here is public so that anyone can run their own private copy —
it is **not** a multi-tenant service you sign up for. Each install:

- Stores everything on the disk of whatever machine runs it (SQLite files
  under `databases/`, uploaded files under `uploads/`).
- Has its own independent `users.json` — accounts are not shared between
  installs.
- Is only as secure as the box it runs on and the network path to it. See
  [`guide.md`](guide.md) for the HTTPS and secret-key guidance before you
  expose an instance to the internet.

## License

No license file is currently included in this repository. Under default
copyright law, that means no rights are granted to use, modify, or
redistribute this code — viewing and forking on GitHub doesn't imply
permission beyond that.
 
The intent is for this project to be usable for **personal use only**
(no commercial use), with the name **Zipline** kept as-is in any copy or
fork. That intent isn't yet formalized as an actual license — until a
LICENSE file is added, don't rely on this note as a substitute for one.