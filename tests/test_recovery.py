"""Recovery integration/security tests. Uses disposable databases and a fake mailer only.

Run: python -m unittest discover -s tests -p 'test_recovery.py' -v
"""
import hashlib
import json
import os
import re
import smtplib
import ssl
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from accounts import AccountStore, users
from garage import GarageStore
from recovery_store import security

_boot = tempfile.TemporaryDirectory(prefix='nav12-recovery-boot-')
_previous_env = {key: os.environ.get(key) for key in ('DATA_DIR', 'APP_ENV', 'DATABASE_URL')}
os.environ['DATA_DIR'] = _boot.name
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_boot.name) / 'bootstrap.sqlite3')
os.environ['APP_ENV'] = 'development'
from app import app, account, rate_buckets  # Startup must never touch a real database.
from collection import CARS
from mailer import MailUnavailable, mail_ready, public_base, send_mail
for _key, _value in _previous_env.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value


class RecoveryTests(unittest.TestCase):
    PASSWORD = 'Original-password-2026'
    NEW_PASSWORD = 'Replacement-password-2026'
    USERNAME = 'RecoveryDriver'
    EMAIL = 'driver@example.com'

    def setUp(self):
        self.saved_config = dict(app.config)
        self.directory = tempfile.TemporaryDirectory(prefix='nav12-recovery-test-')
        self.original_accounts = app.extensions['accounts']
        self.original_garage = app.extensions['garage']
        self.accounts = AccountStore('sqlite:///' + str(Path(self.directory.name) / 'test.sqlite3'))
        self.accounts.initialize()
        app.extensions['accounts'] = self.accounts
        app.extensions['garage'] = GarageStore(self.accounts)
        app.extensions['garage'].initialize()
        self.outbox = []
        self.store = app.extensions['recovery']
        self.saved_clock = self.store.clock
        app.config.update(TESTING=True, MAIL_SYNC=True, PRODUCTION=False,
                          PUBLIC_BASE_URL='https://nav12.example',
                          MAIL_PROVIDER='', MAIL_FROM='', RESEND_API_KEY='', SMTP_HOST='',
                          MAIL_SENDER=lambda recipient, subject, body: self.outbox.append(
                              {'recipient': recipient, 'subject': subject, 'body': body}))
        rate_buckets.clear()
        app.extensions['recovery_limiter'].buckets.clear()
        self.client = app.test_client()
        account(self.USERNAME, self.PASSWORD)

    def tearDown(self):
        self.store.clock = self.saved_clock
        app.config.clear()
        app.config.update(self.saved_config)
        rate_buckets.clear()
        app.extensions['recovery_limiter'].buckets.clear()
        app.extensions['accounts'] = self.original_accounts
        app.extensions['garage'] = self.original_garage
        self.accounts.close()
        self.directory.cleanup()

    def csrf(self, client=None, path='/login', **kwargs):
        response = (client or self.client).get(path, **kwargs)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match, f'No CSRF token at {path}: {response.status_code}')
        return match[1].decode()

    def post(self, path, data=None, client=None, **kwargs):
        client = client or self.client
        payload = dict(data or {})
        payload['csrf_token'] = self.csrf(client, **({'base_url': kwargs['base_url']} if 'base_url' in kwargs else {}))
        return client.post(path, data=payload, **kwargs)

    def login(self, client=None, username=None, password=None):
        response = self.post('/login', {'username': username or self.USERNAME,
                                       'password': password or self.PASSWORD}, client=client)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/dashboard')
        return client or self.client

    def enroll(self, email=None):
        token = self.store.set_pending_email(self.USERNAME, self.PASSWORD, email or self.EMAIL)
        self.assertTrue(self.store.verify_email(token))
        return self.store.snapshot(self.USERNAME)

    def email_token(self, subject):
        message = next(item for item in reversed(self.outbox) if item['subject'] == subject)
        url = re.search(r'https?://\S+', message['body'])[0]
        self.assertEqual(urlsplit(url).query, '')
        return parse_qs(urlsplit(url).fragment)['token'][0], message, url

    def accept(self, token, purpose='reset', client=None):
        response = self.post('/recovery/link/' + purpose, {'token': token}, client=client)
        self.assertEqual(response.status_code, 303)
        self.assertNotIn(token, response.location)
        return response

    def test_full_http_enrollment_reset_and_login_lifecycle(self):
        self.login()
        response = self.post('/account/security', {'current_password': self.PASSWORD, 'email': self.EMAIL})
        self.assertEqual(response.status_code, 303)
        verify_token, _, _ = self.email_token('Verify your NaV12 recovery email')
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], '')
        visitor = app.test_client()
        self.accept(verify_token, 'verify', visitor)
        response = visitor.get('/verify-email')
        self.assertIn(b'Confirm your recovery email.', response.data)
        self.assertTrue(self.store.token_valid(verify_token, 'verify'))
        response = self.post('/verify-email', client=visitor)
        self.assertEqual(response.location, '/login')
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], self.EMAIL)
        self.assertFalse(self.store.token_valid(verify_token, 'verify'))
        self.assertEqual(self.client.get('/dashboard').status_code, 303)
        response = self.post('/forgot-password', {'username': self.USERNAME, 'email': self.EMAIL}, client=visitor)
        self.assertEqual(response.status_code, 303)
        reset_token, _, _ = self.email_token('Reset your NaV12 password')
        self.accept(reset_token, client=visitor)
        response = visitor.get('/reset-password')
        self.assertIn(b'A fresh start.', response.data)
        self.assertNotIn(reset_token.encode(), response.data)
        response = self.post('/reset-password', {'password': self.NEW_PASSWORD,
                                                'confirm_password': self.NEW_PASSWORD}, client=visitor)
        self.assertEqual(response.location, '/login')
        self.assertIsNone(self.store.authenticate(self.USERNAME, self.PASSWORD))
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, self.NEW_PASSWORD))
        self.assertFalse(self.store.token_valid(reset_token, 'reset'))
        with visitor.session_transaction() as session:
            self.assertNotIn('username', session)
        self.login(visitor, password=self.NEW_PASSWORD)
        self.assertTrue(any('password has changed' in item['body'] for item in self.outbox))

    def test_unknown_unverified_and_verified_requests_have_same_response(self):
        self.enroll()
        account('UnverifiedDriver', self.PASSWORD)
        self.store.set_pending_email('UnverifiedDriver', self.PASSWORD, 'pending@example.com')
        cases = [(self.USERNAME, self.EMAIL), ('UnknownDriver', self.EMAIL),
                 ('UnverifiedDriver', 'pending@example.com'), (self.USERNAME, 'wrong@example.com')]
        pages = []
        for username, email in cases:
            with self.subTest(username=username, email=email):
                client = app.test_client()
                response = self.post('/forgot-password', {'username': username, 'email': email},
                                     client=client, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                pages.append(response.data)
        self.assertTrue(all(page == pages[0] for page in pages))
        self.assertEqual(sum(item['subject'] == 'Reset your NaV12 password' for item in self.outbox), 1)

    def test_email_enrollment_requires_authentication_and_current_password(self):
        self.assertEqual(self.client.get('/account/security').status_code, 302)
        self.assertEqual(self.post('/account/security', {'current_password': self.PASSWORD,
                                                       'email': self.EMAIL}).status_code, 302)
        self.login()
        response = self.post('/account/security', {'current_password': 'incorrect', 'email': self.EMAIL})
        self.assertIn(b'current password is incorrect', response.data)
        self.assertEqual(self.outbox, [])
        self.assertEqual(self.store.snapshot(self.USERNAME)['pending_email'], '')

    def test_all_recovery_posts_require_csrf(self):
        for route in ('/forgot-password', '/reset-password', '/verify-email', '/recovery/link/reset',
                      '/recovery/link/verify', '/account/security', '/account/change-password'):
            for supplied in ('', 'incorrect', 'é' * 64):
                with self.subTest(route=route, csrf=supplied):
                    response = self.client.post(route, data={'csrf_token': supplied})
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(self.outbox, [])

    def test_tokens_are_purpose_bound_tamper_proof_and_single_use(self):
        verification = self.store.set_pending_email(self.USERNAME, self.PASSWORD, self.EMAIL)
        self.assertFalse(self.store.token_valid(verification, 'reset'))
        self.assertFalse(self.store.reset_password(verification, self.NEW_PASSWORD))
        self.assertTrue(self.store.verify_email(verification))
        self.assertFalse(self.store.verify_email(verification))
        reset = self.store.issue_reset(self.USERNAME, self.EMAIL)
        self.assertFalse(self.store.verify_email(reset))
        self.assertFalse(self.store.reset_password(reset[:-1] + ('A' if reset[-1] != 'A' else 'B'), self.NEW_PASSWORD))
        self.assertTrue(self.store.reset_password(reset, self.NEW_PASSWORD))
        self.assertFalse(self.store.reset_password(reset, 'Another-password-2026'))

    def test_exact_token_expiry_is_enforced(self):
        clock = [1000000.0]
        self.store.clock = lambda: clock[0]
        verification = self.store.set_pending_email(self.USERNAME, self.PASSWORD, self.EMAIL)
        clock[0] += self.store.verify_ttl
        self.assertFalse(self.store.verify_email(verification))
        verification = self.store.set_pending_email(self.USERNAME, self.PASSWORD, self.EMAIL)
        self.assertTrue(self.store.verify_email(verification))
        token = self.store.issue_reset(self.USERNAME, self.EMAIL)
        clock[0] += self.store.reset_ttl - 0.5
        self.assertTrue(self.store.token_valid(token, 'reset'))
        clock[0] += 0.5
        self.assertFalse(self.store.reset_password(token, self.NEW_PASSWORD))
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, self.PASSWORD))

    def test_reset_accepted_before_expiry_cannot_be_used_after_expiry(self):
        self.enroll()
        clock = [1000000.0]
        self.store.clock = lambda: clock[0]
        token = self.store.issue_reset(self.USERNAME, self.EMAIL)
        self.accept(token)
        clock[0] += self.store.reset_ttl
        response = self.post('/reset-password', {'password': self.NEW_PASSWORD,
                                                'confirm_password': self.NEW_PASSWORD})
        self.assertIn(b'This link is no longer valid.', response.data)
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, self.PASSWORD))

    def test_change_password_checks_current_confirmation_and_invalidates_all_sessions(self):
        self.enroll()
        self.login()
        other = self.login(app.test_client())
        reset = self.store.issue_reset(self.USERNAME, self.EMAIL)
        pending = self.store.set_pending_email(self.USERNAME, self.PASSWORD, 'new@example.com')
        for data, expected in [
            ({'current_password': 'bad', 'password': self.NEW_PASSWORD, 'confirm_password': self.NEW_PASSWORD}, b'current password is incorrect'),
            ({'current_password': self.PASSWORD, 'password': self.NEW_PASSWORD, 'confirm_password': 'different'}, b'passwords do not match'),
            ({'current_password': self.PASSWORD, 'password': self.PASSWORD, 'confirm_password': self.PASSWORD}, b'Choose a different password.'),
        ]:
            response = self.post('/account/change-password', data)
            self.assertIn(expected, response.data)
        response = self.post('/account/change-password', {'current_password': self.PASSWORD,
                             'password': self.NEW_PASSWORD, 'confirm_password': self.NEW_PASSWORD})
        self.assertEqual(response.location, '/login')
        self.assertEqual(other.get('/collection').status_code, 303)
        self.assertEqual(self.client.get('/dashboard').status_code, 302)
        self.assertFalse(self.store.token_valid(reset, 'reset'))
        self.assertFalse(self.store.token_valid(pending, 'verify'))
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, self.NEW_PASSWORD))

    def test_password_reset_invalidates_other_logged_in_sessions(self):
        self.enroll()
        first = self.login(app.test_client())
        second = self.login(app.test_client())
        token = self.store.issue_reset(self.USERNAME, self.EMAIL)
        self.accept(token)
        response = self.post('/reset-password', {'password': self.NEW_PASSWORD,
                                                'confirm_password': self.NEW_PASSWORD})
        self.assertEqual(response.location, '/login')
        self.assertEqual(first.get('/garage').status_code, 303)
        self.assertEqual(second.get('/dashboard').status_code, 303)

    def test_legacy_sessions_without_version_are_rejected(self):
        with self.client.session_transaction() as session:
            session['username'] = self.USERNAME
        self.assertEqual(self.client.get('/dashboard').status_code, 303)
        self.login()
        self.assertEqual(self.client.get('/dashboard').status_code, 200)

    def test_duplicate_email_ownership_cannot_be_transferred(self):
        account('OtherDriver', self.PASSWORD)
        first = self.store.set_pending_email(self.USERNAME, self.PASSWORD, self.EMAIL)
        second = self.store.set_pending_email('OtherDriver', self.PASSWORD, self.EMAIL.upper())
        self.assertTrue(self.store.verify_email(first))
        self.assertFalse(self.store.verify_email(second))
        self.assertEqual(self.store.snapshot('OtherDriver')['email'], '')
        with self.assertRaisesRegex(ValueError, 'cannot be used'):
            self.store.set_pending_email('OtherDriver', self.PASSWORD, self.EMAIL)
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], self.EMAIL)

    def test_pending_email_does_not_replace_verified_recovery_until_confirmed(self):
        self.enroll()
        reset = self.store.issue_reset(self.USERNAME, self.EMAIL)
        pending = self.store.set_pending_email(self.USERNAME, self.PASSWORD, 'replacement@example.com')
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], self.EMAIL)
        self.assertIsNone(self.store.issue_reset(self.USERNAME, 'replacement@example.com'))
        self.assertTrue(self.store.token_valid(reset, 'reset'))
        self.assertTrue(self.store.verify_email(pending))
        self.assertFalse(self.store.token_valid(reset, 'reset'))
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], 'replacement@example.com')

    def test_delivery_failure_revokes_link_without_disclosing_account(self):
        self.enroll()
        attempts = []
        def failing_mail(recipient, subject, body):
            attempts.append(body)
            raise MailUnavailable('simulated failure')
        app.config['MAIL_SENDER'] = failing_mail
        response = self.post('/forgot-password', {'username': self.USERNAME, 'email': self.EMAIL}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'If these details match', response.data)
        token = re.search(r'#token=([A-Za-z0-9_-]+)', attempts[0])[1]
        self.assertFalse(self.store.token_valid(token, 'reset'))
        self.assertNotIn(token.encode(), response.data)

    def test_failed_verification_delivery_does_not_enable_recovery(self):
        self.login()
        attempts = []
        def failing_mail(recipient, subject, body):
            attempts.append(body)
            raise MailUnavailable('simulated failure')
        app.config['MAIL_SENDER'] = failing_mail
        response = self.post('/account/security', {'current_password': self.PASSWORD, 'email': self.EMAIL})
        self.assertIn(b'could not send your verification email', response.data)
        token = re.search(r'#token=([A-Za-z0-9_-]+)', attempts[0])[1]
        self.assertFalse(self.store.token_valid(token, 'verify'))
        self.assertIsNone(self.store.issue_reset(self.USERNAME, self.EMAIL))

    def test_unconfigured_mail_is_reported_without_link_or_password_mutation(self):
        self.enroll()
        app.config.update(MAIL_SENDER=None, MAIL_PROVIDER='', PUBLIC_BASE_URL='')
        response = self.post('/forgot-password', {'username': self.USERNAME, 'email': self.EMAIL})
        self.assertEqual(response.status_code, 503)
        self.assertIn(b'Email recovery is not available yet', response.data)
        self.assertEqual(self.outbox, [])
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, self.PASSWORD))
        self.login()
        response = self.post('/account/change-password', {'current_password': self.PASSWORD,
                             'password': self.NEW_PASSWORD, 'confirm_password': self.NEW_PASSWORD})
        self.assertEqual(response.location, '/login')

    def test_trusted_origin_and_fragment_keep_tokens_out_of_http_urls(self):
        self.enroll()
        response = self.post('/forgot-password', {'username': self.USERNAME, 'email': self.EMAIL},
                             base_url='https://attacker.example')
        self.assertEqual(response.status_code, 303)
        token, message, url = self.email_token('Reset your NaV12 password')
        self.assertTrue(url.startswith('https://nav12.example/reset-password#token='))
        self.assertNotIn('attacker.example', message['body'])
        for path in ('/reset-password', '/verify-email'):
            response = self.client.get(path)
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
            self.assertNotIn(token.encode(), response.data)
        for bad in ('http://nav12.example', 'https://nav12.example@attacker.example/path',
                    'https://nav12.example/?redirect=x', 'https://nav12.example/#secret'):
            with self.subTest(origin=bad):
                with self.assertRaises(MailUnavailable):
                    public_base({'PUBLIC_BASE_URL': bad, 'PRODUCTION': True})
        self.assertFalse(mail_ready({'PUBLIC_BASE_URL': 'https://nav12.example', 'MAIL_PROVIDER': 'smtp',
                                     'MAIL_FROM': 'noreply@example.com', 'SMTP_HOST': 'smtp.example.com',
                                     'SMTP_SECURITY': 'none'}))

    def test_rate_limits_block_repeated_requests_without_locking_login(self):
        for _ in range(5):
            response = self.post('/forgot-password', {'username': 'UnknownDriver', 'email': self.EMAIL})
            self.assertEqual(response.status_code, 303)
        response = self.post('/forgot-password', {'username': 'UnknownDriver', 'email': self.EMAIL.upper()})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers['Retry-After'], '900')
        self.login()
        self.assertEqual(self.client.get('/dashboard').status_code, 200)

    def test_only_token_hashes_are_persisted_and_accounts_and_garage_are_preserved(self):
        account('OtherDriver', self.PASSWORD)
        other_hash = account('OtherDriver')
        car = next(iter(CARS))
        app.extensions['garage'].add(self.USERNAME, car)
        before = app.extensions['garage'].list_slugs(self.USERNAME)
        email = '=formula@example.com'
        verification = self.store.set_pending_email(self.USERNAME, self.PASSWORD, email)
        self.assertTrue(self.store.verify_email(verification))
        token = self.store.issue_reset(self.USERNAME, email)
        with self.accounts.engine.connect() as connection:
            rows = connection.execute(select(security)).mappings().all()
            values = [value for row in rows for value in row.values()]
            self.assertNotIn(token, values)
            self.assertNotIn(verification, values)
            self.assertIn(hashlib.sha256(token.encode()).hexdigest(), values)
            self.assertIn(email, values)
        self.assertTrue(self.store.reset_password(token, self.NEW_PASSWORD))
        self.assertEqual(account('OtherDriver'), other_hash)
        self.assertEqual(app.extensions['garage'].list_slugs(self.USERNAME), before)

    def test_admin_password_reset_revokes_sessions_and_email_tokens(self):
        self.enroll()
        self.login()
        reset = self.store.issue_reset(self.USERNAME, self.EMAIL)
        pending = self.store.set_pending_email(self.USERNAME, self.PASSWORD, 'next@example.com')
        self.assertTrue(self.accounts.reset_password(self.USERNAME, self.NEW_PASSWORD))
        self.assertEqual(self.client.get('/dashboard').status_code, 303)
        self.assertFalse(self.store.token_valid(reset, 'reset'))
        self.assertFalse(self.store.token_valid(pending, 'verify'))

    def test_security_schema_and_tokens_survive_new_database_connection(self):
        self.enroll()
        token = self.store.issue_reset(self.USERNAME, self.EMAIL)
        from recovery_store import RecoveryStore
        other = AccountStore('sqlite:///' + str(Path(self.directory.name) / 'test.sqlite3'))
        try:
            other.initialize()
            reopened = RecoveryStore(other)
            self.assertTrue(reopened.token_valid(token, 'reset'))
            self.assertEqual(reopened.snapshot(self.USERNAME)['email'], self.EMAIL)
            self.assertTrue(reopened.reset_password(token, self.NEW_PASSWORD))
            self.assertFalse(self.store.token_valid(token, 'reset'))
        finally:
            other.close()

    def test_postgresql_recovery_schema_has_unique_email_and_token_constraints(self):
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable
        ddl = str(CreateTable(security).compile(dialect=postgresql.dialect()))
        for expected in ('REFERENCES users (id) ON DELETE CASCADE', 'UNIQUE (email_key)',
                         'UNIQUE (reset_digest)', 'UNIQUE (verify_digest)', 'PRIMARY KEY (user_id)'):
            self.assertIn(expected, ddl)

    def test_concurrent_token_consumption_has_exactly_one_winner(self):
        self.enroll()
        token = self.store.issue_reset(self.USERNAME, self.EMAIL)
        passwords = ['Concurrent-password-one', 'Concurrent-password-two']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda password: self.store.reset_password(token, password), passwords))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, passwords[results.index(True)]))
        self.assertFalse(self.store.token_valid(token, 'reset'))

    def test_failed_old_send_cannot_revoke_newer_reset(self):
        self.enroll()
        old = self.store.issue_reset(self.USERNAME, self.EMAIL)
        current = self.store.issue_reset(self.USERNAME, self.EMAIL)
        self.assertFalse(self.store.revoke_token(old, 'reset'))
        self.assertTrue(self.store.token_valid(current, 'reset'))

    def test_stale_session_does_not_redirect_a_fresh_password_reset_link(self):
        self.enroll()
        self.login()
        self.assertTrue(self.store.change_password(self.USERNAME, self.PASSWORD, self.NEW_PASSWORD))
        token = self.store.issue_reset(self.USERNAME, self.EMAIL)
        # Browser GET excludes #token, but still carries its old signed-in cookie.
        response = self.client.get('/reset-password#token=' + token)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response.headers)
        with self.client.session_transaction() as session:
            self.assertNotIn('username', session)
        self.accept(token)
        replacement = 'Recovered-after-stale-session'
        response = self.post('/reset-password', {'password': replacement, 'confirm_password': replacement})
        self.assertEqual(response.location, '/login')
        self.assertIsNotNone(self.store.authenticate(self.USERNAME, replacement))

    def test_stale_session_does_not_redirect_a_fresh_verification_link(self):
        self.login()
        self.assertTrue(self.store.change_password(self.USERNAME, self.PASSWORD, self.NEW_PASSWORD))
        token = self.store.set_pending_email(self.USERNAME, self.NEW_PASSWORD, self.EMAIL)
        response = self.client.get('/verify-email#token=' + token)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response.headers)
        self.accept(token, 'verify')
        response = self.client.get('/verify-email')
        self.assertIn(self.USERNAME.encode(), response.data)
        self.assertIn(self.EMAIL.encode(), response.data)
        response = self.post('/verify-email')
        self.assertEqual(response.location, '/login')
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], self.EMAIL)

    def test_email_normalization_rejects_unicode_without_changing_delivery_local_part(self):
        for invalid in ('Straße@example.com', 'İnfo@example.com', 'Kevin@example.com',
                        'user@bücher.example', 'user@ｅxample.com'):
            with self.subTest(address=invalid):
                with self.assertRaisesRegex(ValueError, 'valid email'):
                    self.store.normalize_email(invalid)
        exact = 'Mixed.Case@example.com'
        self.assertEqual(self.store.normalize_email(' Mixed.Case@EXAMPLE.COM '), exact)
        self.enroll('Mixed.Case@EXAMPLE.COM')
        self.assertEqual(self.store.snapshot(self.USERNAME)['email'], exact)
        account('OtherDriver', self.PASSWORD)
        with self.assertRaisesRegex(ValueError, 'cannot be used'):
            self.store.set_pending_email('OtherDriver', self.PASSWORD, 'MIXED.CASE@example.com')
        response = self.post('/forgot-password', {'username': self.USERNAME.lower(),
                                                'email': 'mixed.case@EXAMPLE.COM'})
        self.assertEqual(response.status_code, 303)
        token, message, _ = self.email_token('Reset your NaV12 password')
        self.assertEqual(message['recipient'], exact)
        self.assertTrue(self.store.token_valid(token, 'reset'))

    def test_verification_message_and_confirmation_identify_account_and_email(self):
        self.login()
        email = 'Personal.Address@example.com'
        response = self.post('/account/security', {'current_password': self.PASSWORD,
                                                  'email': 'Personal.Address@EXAMPLE.COM'})
        self.assertEqual(response.status_code, 303)
        token, message, _ = self.email_token('Verify your NaV12 recovery email')
        self.assertEqual(message['recipient'], email)
        self.assertIn(self.USERNAME, message['body'])
        self.assertIn(email, message['body'])
        visitor = app.test_client()
        self.accept(token, 'verify', visitor)
        response = visitor.get('/verify-email')
        self.assertIn(self.USERNAME.encode(), response.data)
        self.assertIn(email.encode(), response.data)
        self.assertIn(b'Only confirm if this is the account you intended.', response.data)
        self.assertTrue(self.store.token_valid(token, 'verify'))


class MailerAdapterTests(unittest.TestCase):
    """Exercise the real adapters with network/SMTP boundaries mocked."""
    def config(self, provider, **changes):
        result = {'PUBLIC_BASE_URL': 'https://nav12.example', 'PRODUCTION': True,
                  'MAIL_PROVIDER': provider, 'MAIL_FROM': 'NaV12 <noreply@example.com>',
                  'RESEND_API_KEY': 'test-api-key', 'SMTP_HOST': 'smtp.example.com',
                  'SMTP_PORT': '587', 'SMTP_SECURITY': 'starttls',
                  'SMTP_USERNAME': 'test-user', 'SMTP_PASSWORD': 'test-password'}
        result.update(changes)
        return result

    def test_resend_sends_expected_https_json_payload(self):
        config = self.config('resend')
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id": "fake-message-id"}'
        with patch('mailer.urlopen', return_value=response) as request_mock:
            send_mail(config, 'Mixed.Case@example.com', 'Security test', 'Message text')
        request = request_mock.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.resend.com/emails')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-api-key')
        self.assertEqual(request_mock.call_args.kwargs['timeout'], 10)
        self.assertEqual(json.loads(request.data), {'from': config['MAIL_FROM'],
                         'to': ['Mixed.Case@example.com'], 'subject': 'Security test',
                         'text': 'Message text'})

    def test_resend_rejects_failure_or_missing_acceptance_without_exposing_provider_details(self):
        with patch('mailer.urlopen', side_effect=OSError('private provider failure details')):
            with self.assertRaisesRegex(MailUnavailable, '^Email delivery failed\\.$'):
                send_mail(self.config('resend'), 'driver@example.com', 'Test', 'Body')
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"error": "not accepted"}'
        with patch('mailer.urlopen', return_value=response):
            with self.assertRaisesRegex(MailUnavailable, '^Email delivery failed\\.$'):
                send_mail(self.config('resend'), 'driver@example.com', 'Test', 'Body')

    def test_starttls_is_established_before_smtp_authentication(self):
        with patch('mailer.smtplib.SMTP') as smtp, patch('mailer.smtplib.SMTP_SSL') as smtp_ssl:
            server = smtp.return_value.__enter__.return_value
            server.send_message.return_value = {}
            send_mail(self.config('smtp'), 'Mixed.Case@example.com', 'Security test', 'Message text')
        smtp.assert_called_once_with('smtp.example.com', 587, timeout=10)
        smtp_ssl.assert_not_called()
        self.assertEqual([call[0] for call in server.method_calls],
                         ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'])
        context = server.starttls.call_args.kwargs['context']
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        server.login.assert_called_once_with('test-user', 'test-password')
        message = server.send_message.call_args.args[0]
        self.assertEqual(str(message['To']), 'Mixed.Case@example.com')
        self.assertEqual(str(message['Subject']), 'Security test')
        self.assertEqual(message.get_content().strip(), 'Message text')

    def test_smtp_ssl_uses_verified_tls_without_starttls(self):
        with patch('mailer.smtplib.SMTP_SSL') as smtp_ssl, patch('mailer.smtplib.SMTP') as smtp:
            server = smtp_ssl.return_value.__enter__.return_value
            server.send_message.return_value = {}
            send_mail(self.config('smtp', SMTP_SECURITY='ssl', SMTP_PORT='465'),
                      'driver@example.com', 'Test', 'Body')
        smtp.assert_not_called()
        self.assertEqual(smtp_ssl.call_args.args, ('smtp.example.com', 465))
        context = smtp_ssl.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        server.starttls.assert_not_called()
        server.login.assert_called_once_with('test-user', 'test-password')
        server.send_message.assert_called_once()

    def test_smtp_tls_failure_stops_before_login_and_refusal_is_an_error(self):
        with patch('mailer.smtplib.SMTP') as smtp:
            server = smtp.return_value.__enter__.return_value
            server.starttls.side_effect = smtplib.SMTPNotSupportedError('TLS unsupported')
            with self.assertRaisesRegex(MailUnavailable, '^Email delivery failed\\.$'):
                send_mail(self.config('smtp'), 'driver@example.com', 'Test', 'Body')
            server.login.assert_not_called()
            server.send_message.assert_not_called()
        with patch('mailer.smtplib.SMTP_SSL') as smtp_ssl:
            server = smtp_ssl.return_value.__enter__.return_value
            server.send_message.return_value = {'driver@example.com': (550, b'Rejected')}
            with self.assertRaisesRegex(MailUnavailable, '^Email delivery failed\\.$'):
                send_mail(self.config('smtp', SMTP_SECURITY='ssl', SMTP_PORT='465'),
                          'driver@example.com', 'Test', 'Body')

    def test_invalid_configuration_and_header_injection_never_use_network(self):
        with patch('mailer.urlopen') as urlopen, patch('mailer.smtplib.SMTP') as smtp:
            for config in (self.config('resend', RESEND_API_KEY=''),
                           self.config('smtp', SMTP_SECURITY='none'),
                           self.config('smtp', MAIL_FROM='sender@example.com\nBcc: injected@example.com')):
                self.assertFalse(mail_ready(config))
                with self.assertRaises(MailUnavailable):
                    send_mail(config, 'driver@example.com', 'Test', 'Body')
            with self.assertRaises(MailUnavailable):
                send_mail(self.config('resend'), 'driver@example.com\r\nBcc: other@example.com', 'Test', 'Body')
            urlopen.assert_not_called()
            smtp.assert_not_called()


if __name__ == '__main__':
    unittest.main()
