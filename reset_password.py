"""Reset an existing account using this app's configured database.

Run from the project folder with the same DATABASE_URL as the deployed app:
    python reset_password.py
"""
import getpass
import sys

from app import app
from accounts import StorageUnavailable


def reset_password(username, new_password):
    """Return False for an unknown account; never create a new account."""
    return app.extensions['accounts'].reset_password(username, new_password)


def main():
    try:
        username = input('Username: ').strip()
        if not username:
            print('Username is required.', file=sys.stderr)
            return 1
        new_password = getpass.getpass('New password: ')
        if not 8 <= len(new_password) <= 128:
            print('Password must contain 8–128 characters.', file=sys.stderr)
            return 1
        confirmation = getpass.getpass('Confirm new password: ')
        if new_password != confirmation:
            print('Passwords do not match. Nothing was changed.', file=sys.stderr)
            return 1
        if not reset_password(username, new_password):
            print('Username not found. No account was changed.', file=sys.stderr)
            return 1
    except (EOFError, KeyboardInterrupt):
        print('\nPassword reset cancelled.', file=sys.stderr)
        return 1
    except (StorageUnavailable, ValueError):
        print('Account storage is unavailable. No reset was completed.', file=sys.stderr)
        return 1
    print('Password reset successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
