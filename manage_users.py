"""
CLI to add/update users in users.json.

Usage:
    python manage_users.py <username>                  # prompt for password
    python manage_users.py <username> --password foo   # set directly
    python manage_users.py <username> --force           # overwrite existing user
"""
import argparse
import getpass
import json
from pathlib import Path
from typing import Optional

from werkzeug.security import generate_password_hash

USERS_FILE = Path(__file__).resolve().parent / 'users.json'


def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    with USERS_FILE.open('r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise SystemExit(f'Invalid JSON in {USERS_FILE}: {exc}') from exc
    if not isinstance(data, dict):
        raise SystemExit(f'Expected an object in {USERS_FILE}, found {type(data).__name__}.')
    return data


def save_users(users: dict) -> None:
    with USERS_FILE.open('w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)
        f.write('\n')


def prompt_password() -> str:
    password = getpass.getpass('Password: ')
    confirm = getpass.getpass('Confirm password: ')
    if password != confirm:
        raise SystemExit('Passwords do not match.')
    if not password:
        raise SystemExit('Password cannot be empty.')
    return password


def add_user(username: str, password: Optional[str], force: bool) -> None:
    username = username.strip()
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

    users[username] = {
        'password': generate_password_hash(password),
        'failed_logins': 0,
        'locked_until': None,
    }
    save_users(users)

    action = 'Updated' if user_exists else 'Added'
    print(f'{action} user "{username}" in {USERS_FILE.name}.')


def remove_user(username: str) -> None:
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
