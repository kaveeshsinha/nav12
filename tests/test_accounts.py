"""Database persistence, duplicate races, import rollback, and safe configuration."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from accounts import AccountStore, ImportConflict, StorageUnavailable, users
from import_users import read_backup


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='nav12-db-test-')
        self.url = 'sqlite:///' + str(Path(self.directory.name) / 'accounts.sqlite3')
        self.store = AccountStore(self.url)
        self.store.initialize()

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def count(self):
        with self.store.engine.connect() as connection:
            return connection.scalar(select(func.count()).select_from(users))

    def backup(self, rows):
        path = Path(self.directory.name) / 'users.xlsx'
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Users'
        sheet.append(['Username', 'Password'])
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        workbook.close()
        return path

    def test_hash_and_account_survive_new_connection(self):
        self.store.create_account('PersistentDriver', 'Persistent-test-password')
        self.store.close()
        self.store = AccountStore(self.url)
        self.store.initialize()
        saved = self.store.read_hash('persistentdriver')
        self.assertNotEqual(saved, 'Persistent-test-password')
        self.assertTrue(check_password_hash(saved, 'Persistent-test-password'))

    def test_case_insensitive_duplicate_race(self):
        other = AccountStore(self.url)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda args: args[0].create_account(args[1], 'Duplicate-test-password'),
                    [(self.store, 'RaceDriver'), (other, 'racedriver')]))
            self.assertEqual(sorted(results), [False, True])
            self.assertEqual(self.count(), 1)
        finally:
            other.close()

    def test_registration_cap_is_atomic(self):
        self.store.max_users = 1
        self.store.create_account('FirstDriver', 'First-test-password')
        with self.assertRaises(StorageUnavailable):
            self.store.create_account('SecondDriver', 'Second-test-password')
        self.assertEqual(self.count(), 1)

    def test_reset_unknown_and_existing_user(self):
        self.assertFalse(self.store.reset_password('UnknownDriver', 'Reset-test-password'))
        self.assertEqual(self.count(), 0)
        self.store.create_account('ResetDriver', 'Original-test-password')
        self.assertTrue(self.store.reset_password('resetdriver', 'Updated-test-password'))
        self.assertTrue(check_password_hash(self.store.read_hash('ResetDriver'), 'Updated-test-password'))
        self.assertFalse(check_password_hash(self.store.read_hash('ResetDriver'), 'Original-test-password'))

    def test_import_preview_preserves_hash_and_is_idempotent(self):
        saved = generate_password_hash('Legacy-test-password')
        path = self.backup([('LegacyDriver', saved)])
        before = path.read_bytes()
        rows = read_backup(path)
        self.assertEqual(self.store.import_hashes(rows)['added'], 1)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.store.import_hashes(rows, apply=True)['added'], 1)
        self.assertEqual(self.store.read_hash('legacydriver'), saved)
        self.assertEqual(self.store.import_hashes(rows, apply=True)['skipped'], 1)
        self.assertEqual(self.count(), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_import_conflict_rolls_back_every_addition(self):
        self.store.create_account('ExistingDriver', 'Existing-test-password')
        previous = self.store.read_hash('ExistingDriver')
        rows = [('NewDriver', generate_password_hash('New-test-password')),
                ('existingdriver', generate_password_hash('Conflicting-test-password'))]
        with self.assertRaises(ImportConflict):
            self.store.import_hashes(rows, apply=True)
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.store.read_hash('ExistingDriver'), previous)

    def test_import_rejects_plaintext_and_duplicate_names(self):
        for invalid in ['Plaintext-test-password', 'scrypt:0:0:0$Salt$ff', 'pbkdf2:sha256:0$Salt$ff']:
            with self.assertRaises(ValueError):
                read_backup(self.backup([('PlainDriver', invalid)]))
        saved = generate_password_hash('Legacy-test-password')
        with self.assertRaises(ValueError):
            read_backup(self.backup([('LegacyDriver', saved), ('legacydriver', saved)]))
        self.assertEqual(self.count(), 0)

    def test_production_refuses_local_database_and_insecure_tls(self):
        for url in [self.url, 'postgresql://test:test@localhost/nav12?sslmode=disable']:
            with self.assertRaises(ValueError):
                AccountStore(url, production=True)

    def test_postgresql_url_preserves_pooler_and_security_parameters(self):
        store = AccountStore('postgres://test:test@ep-example-pooler.aws.neon.tech/neondb?sslmode=require&channel_binding=require', production=True)
        try:
            self.assertEqual(store.engine.url.drivername, 'postgresql+psycopg')
            self.assertIn('-pooler', store.engine.url.host)
            self.assertEqual(store.engine.url.query['channel_binding'], 'require')
            self.assertEqual(store.engine.url.query['sslmode'], 'require')
        finally:
            store.close()

    def test_database_errors_return_generic_503_without_credentials(self):
        from app import app
        app.config['TESTING'] = True
        client = app.test_client()
        with client.session_transaction() as session:
            session['csrf_token'] = 'SyntheticToken'
        with patch.object(app.extensions['accounts'], 'read_hash', side_effect=StorageUnavailable('temporary failure')):
            response = client.post('/login', data={'csrf_token': 'SyntheticToken', 'username': 'TestDriver', 'password': 'Synthetic-password'})
        self.assertEqual(response.status_code, 503)
        self.assertIn(b'temporarily unavailable', response.data)
        self.assertNotIn(b'postgresql://', response.data)


if __name__ == '__main__':
    unittest.main()
