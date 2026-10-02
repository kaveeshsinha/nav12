# NaV12 — Complete source code

See README.md for hosting instructions and Excel persistence constraints.

## app.py

```python
"""NaV12: single-instance Flask application with locked Excel storage.

Linux/macOS only (fcntl); deploy one worker on persistent storage.
"""
import os
import re
import secrets
import fcntl
import threading
import time
from collections import deque
from contextlib import contextmanager
from zipfile import BadZipFile
from datetime import timedelta
from pathlib import Path
from functools import wraps
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
production = os.environ.get('APP_ENV', 'development') == 'production'
secret = os.environ.get('SECRET_KEY')
if production and (not secret or len(secret) < 32):
    raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters.')
# Restrict newly created workbook/lock files to the service owner.
os.umask(0o077)
app.config.update(
    SECRET_KEY=secret or secrets.token_hex(32),
    USER_FILE=Path(os.environ.get('DATA_DIR', str(BASE_DIR / 'data'))) / 'users.xlsx',
    SESSION_COOKIE_SECURE=production,
    MAX_USERS=int(os.environ.get('MAX_USERS', '1000')),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    MAX_CONTENT_LENGTH=16 * 1024,
)


storage_mutex = threading.Lock()
rate_mutex = threading.Lock()
rate_buckets = {}


class StorageUnavailable(Exception):
    pass


@contextmanager
def workbook_lock(path):
    # Thread lock + OS lock: protect a complete read/check/append/save transaction.
    with storage_mutex:
        with open(str(path) + '.lock', 'a') as handle:
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise StorageUnavailable('Workbook is busy')
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


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


def workbook_path():
    path = Path(app.config['USER_FILE'])
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_workbook(wb, path):
    # Replace only after a complete write, so an interrupted save keeps the old file.
    temporary = path.with_suffix('.tmp.xlsx')
    try:
        wb.save(temporary)
        with temporary.open('rb') as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def open_users(path):
    if path.exists():
        wb = load_workbook(path)
        if 'Users' not in wb.sheetnames or [c.value for c in wb['Users'][1]] != ['Username', 'Password']:
            wb.close()
            raise StorageUnavailable('Unexpected workbook format; restore a valid backup')
        return wb
    wb = Workbook()
    ws = wb.active
    ws.title = 'Users'
    ws.append(['Username', 'Password'])
    ws.freeze_panes = 'A2'
    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 90
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='172126')
    save_workbook(wb, path)
    return wb


def account(username, password=None):
    """Read one hash, or append an account; lock the entire read/write operation."""
    path = workbook_path()
    with workbook_lock(path):
        wb = open_users(path)
        try:
            ws = wb['Users']
            for name, saved_hash in ws.iter_rows(min_row=2, max_col=2, values_only=True):
                if name and str(name).casefold() == username.casefold():
                    return False if password is not None else saved_hash
            if password is None:
                return None
            if ws.max_row - 1 >= app.config['MAX_USERS']:
                raise StorageUnavailable('Registration capacity reached')
            ws.append([username, generate_password_hash(password)])
            save_workbook(wb, path)
            return True
        finally:
            wb.close()


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
            flash('Successfully logged in', 'success')
            return redirect(url_for('dashboard'))
    return render_template('login.html', title='Welcome back')


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', title='Your garage')


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
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; script-src 'none'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if production:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.errorhandler(StorageUnavailable)
@app.errorhandler(OSError)
@app.errorhandler(BadZipFile)
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


# Runs at import, including under Gunicorn and PythonAnywhere WSGI.
# Never silently overwrite an existing damaged workbook.
with workbook_lock(workbook_path()):
    initial_workbook = open_users(workbook_path())
    initial_workbook.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)

```

## requirements.txt

```text
Flask==3.1.3
openpyxl==3.1.5
gunicorn==26.2.0

```

## Procfile

```text
web: gunicorn --workers 1 --threads 1 --bind 0.0.0.0:$PORT --timeout 60 --access-logfile - --error-logfile - app:app

```

## wsgi_pythonanywhere.py

```python
"""Copy this content into the WSGI file linked from PythonAnywhere's Web tab.
Replace YOUR_PA_USERNAME in both paths first.
"""
import os
import sys
from pathlib import Path
project = '/home/YOUR_PA_USERNAME/NaV12'
sys.path.insert(0, project)
os.environ['APP_ENV'] = 'production'
os.environ['SECRET_KEY'] = Path('/home/YOUR_PA_USERNAME/.nav12-secret').read_text().strip()
os.environ['DATA_DIR'] = '/home/YOUR_PA_USERNAME/nav12-data'
from app import app as application

```

## .gitignore

```text
.venv/
__pycache__/
*.pyc
data/
*.xlsx
*.xlsx.lock
.env
*.secret

```

## templates/auth.html

```html
{% extends 'base.html' %}
{% block content %}
<section class="auth-layout">
  <div class="intro">
    <p class="eyebrow"><span class="dot"></span> THE AUTOMOTIVE COLLECTIVE</p>
    <h1>Life's better<br>in the <em>fast lane.</em></h1>
    <p class="intro-copy">Iconic machines. Uncompromising design.<br>Your next obsession starts here.</p>
    <div class="car-art" aria-hidden="true"><div class="car-body"></div><div class="wheel rear"></div><div class="wheel front"></div><div class="road"></div></div>
    <div class="intro-bottom"><span>01 / THE PURSUIT OF PERFORMANCE</span><span>EST. 2026</span></div>
  </div>
  <section class="auth-panel" aria-labelledby="form-title">
    <p class="eyebrow">YOUR ACCESS TO THE EXTRAORDINARY</p>
    {% block form %}{% endblock %}
  </section>
</section>
{% endblock %}

```

## templates/base.html

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} · NaV12</title>
  {% include 'styles.html' %}
</head>
<body>
  <header class="site-header">
    <a class="logo" href="{{ url_for('index') }}">NaV<span>12</span><i></i></a>
    <span class="header-caption">FOR THE LOVE OF THE DRIVE</span>
    <nav aria-label="Main navigation">
      {% if session.get('username') %}
      <form method="post" action="{{ url_for('logout') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button class="nav-button" type="submit">Log out ↗</button>
      </form>
      {% else %}
      <a href="{{ url_for('login') }}">Login</a>
      <a class="nav-button" href="{{ url_for('signup') }}">Join the garage ↗</a>
      {% endif %}
    </nav>
  </header>
  <main>
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}<div class="messages" aria-live="polite">
      {% for category, message in messages %}<div class="alert {{ category }}" role="status">{{ message }}</div>{% endfor %}
    </div>{% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>
  <footer><span>NaV12 / THE DRIVER'S COLLECTION</span><span>PASSION. PRECISION. PERFORMANCE.</span></footer>
</body>
</html>

```

## templates/dashboard.html

```html
{% extends 'base.html' %}
{% block content %}
<section class="dashboard">
  <p class="eyebrow"><span class="dot"></span> THE GARAGE / MEMBERS AREA</p>
  <div class="dashboard-heading"><div><h1>Welcome, <em>{{ session['username'] }}.</em></h1><p class="muted">Great cars. Better conversations. Make yourself at home.</p></div><span class="member-tag">● DRIVER CONNECTED</span></div>
  <article class="feature">
    <div><p class="eyebrow">THE PURSUIT OF PERFORMANCE</p><h2>Twelve cylinders.<br>One obsession.</h2><p>From the unmistakable silhouette of a Porsche to the presence of Mercedes-AMG, explore a world of automotive ambition.</p><a class="primary collection-link" href="#collection">Explore the collection <span>↓</span></a></div>
    <div class="feature-graphic">
      <svg class="engine" viewBox="0 0 320 260" role="img" aria-label="Stylized V12 engine illustration with two banks of six cylinders">
        <path d="M35 35 L145 220 L175 220 L285 35" fill="none" stroke="#3b4149" stroke-width="38"/>
        <path d="M45 35 L153 215 M275 35 L167 215" fill="none" stroke="#ff454d" stroke-width="3"/>
        <g fill="#171c21" stroke="#ff454d" stroke-width="2">
          <rect x="43" y="35" width="42" height="22" rx="4"/><rect x="60" y="63" width="42" height="22" rx="4"/>
          <rect x="77" y="91" width="42" height="22" rx="4"/><rect x="94" y="119" width="42" height="22" rx="4"/>
          <rect x="111" y="147" width="42" height="22" rx="4"/><rect x="128" y="175" width="42" height="22" rx="4"/>
          <rect x="235" y="35" width="42" height="22" rx="4"/><rect x="218" y="63" width="42" height="22" rx="4"/>
          <rect x="201" y="91" width="42" height="22" rx="4"/><rect x="184" y="119" width="42" height="22" rx="4"/>
          <rect x="167" y="147" width="42" height="22" rx="4"/><rect x="150" y="175" width="42" height="22" rx="4"/>
        </g>
        <circle cx="160" cy="220" r="18" fill="#111518" stroke="#bcc4ca" stroke-width="4"/>
        <text x="160" y="65" text-anchor="middle" fill="#ffffff" font-size="32" font-weight="bold">V12</text>
      </svg><p class="engine-note">12 CYLINDERS / TWO BANKS / STYLIZED ARTWORK</p>
    </div>
  </article>
  <section aria-label="Lamborghini Revuelto specifications">
    <div class="section-title"><h2>V12 spotlight / Lamborghini Revuelto</h2></div>
    <div class="spec-grid">
      <div class="spec"><strong>6.5 L</strong><span>6498.5 cm³ V12</span></div>
      <div class="spec"><strong>1015 CV</strong><span>Combined hybrid power</span></div>
      <div class="spec"><strong>2.5 s</strong><span>0–100 km/h</span></div>
      <div class="spec"><strong>&gt;350</strong><span>Top speed · km/h</span></div>
    </div>
    <p class="spec-source">Manufacturer figures. Combined power includes the electric motors, not just the V12 engine. <a href="https://www.lamborghini.com/en-en/models/revuelto-models/revuelto" target="_blank" rel="noopener noreferrer">View official specifications ↗</a></p>
  </section>
  <div class="section-title"><h2>The shortlist</h2><span>03 / EDITORIAL PICKS</span></div>
  <div id="collection" class="car-grid">
    <article class="car-card"><div class="card-top"><span>01 / PRECISION</span><span>↗</span></div><div class="card-mark">911</div><h3>Porsche</h3><p>Timeless sports-car design and a relentless fascination with the perfect corner.</p><span class="pill">THE SPORTS CAR ICON</span></article>
    <article class="car-card"><div class="card-top"><span>02 / PRESENCE</span><span>↗</span></div><div class="card-mark">AMG</div><h3>Mercedes-AMG</h3><p>Muscular character, expressive styling, and a passion for performance.</p><span class="pill">PERFORMANCE WITH ATTITUDE</span></article>
    <article class="car-card"><div class="card-top"><span>03 / EMOTION</span><span>↗</span></div><div class="card-mark">GT</div><h3>The grand tourer</h3><p>Long roads, sweeping curves, and the simple pleasure of taking the scenic route.</p><span class="pill">MADE FOR THE JOURNEY</span></article>
  </div>
  <p class="editorial-note">An enthusiast's demo collection. Brand names are used for illustrative content; NaV12 is independent.</p>
</section>
{% endblock %}

```

## templates/error.html

```html
{% extends 'base.html' %}
{% block content %}<section class="dashboard"><h1>{{ title }}</h1><p class="muted">{{ message }}</p><a class="nav-button" href="{{ url_for('login') }}">Return to login</a></section>{% endblock %}

```

## templates/login.html

```html
{% extends 'auth.html' %}
{% block form %}
<h2 id="form-title">Welcome back.</h2>
<p class="muted">Your garage is waiting. Let's get you in.</p>
<form method="post" action="{{ url_for('login') }}" class="account-form">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <label for="username">Username</label>
  <input id="username" name="username" placeholder="Your username" autocomplete="username" maxlength="30" value="{{ request.form.get('username', '') }}" required>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" placeholder="Your password" autocomplete="current-password" maxlength="128" required>
  <button class="primary" type="submit">Enter your garage <span>↗</span></button>
</form>
<p class="switch">New to NaV12? <a href="{{ url_for('signup') }}">Create an account</a></p>
<div class="panel-foot">BUILT FOR PEOPLE WHO LOVE CARS.</div>
{% endblock %}

```

## templates/signup.html

```html
{% extends 'auth.html' %}
{% block form %}
<h2 id="form-title">Find your drive.</h2>
<p class="muted">Join a world built around automotive passion.</p>
<form method="post" action="{{ url_for('signup') }}" class="account-form">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <label for="username">Choose a username</label>
  <input id="username" name="username" placeholder="e.g. night_driver" autocomplete="username" pattern="[A-Za-z0-9_]{3,30}" minlength="3" maxlength="30" aria-describedby="username-help" value="{{ request.form.get('username', '') }}" required>
  <small id="username-help">3–30 letters, numbers, or underscores.</small>
  <label for="password">Create a password</label>
  <input id="password" name="password" type="password" placeholder="At least 8 characters" autocomplete="new-password" minlength="8" maxlength="128" required>
  <button class="primary" type="submit">Create account <span>↗</span></button>
</form>
<p class="switch">Already part of the crew? <a href="{{ url_for('login') }}">Log in</a></p>
{% endblock %}

```

## templates/styles.html

```html
<style>
:root{--bg:#0d1113;--panel:#141a1e;--line:#2a3339;--text:#f3f5f3;--muted:#a1abb1;--accent:#ff454d}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,Helvetica,sans-serif;line-height:1.6}a{color:inherit;text-decoration:none}button,input{font:inherit}button,a,input{outline-offset:5px}a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--accent)}button{cursor:pointer}.site-header{min-height:100px;padding:24px 6%;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:24px}.logo{font-size:30px;font-weight:900;letter-spacing:-2px;font-style:italic}.logo span{color:var(--accent)}.logo i{display:inline-block;width:8px;height:8px;background:var(--accent);margin-left:8px}.header-caption,.eyebrow,.intro-bottom,.panel-foot,footer,.card-top,.section-title>span,.member-tag,.pill{font-size:10px;letter-spacing:2px;font-weight:700}.header-caption{color:var(--muted)}nav{display:flex;align-items:center;gap:28px;font-size:13px}nav form{margin:0}.nav-button{border:1px solid var(--line);background:transparent;color:var(--text);padding:10px 18px;display:inline-block}.nav-button:hover{border-color:var(--accent)}main{min-height:calc(100vh - 181px)}.auth-layout{max-width:1400px;margin:auto;display:grid;grid-template-columns:1.2fr 1fr;min-height:650px}.intro{padding:70px 10% 30px;border-right:1px solid var(--line);overflow:hidden;background:radial-gradient(ellipse at 40% 75%,#263439,transparent 65%)}.eyebrow{color:var(--muted);margin:0 0 24px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:8px}h1{font-size:clamp(36px,4.5vw,65px);letter-spacing:-3px;line-height:1.1;margin:20px 0}em{font-style:normal;color:var(--accent)}.intro-copy,.muted{color:var(--muted);font-size:14px}.intro-bottom{display:flex;justify-content:space-between;gap:15px;color:var(--muted);font-size:8px;border-top:1px solid var(--line);padding-top:24px}.auth-panel{padding:75px 13%;align-self:center}.auth-panel .eyebrow{font-size:9px;letter-spacing:1.5px}.auth-panel h2{font-size:34px;line-height:1.2;letter-spacing:-1px;margin:0 0 10px}.account-form{display:flex;flex-direction:column;margin-top:32px}.account-form label{font-size:12px;margin:16px 0 8px;font-weight:bold}.account-form input{width:100%;border:1px solid #364048;border-radius:3px;padding:13px 15px;background:#101518;color:var(--text)}.account-form input::placeholder{color:#7e8990}.account-form small{color:var(--muted);font-size:11px;margin-top:5px}.primary{background:var(--accent);color:#ffffff;border:0;border-radius:3px;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:20px;font-size:13px;font-weight:bold}.primary:hover{background:#ff6970}.account-form .primary{margin-top:30px}.switch{font-size:12px;color:var(--muted);margin-top:25px}.switch a{color:var(--accent)}.panel-foot{border-top:1px solid var(--line);padding-top:25px;margin-top:36px;font-size:8px;color:var(--muted)}footer{padding:25px 6%;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;color:var(--muted);font-size:8px}.messages{max-width:1200px;padding:20px 24px 0;margin:auto}.alert{padding:12px 18px;border:1px solid #46682a;border-radius:4px;background:#1b291b;color:#d5f5b6;font-size:14px;margin-bottom:8px}.alert.error{background:#321c20;border-color:#70404a;color:#ffc8ce}.car-art{position:relative;height:210px;margin-top:25px}.car-body{position:absolute;top:65px;left:0;width:100%;height:100px;background:linear-gradient(170deg,#ff454d 0%,#862b32 45%,#29181c 85%);clip-path:polygon(0 62%,13% 48%,29% 10%,58% 8%,76% 46%,94% 58%,100% 74%,98% 89%,2% 89%)}.car-body:before{content:'';position:absolute;inset:14px 28% 49px 29%;background:#172125;clip-path:polygon(12% 0,78% 0,100% 100%,0 100%)}.wheel{position:absolute;top:124px;width:49px;height:49px;background:radial-gradient(circle,#8d999d 0 12%,#222d31 14% 40%,#627174 42% 48%,#090c0e 50%);border-radius:50%;box-shadow:0 0 0 4px #101719}.rear{left:14%}.front{right:13%}.road{position:absolute;bottom:28px;width:100%;height:1px;background:linear-gradient(90deg,transparent,#6a7b6e,transparent)}.dashboard{max-width:1280px;margin:auto;padding:48px 5%}.dashboard-heading{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:35px}.dashboard-heading h1{font-size:36px;letter-spacing:-1px;overflow-wrap:anywhere}.member-tag{white-space:nowrap;border:1px solid #71343b;color:var(--accent);padding:10px;font-size:8px}.feature{padding:40px;display:grid;grid-template-columns:1fr 1fr;gap:25px;background:linear-gradient(115deg,#1d292d,#15201c);border:1px solid var(--line);border-radius:5px}.feature h2{font-size:46px;letter-spacing:-2px;line-height:1.1;margin:16px 0}.feature p:not(.eyebrow){font-size:13px;color:#b6c0c3;max-width:400px}.collection-link{max-width:250px;margin-top:25px}.feature-graphic{display:flex;flex-direction:column;justify-content:center;align-items:center;transform:skew(-8deg);color:var(--accent);background:repeating-linear-gradient(135deg,transparent 0 28px,#ffffff04 29px 30px)}.feature-graphic span{font-size:clamp(75px,13vw,180px);font-weight:900;letter-spacing:-12px;line-height:1.2}.feature-graphic small{font-size:9px;letter-spacing:4px}.section-title{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:35px 0 18px}.section-title h2{font-size:22px}.section-title>span{color:var(--muted);font-size:9px}.car-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.car-card{background:var(--panel);border:1px solid var(--line);padding:25px;border-radius:4px}.card-top{display:flex;justify-content:space-between;color:var(--muted);font-size:8px}.card-mark{font-size:55px;font-style:italic;font-weight:900;letter-spacing:-3px;color:#7e929a;margin:15px 0}.car-card:nth-child(2) .card-mark{color:#ff454d}.car-card:nth-child(3) .card-mark{color:#c1aa89}.car-card h3{margin:0;font-size:20px}.car-card p{font-size:12px;color:var(--muted);min-height:60px}.pill{font-size:7px;color:#c4ceca;border-top:1px solid var(--line);display:block;padding-top:16px}.editorial-note{color:var(--muted);font-size:10px;margin-top:24px}@media(max-width:800px){.header-caption{display:none}.auth-layout{grid-template-columns:1fr}.intro{border-right:0;border-bottom:1px solid var(--line);padding:40px 8%}.intro h1{font-size:45px}.car-art{max-width:420px;height:185px}.auth-panel{padding:40px 8%}.dashboard-heading{align-items:flex-start;flex-direction:column}.feature{grid-template-columns:1fr;padding:25px}.feature-graphic{display:none}.car-grid{grid-template-columns:1fr}.car-card p{min-height:0}footer{flex-direction:column;gap:6px}.site-header{padding:20px 6%;gap:15px}nav{gap:14px;font-size:12px}.nav-button{padding:8px 10px}.section-title>span{letter-spacing:1px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}

.spec-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}.spec{background:#19191d;border:1px solid var(--line);padding:24px}.spec strong{display:block;font-size:30px;letter-spacing:-1px}.spec span{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}.engine{width:100%;max-width:320px;height:auto}.feature-graphic{transform:none}.spec-source{font-size:11px;color:var(--muted)}.spec-source a{color:var(--accent);text-decoration:underline}.engine-note{font-size:9px;color:var(--muted);letter-spacing:1px}@media(max-width:650px){.spec-grid{grid-template-columns:repeat(2,1fr)}}

</style>

```
