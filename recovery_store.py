"""Atomic recovery state in the existing PostgreSQL/SQLite account database."""
import hashlib
import re
import secrets
import time
from contextlib import contextmanager

from sqlalchemy import (Column, Float, ForeignKey, Integer, String, Table,
                        delete, insert, select, update)
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from accounts import StorageUnavailable, metadata, users

security = Table(
    'account_security', metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('email', String(254)),
    Column('email_key', String(254), unique=True),
    Column('pending_email', String(254)),
    Column('version', Integer, nullable=False, server_default='0'),
    Column('reset_digest', String(64), unique=True),
    Column('reset_expires', Float),
    Column('reset_email', String(254)),
    Column('reset_version', Integer),
    Column('verify_digest', String(64), unique=True),
    Column('verify_expires', Float),
    Column('verify_email', String(254)),
    Column('verify_version', Integer),
)


class RecoveryStore:
    EMAIL_UNAVAILABLE = 'This email address cannot be used. Try another address.'
    _TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z')
    _LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}\Z")
    _DOMAIN_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')

    def __init__(self, accounts, reset_ttl=1800, verify_ttl=86400, clock=None):
        self._accounts = accounts
        self.reset_ttl = int(reset_ttl)
        self.verify_ttl = int(verify_ttl)
        if self.reset_ttl <= 0 or self.verify_ttl <= 0:
            raise ValueError('Token expiry must be positive.')
        self.clock = clock or time.time

    @property
    def accounts(self):
        return self._accounts() if callable(self._accounts) else self._accounts

    def initialize(self):
        # The same transaction-scoped lock as account writes serializes startup
        # across processes; no existing table or password is altered.
        with self.accounts._write() as connection:
            security.create(connection, checkfirst=True)

    @classmethod
    def normalize_email(cls, email):
        if not isinstance(email, str) or not email.isascii():
            raise ValueError('Enter a valid email address.')
        email = email.strip()
        if len(email) > 254 or email.count('@') != 1:
            raise ValueError('Enter a valid email address.')
        local, domain = email.split('@')
        domain = domain.lower()
        if (not cls._LOCAL.fullmatch(local) or local.startswith('.') or local.endswith('.')
                or '..' in local or len(domain) > 253 or '.' not in domain
                or not all(cls._DOMAIN_LABEL.fullmatch(label) for label in domain.split('.'))):
            raise ValueError('Enter a valid email address.')
        return local + '@' + domain

    @contextmanager
    def _read(self):
        try:
            with self.accounts.engine.connect() as connection:
                yield connection
        except SQLAlchemyError:
            raise StorageUnavailable('Account security storage is temporarily unavailable.') from None

    @staticmethod
    def _user(connection, username):
        if not isinstance(username, str):
            return None
        return connection.execute(select(users).where(users.c.username_key == username.casefold())).mappings().first()

    @staticmethod
    def _record(connection, user_id):
        return connection.execute(select(security).where(security.c.user_id == user_id)).mappings().first()

    @staticmethod
    def _snapshot(user, record):
        return {'username': user['username'], 'email': (record['email'] or '') if record else '',
                'pending_email': (record['pending_email'] or '') if record else '',
                'version': record['version'] if record else 0}

    def snapshot(self, username):
        with self._read() as connection:
            user = self._user(connection, username)
            return self._snapshot(user, self._record(connection, user['id'])) if user else None

    @staticmethod
    def _password_matches(saved_hash, password):
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            return False
        try:
            return check_password_hash(saved_hash, password)
        except (ValueError, TypeError):
            raise StorageUnavailable('Account security data is invalid.') from None

    def authenticate(self, username, password):
        # Read hash and session version from one locked transaction, so a reset
        # cannot race between successful authentication and version selection.
        with self.accounts._write() as connection:
            user = self._user(connection, username)
            if not user or not self._password_matches(user['password_hash'], password):
                return None
            return self._snapshot(user, self._record(connection, user['id']))

    @staticmethod
    def _ensure(connection, user_id):
        record = RecoveryStore._record(connection, user_id)
        if record is None:
            connection.execute(insert(security).values(user_id=user_id, version=0))
            record = RecoveryStore._record(connection, user_id)
        return record

    @staticmethod
    def _clear(prefix):
        return {prefix + suffix: None for suffix in ('_digest', '_expires', '_email', '_version')}

    @classmethod
    def invalidate(cls, connection, user_id):
        """Called by all password-changing paths, including the admin CLI."""
        record = cls._ensure(connection, user_id)
        connection.execute(update(security).where(security.c.user_id == user_id).values(
            version=record['version'] + 1, pending_email=None,
            **cls._clear('reset'), **cls._clear('verify')))

    def _issue(self, connection, record, purpose, email, ttl):
        token = secrets.token_urlsafe(32)
        values = {purpose + '_digest': hashlib.sha256(token.encode('ascii')).hexdigest(),
                  purpose + '_expires': self.clock() + ttl,
                  purpose + '_email': email, purpose + '_version': record['version']}
        if purpose == 'verify':
            values['pending_email'] = email
        connection.execute(update(security).where(security.c.user_id == record['user_id']).values(**values))
        return token

    def set_pending_email(self, username, password, email):
        email = self.normalize_email(email)
        with self.accounts._write() as connection:
            user = self._user(connection, username)
            if not user or not self._password_matches(user['password_hash'], password):
                return None
            owner = connection.scalar(select(security.c.user_id).where(security.c.email_key == email.casefold()))
            if owner is not None and owner != user['id']:
                raise ValueError(self.EMAIL_UNAVAILABLE)
            record = self._ensure(connection, user['id'])
            return self._issue(connection, record, 'verify', email, self.verify_ttl)

    def issue_reset(self, username, email):
        try:
            email = self.normalize_email(email)
        except ValueError:
            return None
        with self.accounts._write() as connection:
            user = self._user(connection, username)
            record = self._record(connection, user['id']) if user else None
            if not record or record['email_key'] != email.casefold():
                return None
            return self._issue(connection, record, 'reset', record['email'], self.reset_ttl)

    def _match(self, connection, token, purpose, include_expired=False):
        if purpose not in {'reset', 'verify'}:
            raise ValueError('Unknown token purpose.')
        if not isinstance(token, str) or not self._TOKEN.fullmatch(token):
            return None
        digest = hashlib.sha256(token.encode('ascii')).hexdigest()
        row = connection.execute(select(security).where(security.c[purpose + '_digest'] == digest)).mappings().first()
        if not row or (not include_expired and self.clock() >= row[purpose + '_expires']):
            return None
        target = row['email' if purpose == 'reset' else 'pending_email']
        if row[purpose + '_email'] != target or row[purpose + '_version'] != row['version']:
            return None
        return row

    def token_valid(self, token, purpose):
        with self._read() as connection:
            return self._match(connection, token, purpose) is not None

    def token_profile(self, token, purpose):
        with self._read() as connection:
            record = self._match(connection, token, purpose)
            if not record:
                return None
            user = connection.execute(select(users).where(users.c.id == record['user_id'])).mappings().first()
            return self._snapshot(user, record) if user else None

    def revoke_token(self, token, purpose):
        with self.accounts._write() as connection:
            record = self._match(connection, token, purpose, include_expired=True)
            if not record:
                return False
            connection.execute(update(security).where(security.c.user_id == record['user_id']).values(**self._clear(purpose)))
            return True

    def verify_email(self, token):
        with self.accounts._write() as connection:
            record = self._match(connection, token, 'verify')
            if not record:
                return False
            owner = connection.scalar(select(security.c.user_id).where(
                security.c.email_key == record['pending_email'].casefold()))
            if owner is not None and owner != record['user_id']:
                connection.execute(update(security).where(security.c.user_id == record['user_id']).values(
                    pending_email=None, **self._clear('verify')))
                return False
            connection.execute(update(security).where(security.c.user_id == record['user_id']).values(
                email=record['pending_email'], email_key=record['pending_email'].casefold()))
            self.invalidate(connection, record['user_id'])
            return True

    @staticmethod
    def _valid_new_password(password):
        return isinstance(password, str) and 8 <= len(password) <= 128

    def reset_password(self, token, new_password):
        if not self._valid_new_password(new_password):
            return False
        with self.accounts._write() as connection:
            record = self._match(connection, token, 'reset')
            if not record:
                return False
            user = connection.execute(select(users).where(users.c.id == record['user_id'])).mappings().first()
            if not user:
                return False
            if self._password_matches(user['password_hash'], new_password):
                raise ValueError('Choose a different password.')
            connection.execute(update(users).where(users.c.id == user['id']).values(password_hash=generate_password_hash(new_password)))
            self.invalidate(connection, user['id'])
            return True

    def change_password(self, username, current_password, new_password):
        if not self._valid_new_password(new_password):
            return False
        with self.accounts._write() as connection:
            user = self._user(connection, username)
            if not user or not self._password_matches(user['password_hash'], current_password):
                return False
            if self._password_matches(user['password_hash'], new_password):
                raise ValueError('Choose a different password.')
            connection.execute(update(users).where(users.c.id == user['id']).values(password_hash=generate_password_hash(new_password)))
            self.invalidate(connection, user['id'])
            return True
