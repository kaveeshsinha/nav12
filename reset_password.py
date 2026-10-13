"""Reset an existing account using this app's configured, locked storage.

Run from the project folder with the same DATA_DIR as the deployed app:
    python reset_password.py
"""
import getpass
import sys
from zipfile import BadZipFile

from werkzeug.security import generate_password_hash

from app import StorageUnavailable, open_users, save_workbook, workbook_lock, workbook_path


def reset_password(username, new_password):
    """Return False for an unknown account; never create a new account."""
    if not username or not 8 <= len(new_password) <= 128:
        raise ValueError('Provide a username and an 8–128 character password.')
    path = workbook_path()
    with workbook_lock(path):
        wb = open_users(path)
        try:
            for row in wb['Users'].iter_rows(min_row=2, max_col=2):
                saved_name = row[0].value
                if saved_name and str(saved_name).casefold() == username.casefold():
                    row[1].value = generate_password_hash(new_password)
                    save_workbook(wb, path)
                    return True
            return False
        finally:
            wb.close()


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
    except (StorageUnavailable, OSError, BadZipFile):
        print('Account storage is unavailable. No reset was completed.', file=sys.stderr)
        return 1
    print('Password reset successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
