"""Member favourites and dream rankings in the existing account database."""
from urllib.parse import unquote, urlsplit

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, session, url_for
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table, delete, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from accounts import StorageUnavailable, metadata, users
from collection import CARS

favourites = Table(
    'garage_favourites', metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('car_slug', String(100), primary_key=True),
    Column('rank', Integer, nullable=False),
    CheckConstraint('rank > 0', name='garage_positive_rank'),
)


class GarageStore:
    def __init__(self, accounts):
        self.accounts = accounts
        self.engine = accounts.engine

    def initialize(self):
        # Add one table; existing accounts and their password hashes are untouched.
        try:
            favourites.create(self.engine, checkfirst=True)
        except SQLAlchemyError:
            raise StorageUnavailable('Garage storage could not be initialized.') from None

    def list_slugs(self, username):
        try:
            with self.engine.connect() as connection:
                return list(connection.scalars(
                    select(favourites.c.car_slug)
                    .join(users, favourites.c.user_id == users.c.id)
                    .where(users.c.username_key == username.casefold())
                    .order_by(favourites.c.rank, favourites.c.car_slug)
                ))
        except SQLAlchemyError:
            raise StorageUnavailable('Garage storage is temporarily unavailable.') from None

    def _user_id(self, connection, username):
        user_id = connection.scalar(select(users.c.id).where(users.c.username_key == username.casefold()))
        if user_id is None:
            raise PermissionError('Account no longer exists.')
        return user_id

    def _ordered(self, connection, user_id):
        return list(connection.scalars(select(favourites.c.car_slug)
                    .where(favourites.c.user_id == user_id)
                    .order_by(favourites.c.rank, favourites.c.car_slug)))

    def _rerank(self, connection, user_id, slugs):
        for rank, slug in enumerate(slugs, 1):
            connection.execute(update(favourites).where(
                favourites.c.user_id == user_id, favourites.c.car_slug == slug
            ).values(rank=rank))

    def add(self, username, slug):
        if slug not in CARS:
            raise ValueError('Unknown car.')
        # Reuse the account transaction lock. This serializes rank changes and
        # duplicate saves across workers, including with Neon's pooled endpoint.
        with self.accounts._write() as connection:
            user_id = self._user_id(connection, username)
            slugs = self._ordered(connection, user_id)
            if slug not in slugs:
                connection.execute(insert(favourites).values(
                    user_id=user_id, car_slug=slug, rank=len(slugs) + 1))

    def remove(self, username, slug):
        with self.accounts._write() as connection:
            user_id = self._user_id(connection, username)
            connection.execute(delete(favourites).where(
                favourites.c.user_id == user_id, favourites.c.car_slug == slug))
            self._rerank(connection, user_id, self._ordered(connection, user_id))

    def rank(self, username, slug, position):
        with self.accounts._write() as connection:
            user_id = self._user_id(connection, username)
            slugs = self._ordered(connection, user_id)
            if slug not in slugs:
                raise LookupError('Car is not saved in your garage.')
            if type(position) is not int or not 1 <= position <= len(slugs):
                raise ValueError('Choose an available dream rank.')
            slugs.remove(slug)
            slugs.insert(position - 1, slug)
            self._rerank(connection, user_id, slugs)


def register_garage(app, login_required):
    store = GarageStore(app.extensions['accounts'])
    store.initialize()
    app.extensions['garage'] = store
    garage = Blueprint('garage', __name__)

    def current_store():
        return current_app.extensions['garage']

    def saved_slugs():
        if 'garage_slugs' not in g:
            try:
                g.garage_slugs = current_store().list_slugs(session['username'])
            except StorageUnavailable:
                g.garage_read_failed = True
                raise
        return g.garage_slugs

    @app.context_processor
    def garage_context():
        endpoint = request.endpoint or ''
        if (request.method == 'GET' and not getattr(g, 'garage_read_failed', False)
                and session.get('username')
                and (endpoint == 'dashboard' or endpoint.startswith(('collection.', 'garage.')))):
            slugs = saved_slugs()
            return {'saved_car_slugs': set(slugs), 'garage_count': len(slugs)}
        return {'saved_car_slugs': set(), 'garage_count': 0}

    def require_car(car_slug):
        if car_slug not in CARS:
            abort(404)

    def destination():
        candidate = request.form.get('next', '')
        # Only a local absolute path is accepted. Decode before checking because
        # browsers and intermediaries can normalize encoded slashes/backslashes.
        decoded = unquote(candidate)
        if (decoded.startswith('/') and not decoded.startswith('//')
                and '\\' not in decoded and not any(ord(c) < 32 for c in decoded)):
            parts = urlsplit(decoded)
            if not parts.scheme and not parts.netloc:
                return candidate
        return url_for('garage.index')

    def mutate(action, car_slug, *args):
        require_car(car_slug)
        try:
            action(session['username'], car_slug, *args)
        except PermissionError:
            abort(403, description='Please log in with an existing account.')
        except LookupError:
            abort(404, description='This car is not saved in your garage.')
        except ValueError as error:
            abort(400, description=str(error))
        return redirect(destination(), code=303)

    @garage.get('/garage')
    @login_required
    def index():
        cars = [CARS[slug] for slug in saved_slugs() if slug in CARS]
        garage_saved = [{'car': car, 'rank': rank} for rank, car in enumerate(cars, 1)]
        return render_template('garage/index.html', title='My Garage', garage_saved=garage_saved)

    @garage.post('/garage/add/<car_slug>')
    @login_required
    def add(car_slug):
        return mutate(current_store().add, car_slug)

    @garage.post('/garage/remove/<car_slug>')
    @login_required
    def remove(car_slug):
        return mutate(current_store().remove, car_slug)

    @garage.post('/garage/rank/<car_slug>')
    @login_required
    def rank(car_slug):
        try:
            position = int(request.form.get('position', ''))
        except ValueError:
            abort(400, description='Choose an available dream rank.')
        return mutate(current_store().rank, car_slug, position)

    @garage.get('/garage/compare')
    @login_required
    def compare():
        slugs = request.args.getlist('car')
        owned = set(saved_slugs())
        if (not 2 <= len(slugs) <= 4 or len(set(slugs)) != len(slugs)
                or any(slug not in owned or slug not in CARS for slug in slugs)):
            abort(400, description='Choose between 2 and 4 different cars from your garage.')
        return render_template('garage/compare.html', title='Compare saved cars', compare_cars=[CARS[slug] for slug in slugs])

    app.register_blueprint(garage)
