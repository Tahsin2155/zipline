# Self-Hosting Guide

This is the full guide to running your own copy of Zipline: local setup,
configuration, deploying it somewhere it stays up, scheduling the file
retention cleanup, backups, and troubleshooting.

If you just want the two-minute version, see the Quick Start in
[`README.md`](README.md). This document goes deeper.

## Table of contents

- [Requirements](#requirements)
- [1. Get the code](#1-get-the-code)
- [2. Install dependencies](#2-install-dependencies)
- [3. Create your first user](#3-create-your-first-user)
- [4. Run it locally](#4-run-it-locally)
- [5. Configuration](#5-configuration)
- [6. Deploying for real](#6-deploying-for-real)
  - [6a. Any Linux server / VPS (systemd + Gunicorn + Nginx)](#6a-any-linux-server--vps-systemd--gunicorn--nginx)
  - [6b. PythonAnywhere](#6b-pythonanywhere)
- [7. Scheduling the cleanup task](#7-scheduling-the-cleanup-task)
- [8. Managing users](#8-managing-users)
- [9. Backups](#9-backups)
- [10. Troubleshooting](#10-troubleshooting)

## Requirements

- Python 3.10 or newer
- `pip`
- A place to run a long-lived process (your own machine, a VPS, or a
  platform like PythonAnywhere) if you want Zipline reachable outside
  your own computer

Zipline uses SQLite (via Python's built-in `sqlite3`) and the local
filesystem for storage — there is no separate database server to install
or configure.

## 1. Get the code

```bash
git clone https://github.com/Tahsin2155/zipline.git
cd zipline
```

If you don't have `git`, you can also download the repository as a ZIP
from GitHub and extract it.

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

This installs Flask and Werkzeug (pinned to compatible major versions —
see `requirements.txt`). Using a virtual environment
(`python -m venv .venv && source .venv/bin/activate` on Linux/macOS, or
`.venv\Scripts\activate` on Windows) is recommended but not required.

## 3. Create your first user

Zipline has no public sign-up page — you create accounts yourself from
the command line:

```bash
python manage_users.py yourname
```

You'll be prompted for a password (entered twice, to confirm). See
[Managing users](#8-managing-users) below for the rest of this script's
options (setting a password non-interactively, overwriting, removing).

## 4. Run it locally

```bash
FLASK_ENV=development python wsgi.py
```

Then visit `http://127.0.0.1:5000` and log in with the user you just
created.

**Why `FLASK_ENV=development` matters:** Zipline marks its session cookie
`Secure` by default, meaning browsers will only send it back over HTTPS.
That's the right default for a real deployment, but it means a plain
`http://` connection — like bare localhost — would silently fail to keep
you logged in. Setting `FLASK_ENV=development` relaxes that flag for
local testing. **Don't set this environment variable in any deployment
that's reachable over the network** — see
[Configuration](#5-configuration) and [Deploying for real](#6-deploying-for-real).

## 5. Configuration

All tunable settings live in `app/config.py` (each is commented in place
in that file). The ones you're most likely to want to change:

| Setting | Default | What it controls |
|---|---|---|
| `FLASK_SECRET_KEY` (env var, read into `SECRET_KEY`) | `'dev-only-change-this-in-production'` | Signs session cookies. **Must** be overridden in any real deployment — see below. |
| `PERMANENT_SESSION_LIFETIME` | 30 minutes | Idle timeout — resets on each request, so it's "30 minutes of no activity," not a hard cutoff from login. |
| `MAX_FILE_SIZE` / `MAX_CONTENT_LENGTH` | 100MB | Per-file and per-request upload size cap. |
| `USER_STORAGE_QUOTA` | 100MB | Total storage allowed per user. Tune this to whatever disk you actually have. |
| `FILE_RETENTION_DAYS` | 5 | How old a file must be before the cleanup task deletes it. |
| `FILES_PER_PAGE` | 25 | Pagination size on the dashboard. |
| `BLOCKED_EXTENSIONS` | executables/scripts (`.exe`, `.sh`, `.jar`, etc.) | A **blocklist**, not an allowlist — Zipline is meant to move any file type around for personal use, so this only blocks the extensions most likely to be dangerous to execute. Add to it if you want to be stricter. |
| `TEXT_PREVIEW_EXTENSIONS`, `IMAGE_PREVIEW_EXTENSIONS`, `PDF_PREVIEW_EXTENSIONS` | see file | Which extensions get inline previews vs. a plain download link. |
| `TEXT_PREVIEW_MAX_BYTES` | 50KB | How much of a text/code file is read for its preview before it's truncated. |

### Setting the secret key

Never leave `FLASK_SECRET_KEY` at its default outside of local testing —
anyone who knows the default could forge session cookies. Generate a real
one and set it as an environment variable:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then set `FLASK_SECRET_KEY` to that value however your host lets you set
environment variables (a `systemd` unit's `Environment=`, a `.env` file
your process manager loads, PythonAnywhere's Web tab, etc.) — see the
platform-specific sections below.

## 6. Deploying for real

Zipline is a standard Flask app exposed through `wsgi.py`, so it runs
behind any WSGI server. Two common paths:

### 6a. Any Linux server / VPS (systemd + Gunicorn + Nginx)

This runs Zipline as a background service that survives reboots, behind
Nginx for TLS.

1. Get the code and dependencies onto the server (steps 1–2 above),
   ideally into a virtual environment.
2. Install Gunicorn: `pip install gunicorn`.
3. Create your first user (step 3 above).
4. Test it directly first:
   ```bash
   gunicorn --bind 127.0.0.1:8000 wsgi:application
   ```
5. Create a `systemd` service so it starts on boot and restarts on
   failure — e.g. `/etc/systemd/system/zipline.service`:
   ```ini
   [Unit]
   Description=Zipline
   After=network.target

   [Service]
   User=youruser
   WorkingDirectory=/home/youruser/zipline
   Environment="FLASK_SECRET_KEY=your-generated-secret-here"
   ExecStart=/home/youruser/zipline/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 wsgi:application
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   Then:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now zipline
   ```
6. Put Nginx (or your reverse proxy of choice) in front of it to
   terminate HTTPS and forward to `127.0.0.1:8000`. **Do not** set
   `FLASK_ENV=development` here — with real HTTPS in front of it, the
   default secure-cookie behavior is correct and you want it on.
7. Set up a certificate (e.g. via `certbot`) so the site is served over
   HTTPS — the app assumes it in production.

### 6b. PythonAnywhere

PythonAnywhere is a convenient option if you don't want to manage a
server yourself — it terminates HTTPS for you and has a built-in
scheduled-task system (used below for cleanup).

1. Upload or clone this project to somewhere like `/home/<you>/zipline`
   (PythonAnywhere gives you a Bash console you can `git clone` from).
2. In that Bash console: `pip install --user -r requirements.txt`.
3. Create at least one user: `python manage_users.py yourname`.
4. On the **Web** tab, create a new web app — choose **manual
   configuration** and a Python version 3.10 or newer.
5. Set the **source code** directory to `/home/<you>/zipline`.
6. Edit the auto-generated WSGI configuration file (linked from the Web
   tab) so it ends with:
   ```python
   import sys
   path = '/home/<you>/zipline'
   if path not in sys.path:
       sys.path.insert(0, path)

   from wsgi import application
   ```
7. Add an environment variable `FLASK_SECRET_KEY` set to
   a generated secret (see [above](#setting-the-secret-key)) — don't
   leave the default in production.
8. Reload the web app.
9. Set up the cleanup task — see the next section, this is the part
   PythonAnywhere handles differently from a normal server.

## 7. Scheduling the cleanup task

Zipline deletes files older than `FILE_RETENTION_DAYS` (default 5), but
it does this by running `cleanup_task.py` **once**, not through an
always-on background thread inside the web process. This is deliberate:
platforms like PythonAnywhere run web apps under a WSGI server without
reliable thread support, so a typical "loop forever and sleep" cleanup
thread wouldn't run reliably there — and running cleanup as a scheduled,
one-shot script works everywhere regardless of that limitation.

You need to schedule it yourself:

**On PythonAnywhere:**
1. Go to the **Tasks** tab.
2. Add a daily scheduled task (e.g. 03:00) running:
   ```
   python3.x /home/<you>/zipline/cleanup_task.py
   ```
   (replace `python3.x` with the same Python version you configured the
   web app with).

**On a Linux server (cron):**
```bash
crontab -e
```
Add a line like:
```
0 3 * * * cd /home/youruser/zipline && /home/youruser/zipline/.venv/bin/python cleanup_task.py >> /home/youruser/zipline/cleanup.log 2>&1
```

**Overriding the retention period for a single run**, without touching
`config.py`:
```bash
python cleanup_task.py --retention-days 10
```

The script prints how many files it deleted and exits — check your
scheduler's logs (PythonAnywhere's Tasks tab, or the log file in the cron
example above) if you want to confirm it ran.

## 8. Managing users

All user management goes through `manage_users.py`, which edits
`users.json` directly (passwords are stored hashed, never in plain text):

```bash
python manage_users.py alice                      # prompts for a password
python manage_users.py alice --password foo123     # set the password directly (e.g. for scripting)
python manage_users.py alice --force               # overwrite an existing user
python manage_users.py alice --remove              # delete a user
```

Removing a user deletes their entry from `users.json` only — it does
**not** delete their SQLite database under `databases/` or their files
under `uploads/`. Remove those manually if you want the storage back.

There's no web UI for user management by design — Zipline has no
public sign-up flow, since every account is something you, the host,
create by hand.

## 9. Backups

Everything that matters lives in two places on disk, both of which are
safe to back up with any ordinary file-based backup tool while the app is
stopped (or, for SQLite, generally safe to copy live since SQLite handles
concurrent readers, but stopping the app first is simplest if you want a
guaranteed-consistent snapshot):

- `databases/` — one SQLite file per user (folder structure, file
  metadata, notes).
- `uploads/` — one subfolder per user, containing the actual uploaded
  files.

Also back up `users.json` (login credentials) and, if you customized it,
`app/config.py`.

## 10. Troubleshooting

**I log in locally and it immediately kicks me back to the login page.**
You're almost certainly running over plain HTTP without
`FLASK_ENV=development` set. The session cookie is marked `Secure` by
default, so the browser won't send it back over `http://`. Either set
`FLASK_ENV=development` for local testing, or put real HTTPS in front of
the app.

**Uploads fail with "Request too large."**
The file (or the whole request) exceeded `MAX_FILE_SIZE` /
`MAX_CONTENT_LENGTH` in `app/config.py`. Raise the limit there if your
host has the disk and bandwidth for it.

**A user can't upload anything even though the file is small.**
Check `USER_STORAGE_QUOTA` — it's a *total* per-user cap, not a per-file
one. If they're near it, either raise the quota or have them delete old
files.

**Old files aren't being deleted.**
`cleanup_task.py` only runs when something triggers it — a scheduled
task (PythonAnywhere) or a cron job (your own server). There's no
built-in timer inside the running web app. Confirm the scheduler is
actually configured and check its logs (see
[Scheduling the cleanup task](#7-scheduling-the-cleanup-task)).

**A file type I need is blocked.**
`BLOCKED_EXTENSIONS` in `app/config.py` is a deliberately small blocklist
(executables and scripts) — remove an extension from that set if you
trust what you're storing and want to allow it.

**I edited `users.json` by hand and now logins are broken.**
Make sure it's still valid JSON and that each entry is either the legacy
plain-string form or the full object form (`password`, `failed_logins`,
`locked_until`) described at the top of `app/users.py`. When in doubt,
prefer editing users through `manage_users.py` instead of by hand.

**I'm locked out after failed login attempts.**
This is the built-in lockout: 5 failed attempts locks that username out
for 15 minutes. Wait it out, or clear `locked_until` for that user in
`users.json` (or via a quick edit) if you need back in sooner.
