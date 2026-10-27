"""Recovery routes using the application's existing account database."""
import hashlib
import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from mailer import MailUnavailable, mail_ready, public_base, send_mail
from recovery_store import RecoveryStore


class RecoveryLimiter:
    """Bounded single-worker limits; no trusted proxy-header assumptions."""
    def __init__(self):
        self.buckets = {}
        self.lock = threading.Lock()

    def allow(self, identity, address, action):
        now = time.monotonic()
        digest = hashlib.sha256(identity.casefold().encode()).hexdigest()
        keys = [('global', 100, 3600), ('ip:' + address, 30, 900),
                (action + ':' + digest, 5 if action in {'forgot', 'email'} else 15, 900)]
        with self.lock:
            for key in list(self.buckets):
                bucket = self.buckets[key]
                while bucket and bucket[0] <= now - 3600:
                    bucket.popleft()
                if not bucket:
                    del self.buckets[key]
            if any(sum(t > now - window for t in self.buckets.get(key, ())) >= cap
                   for key, cap, window in keys):
                return False
            for key, _, _ in keys:
                self.buckets.setdefault(key, deque()).append(now)
            return True


class MailJobs:
    """Best-effort bounded async jobs: no account-dependent email latency on reset requests."""
    def __init__(self, app):
        self.app = app
        self.executor = None
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(20)

    def submit(self, job):
        if self.app.config.get('TESTING') and self.app.config.get('MAIL_SYNC'):
            job()
            return True
        if not self.slots.acquire(blocking=False):
            return False
        def run():
            try:
                with self.app.app_context():
                    job()
            except Exception:
                self.app.logger.error('Recovery email job could not be completed.')
            finally:
                self.slots.release()
        with self.lock:
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='nav12-mail')
        try:
            self.executor.submit(run)
        except RuntimeError:
            self.slots.release()
            return False
        return True


def register_recovery(app, login_required):
    settings = {'MAIL_PROVIDER': '', 'MAIL_FROM': '', 'PUBLIC_BASE_URL': '',
                'RESEND_API_KEY': '', 'SMTP_HOST': '', 'SMTP_PORT': '587',
                'SMTP_SECURITY': 'starttls', 'SMTP_USERNAME': '', 'SMTP_PASSWORD': ''}
    for key, default in settings.items():
        app.config.setdefault(key, os.environ.get(key, default))
    store = RecoveryStore(lambda: app.extensions['accounts'])
    store.initialize()
    limiter = RecoveryLimiter()
    jobs = MailJobs(app)
    app.extensions.update(recovery=store, recovery_limiter=limiter, recovery_mail_jobs=jobs)
    recovery = Blueprint('recovery', __name__)

    def throttle(identity, action):
        if not limiter.allow(identity[:254], request.remote_addr or 'unknown', action):
            abort(429, description='Too many recovery attempts. Please wait 15 minutes.')

    def link(purpose, token):
        path = '/reset-password' if purpose == 'reset' else '/verify-email'
        return public_base(app.config) + path + '#token=' + quote(token, safe='')

    def deliver_token(recipient, token, purpose):
        try:
            if purpose == 'reset':
                subject = 'Reset your NaV12 password'
                text = ('Open this link to choose a new password. It expires in 30 minutes '
                        'and can be used once.\n\n' + link(purpose, token) +
                        '\n\nIf you did not request a reset, ignore this email. Your password has not changed.')
            else:
                subject = 'Verify your NaV12 recovery email'
                profile = store.token_profile(token, 'verify')
                if not profile:
                    return False
                text = ('Confirm ' + recipient + ' as the recovery email for NaV12 username: '
                        + profile['username'] + '.\nOnly confirm if this is the account you intended.\n\n'
                        'This link expires in 24 hours '
                        'and can be used once.\n\n' + link(purpose, token) +
                        '\n\nIf you did not request this, ignore this email.')
            send_mail(app.config, recipient, subject, text)
        except MailUnavailable:
            store.revoke_token(token, purpose)
            app.logger.error('Recovery email delivery failed; link revoked.')
            return False
        return True

    def notification(profile, message='Your NaV12 password has changed.'):
        if profile and profile.get('email') and mail_ready(app.config):
            def deliver():
                try:
                    send_mail(app.config, profile['email'], 'NaV12 account security update',
                              message + '\n\nIf this was not you, contact the site owner immediately.')
                except MailUnavailable:
                    app.logger.error('Account security notification could not be delivered.')
            jobs.submit(deliver)

    @app.before_request
    def validate_member_session():
        if request.endpoint == 'static' or 'username' not in session:
            return
        profile = store.snapshot(session['username'])
        if (not profile or 'auth_version' not in session
                or session['auth_version'] != profile['version']):
            session.clear()
            flash('Your session has ended. Please log in again.', 'error')
            if request.endpoint not in {'recovery.forgot_password', 'recovery.reset_password',
                                        'recovery.verify_email', 'recovery.accept_link', 'login'}:
                return redirect(url_for('login'), code=303)

    @recovery.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        ready = mail_ready(app.config)
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            throttle(email, 'forgot')
            if not ready:
                return render_template('forgot_password.html', title='Password recovery', mail_ready=False, sent=False), 503
            # Enqueue the lookup as well as delivery: unknown accounts follow the same HTTP path.
            def attempt():
                try:
                    normalized = store.normalize_email(email)
                except ValueError:
                    return
                if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', username):
                    return
                token = store.issue_reset(username, normalized)
                if token:
                    profile = store.token_profile(token, 'reset')
                    if profile:
                        deliver_token(profile['email'], token, 'reset')
            if not jobs.submit(attempt):
                app.logger.warning('Recovery email queue is full.')
            return redirect(url_for('recovery.forgot_password', sent='1'), code=303)
        return render_template('forgot_password.html', title='Password recovery',
                               mail_ready=ready, sent=request.args.get('sent') == '1')

    @recovery.post('/recovery/link/<purpose>')
    def accept_link(purpose):
        if purpose not in {'reset', 'verify'}:
            abort(404)
        throttle(request.remote_addr or 'unknown', 'link')
        token = request.form.get('token', '')
        key = 'recovery_' + purpose
        session.pop(key, None)
        if store.token_valid(token, purpose):
            session[key] = token
        return redirect(url_for('recovery.reset_password' if purpose == 'reset' else 'recovery.verify_email'), code=303)

    @recovery.route('/reset-password', methods=['GET', 'POST'])
    def reset_password():
        token = session.get('recovery_reset', '')
        valid = store.token_valid(token, 'reset')
        if request.method == 'POST':
            throttle(request.remote_addr or 'unknown', 'reset')
            password = request.form.get('password', '')
            confirm = request.form.get('confirm_password', '')
            if not valid:
                session.pop('recovery_reset', None)
            elif not 8 <= len(password) <= 128:
                flash('Your password must contain 8–128 characters.', 'error')
            elif password != confirm:
                flash('The passwords do not match.', 'error')
            else:
                profile = store.token_profile(token, 'reset')
                try:
                    changed = store.reset_password(token, password)
                except ValueError as error:
                    flash(str(error), 'error')
                else:
                    if changed:
                        session.clear()
                        notification(profile)
                        flash('Password reset. Log in with your new password.', 'success')
                        return redirect(url_for('login'), code=303)
                    valid = False
        return render_template('reset_password.html', title='Choose a new password', valid=valid)

    @recovery.route('/verify-email', methods=['GET', 'POST'])
    def verify_email():
        token = session.get('recovery_verify', '')
        valid = store.token_valid(token, 'verify')
        if request.method == 'POST':
            throttle(request.remote_addr or 'unknown', 'verify')
            profile = store.token_profile(token, 'verify')
            if store.verify_email(token):
                session.clear()
                if profile and profile.get('email') != profile.get('pending_email'):
                    notification(profile, 'Your NaV12 recovery email address has changed.')
                flash('Recovery email verified. Please log in again.', 'success')
                return redirect(url_for('login'), code=303)
            session.pop('recovery_verify', None)
            valid = False
        return render_template('verify_email.html', title='Verify your recovery email', valid=valid,
                               verification=store.token_profile(token, 'verify') if valid else None)

    @recovery.route('/account/security', methods=['GET', 'POST'])
    @login_required
    def account_security():
        profile = store.snapshot(session['username'])
        ready = mail_ready(app.config)
        if request.method == 'POST':
            throttle(session['username'], 'email')
            if not ready:
                flash('Email recovery is not available yet. Please try again later.', 'error')
            else:
                try:
                    email = store.normalize_email(request.form.get('email', ''))
                    token = store.set_pending_email(session['username'], request.form.get('current_password', ''), email)
                    if not token:
                        flash('Your current password is incorrect.', 'error')
                    elif deliver_token(email, token, 'verify'):
                        flash('Verification email sent. Open the link to confirm your address.', 'success')
                        return redirect(url_for('recovery.account_security'), code=303)
                    else:
                        flash('We could not send your verification email. Please try again later.', 'error')
                except ValueError as error:
                    flash(str(error), 'error')
            profile = store.snapshot(session['username'])
        return render_template('account_security.html', title='Account security', profile=profile, mail_ready=ready)

    @recovery.route('/account/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if request.method == 'POST':
            throttle(session['username'], 'change')
            password = request.form.get('password', '')
            if not 8 <= len(password) <= 128:
                flash('Your password must contain 8–128 characters.', 'error')
            elif password != request.form.get('confirm_password', ''):
                flash('The passwords do not match.', 'error')
            else:
                profile = store.snapshot(session['username'])
                try:
                    changed = store.change_password(session['username'], request.form.get('current_password', ''), password)
                except ValueError as error:
                    flash(str(error), 'error')
                else:
                    if changed:
                        session.clear()
                        notification(profile)
                        flash('Password changed. Log in with your new password.', 'success')
                        return redirect(url_for('login'), code=303)
                    flash('Your current password is incorrect.', 'error')
        return render_template('change_password.html', title='Change your password')

    @recovery.after_request
    def recovery_headers(response):
        response.headers['Referrer-Policy'] = 'no-referrer'
        if response.status_code == 429:
            response.headers['Retry-After'] = '900'
        return response

    app.register_blueprint(recovery)
    return store
