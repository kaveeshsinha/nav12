"""NaV12 Flask app with PostgreSQL account storage for Render + Neon."""
import os
import re
import secrets
import threading
import time
from collections import deque
from datetime import timedelta
from pathlib import Path
from functools import wraps
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from accounts import AccountStore, StorageUnavailable

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
production = os.environ.get('APP_ENV', 'development') == 'production'
secret = os.environ.get('SECRET_KEY')
if production and (not secret or len(secret) < 32):
    raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters.')
# Restrict local development database files to the service owner.
os.umask(0o077)
app.config.update(
    SECRET_KEY=secret or secrets.token_hex(32),
    SESSION_COOKIE_SECURE=production,
    MAX_USERS=int(os.environ.get('MAX_USERS', '1000')),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    MAX_CONTENT_LENGTH=16 * 1024,
)


rate_mutex = threading.Lock()
rate_buckets = {}


def rate_allowed(username):
    # Bounded, in-memory protection for ONE worker. Resets at process restart.
    # Global cap covers username rotation; per-name cap slows repeated attempts.
    now = time.monotonic()
    keys = [('all', 60), ('user:' + username.casefold(), 10)]
    with rate_mutex:
        for key in list(rate_buckets):
            bucket = rate_buckets[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if not bucket:
                del rate_buckets[key]
        if any(len(rate_buckets.get(key, ())) >= limit for key, limit in keys):
            return False
        for key, _ in keys:
            rate_buckets.setdefault(key, deque()).append(now)
        return True


def account(username, password=None):
    store = app.extensions['accounts']
    return store.read_hash(username) if password is None else store.create_account(username, password)


def csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


app.jinja_env.globals['csrf_token'] = csrf_token


@app.before_request
def protect_forms():
    if request.method == 'POST':
        supplied = request.form.get('csrf_token', '')
        expected = session.get('csrf_token', '')
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description='Form expired. Reload the page and try again.')
        if request.endpoint in {'login', 'signup'}:
            username = request.form.get('username', '').strip()
            if len(username) > 30:
                abort(400, description='Username is too long.')
            if not rate_allowed(username):
                abort(429, description='Too many attempts. Please wait one minute.')


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access your garage.', 'error')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


@app.route('/')
def index():
    return redirect(url_for('dashboard' if 'username' in session else 'login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', username):
            flash('Use 3–30 letters, numbers, or underscores for your username.', 'error')
        elif not 8 <= len(password) <= 128:
            flash('Your password must contain 8–128 characters.', 'error')
        elif not account(username, password):
            flash('Username already exists. Please log in or choose another.', 'error')
        else:
            flash('Account created. Log in to enter your garage.', 'success')
            return redirect(url_for('login'))
    return render_template('signup.html', title='Join the garage')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        saved_hash = account(username)
        if saved_hash is None:
            flash('User not found', 'error')
        elif not password or len(password) > 128 or not check_password_hash(saved_hash, password):
            flash('Incorrect credentials', 'error')
        else:
            session.clear()
            session.permanent = True
            session['username'] = username
            return redirect(url_for('dashboard'))
    return render_template('login.html', title='Welcome back')


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', title='Your garage')


# Catalogue registration does not alter account or storage configuration.
from collection import register_collection
register_collection(app, login_required)


@app.post('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.after_request
def prevent_cached_accounts(response):
    if request.endpoint != 'static':
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    # Only pages using local enhancements may execute scripts; never inline code.
    scripts = ("'self'" if request.endpoint in {'dashboard', 'login', 'signup'}
               or (request.endpoint or '').startswith(('collection.', 'garage.'))
               else "'none'")
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        f"img-src 'self'; script-src {scripts}; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if production:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.errorhandler(StorageUnavailable)
def storage_error(error):
    app.logger.error('Account storage unavailable: %s', type(error).__name__)
    return render_template('error.html', title='Temporarily unavailable',
                           message='Account storage is temporarily unavailable. Please try again later.'), 503


@app.errorhandler(400)
@app.errorhandler(413)
@app.errorhandler(429)
def request_error(error):
    response = app.make_response((render_template('error.html', title='Request could not be completed',
                                                 message=error.description), error.code))
    if error.code == 429:
        response.headers['Retry-After'] = '60'
    return response


# Production always requires an external PostgreSQL database.
# SQLite is only a convenience for local development without cloud credentials.
database_url = os.environ.get('DATABASE_URL', '').strip()
if not database_url:
    if production:
        raise RuntimeError('Set DATABASE_URL to your Neon PostgreSQL connection URL.')
    local_dir = Path(os.environ.get('DATA_DIR', str(BASE_DIR / 'data')))
    local_dir.mkdir(parents=True, exist_ok=True)
    database_url = 'sqlite:///' + str((local_dir / 'nav12.sqlite3').resolve())
store = AccountStore(database_url, production=production, max_users=app.config['MAX_USERS'])
try:
    store.initialize()
except StorageUnavailable:
    raise RuntimeError('Cannot initialize the account database. Check DATABASE_URL and database availability.') from None
app.extensions['accounts'] = store

from garage import register_garage
register_garage(app, login_required)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
