"""
CLI to add, update, and remove users in users.json.

This is the only way to create a Zipline account -- there's no public
sign-up page in the app itself, by design (see guide.md for the
reasoning). Run this from a shell on whatever machine hosts the app,
pointed at the same users.json the running app uses.

Usage:
    python manage_users.py <username>                  # prompt for password
    python manage_users.py <username> --password foo   # set directly (e.g. for scripting)
    python manage_users.py <username> --force           # overwrite an existing user
    python manage_users.py <username> --remove          # delete a user

Note: --remove only deletes the users.json entry. It does NOT delete
that user's SQLite database under databases/ or their files under
uploads/ -- remove those by hand if you want the disk space back.
"""
import argparse
import json
from pathlib import Path
from typing import Optional

from werkzeug.security import generate_password_hash

# users.json lives at the project root (one level up from this script),
# next to app/, uploads/, and databases/ -- this is the same file
# app/config.py points USERS_FILE at, so this script and the running
# app always agree on which file they're editing.
USERS_FILE = Path(__file__).resolve().parent / 'users.json'


def load_users() -> dict:
    """Read users.json into a dict, or {} if it doesn't exist yet."""
    if not USERS_FILE.exists():
        return {}
    with USERS_FILE.open('r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            # Fail loudly rather than silently treating a corrupt file
            # as "no users" -- that would be a much worse surprise.
            raise SystemExit(f'Invalid JSON in {USERS_FILE}: {exc}') from exc
    if not isinstance(data, dict):
        raise SystemExit(f'Expected an object in {USERS_FILE}, found {type(data).__name__}.')
    return data


def save_users(users: dict) -> None:
    """Write the full users dict back to users.json, pretty-printed."""
    with USERS_FILE.open('w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)
        f.write('\n')


def prompt_password() -> str:
    """Interactively ask for a password twice and confirm they match.

    Note: this uses plain input(), so the password is echoed to the
    terminal as you type it (not masked). Use --password if you need it
    hidden from screen/scrollback, e.g. when running over someone else's
    shoulder-visible terminal.
    """
    password = input('Password: ')
    confirm = input('Confirm password: ')
    if password != confirm:
        raise SystemExit('Passwords do not match.')
    if not password:
        raise SystemExit('Password cannot be empty.')
    return password


def add_user(username: str, password: Optional[str], force: bool) -> None:
    """Create a new user, or overwrite an existing one if --force was passed.

    The stored record always uses the current (hashed) format -- see
    app/users.py for the full shape and for how legacy plaintext entries
    from very old users.json files get migrated automatically on first
    login instead of here.
    """
    username = username.lower().strip()
    if not username:
        raise SystemExit('Username cannot be empty.')

    users = load_users()
    user_exists = username in users

    if user_exists and not force:
        raise SystemExit(f'User "{username}" already exists. Use --force to overwrite.')

    if password is None:
        password = prompt_password()
    elif not password:
        raise SystemExit('Password cannot be empty.')

    # generate_password_hash() salts and hashes the password -- the
    # plaintext value is never written to disk.
    users[username] = {
        'password': generate_password_hash(password),
        'failed_logins': 0,
        'locked_until': None,
    }
    save_users(users)

    action = 'Updated' if user_exists else 'Added'
    print(f'{action} user "{username}" in {USERS_FILE.name}.')


def remove_user(username: str) -> None:
    """Delete a user's users.json entry (their files/DB are left alone -- see module docstring)."""
    users = load_users()
    if username not in users:
        raise SystemExit(f'User "{username}" not found.')
    del users[username]
    save_users(users)
    print(f'Removed user "{username}" from {USERS_FILE.name}.')


def main() -> None:
    parser = argparse.ArgumentParser(description='Manage users in users.json for the Data Transfer Interface.')
    parser.add_argument('username', help='Username to add, update, or remove')
    parser.add_argument('--password', help='Password value. If omitted, you will be prompted securely.')
    parser.add_argument('--force', action='store_true', help='Overwrite existing user if it already exists.')
    parser.add_argument('--remove', action='store_true', help='Remove this user instead of adding/updating.')
    args = parser.parse_args()

    if args.remove:
        remove_user(args.username)
    else:
        add_user(args.username, args.password, args.force)


if __name__ == '__main__':
    main()
