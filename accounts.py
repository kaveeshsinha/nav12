"""Account storage: PostgreSQL on Neon, SQLite for local development only."""
import re
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        Text, create_engine, func, insert, select, text, update)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash

metadata = MetaData()
users = Table(
    'users', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', String(30), nullable=False),
    Column('username_key', String(30), nullable=False, unique=True),
    Column('password_hash', Text, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False,
           server_default=func.now()),
)


class StorageUnavailable(Exception):
    """Public error messages never include connection strings or SQL parameters."""


class ImportConflict(ValueError):
    pass


def valid_username(username):
    return isinstance(username, str) and re.fullmatch(r'[A-Za-z0-9_]{3,30}', username)


class AccountStore:
    def __init__(self, database_url, *, production=False, max_users=1000):
        self.max_users = max_users
        if not isinstance(max_users, int) or max_users < 1:
            raise ValueError('MAX_USERS must be a positive integer.')
        try:
            url = make_url(database_url.strip())
            if url.drivername in ('postgres', 'postgresql', 'postgresql+psycopg'):
                url = url.set(drivername='postgresql+psycopg')
                if production:
                    if url.query.get('sslmode', 'require') not in ('require', 'verify-ca', 'verify-full'):
                        raise ValueError('Production database connections must require TLS.')
                    url = url.update_query_dict({'sslmode': url.query.get('sslmode', 'require')})
                self.engine = create_engine(
                    url, pool_pre_ping=True, pool_size=2, max_overflow=1,
                    pool_timeout=10, pool_recycle=300, hide_parameters=True,
                    connect_args={'connect_timeout': 10, 'prepare_threshold': None},
                )
            elif url.drivername == 'sqlite' and not production:
                options = {'connect_args': {'timeout': 10, 'check_same_thread': False},
                           'hide_parameters': True}
                if url.database in (None, '', ':memory:'):
                    options['poolclass'] = StaticPool
                else:
                    Path(url.database).parent.mkdir(parents=True, exist_ok=True)
                self.engine = create_engine(url, **options)
            else:
                raise ValueError('Use a PostgreSQL DATABASE_URL in production.')
        except ValueError:
            raise ValueError('Invalid database configuration; use the Neon PostgreSQL URL with TLS in production.') from None
        except SQLAlchemyError:
            raise ValueError('Invalid DATABASE_URL configuration.') from None

    def initialize(self):
        try:
            metadata.create_all(self.engine)
        except SQLAlchemyError:
            raise StorageUnavailable('Account database could not be initialized.') from None

    @contextmanager
    def _write(self):
        try:
            with self.engine.begin() as connection:
                # Keep duplicate checks and the registration cap atomic across processes.
                # A transaction-scoped lock is compatible with Neon's pooled endpoint.
                if self.engine.dialect.name == 'postgresql':
                    connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 120026})
                else:
                    connection.exec_driver_sql('BEGIN IMMEDIATE')
                yield connection
        except SQLAlchemyError:
            raise StorageUnavailable('Account database is temporarily unavailable.') from None

    def read_hash(self, username):
        try:
            with self.engine.connect() as connection:
                return connection.scalar(select(users.c.password_hash).where(
                    users.c.username_key == username.casefold()))
        except SQLAlchemyError:
            raise StorageUnavailable('Account database is temporarily unavailable.') from None

    def create_account(self, username, password):
        if not valid_username(username) or not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise ValueError('Invalid account details.')
        password_hash = generate_password_hash(password)
        with self._write() as connection:
            if connection.scalar(select(users.c.id).where(users.c.username_key == username.casefold())) is not None:
                return False
            if connection.scalar(select(func.count()).select_from(users)) >= self.max_users:
                raise StorageUnavailable('Registration capacity reached.')
            connection.execute(insert(users).values(username=username,
                               username_key=username.casefold(), password_hash=password_hash))
        return True

    def reset_password(self, username, new_password):
        if not valid_username(username) or not isinstance(new_password, str) or not 8 <= len(new_password) <= 128:
            raise ValueError('Provide a username and an 8–128 character password.')
        password_hash = generate_password_hash(new_password)
        with self._write() as connection:
            result = connection.execute(update(users).where(users.c.username_key == username.casefold())
                                        .values(password_hash=password_hash))
            return result.rowcount == 1

    def import_hashes(self, rows, *, apply=False):
        """Import validated hashes atomically; never overwrite an existing account."""
        with self._write() as connection:
            existing = dict(connection.execute(select(users.c.username_key, users.c.password_hash)).all())
            additions = []
            skipped = 0
            for username, password_hash in rows:
                key = username.casefold()
                if key in existing:
                    if existing[key] != password_hash:
                        raise ImportConflict('An existing account has a different password hash. Nothing was imported.')
                    skipped += 1
                else:
                    additions.append({'username': username, 'username_key': key, 'password_hash': password_hash})
                    existing[key] = password_hash
            if len(existing) > self.max_users:
                raise ImportConflict('Import would exceed MAX_USERS. Nothing was imported.')
            if apply and additions:
                connection.execute(insert(users), additions)
            return {'added': len(additions), 'skipped': skipped, 'applied': apply}

    def close(self):
        self.engine.dispose()
