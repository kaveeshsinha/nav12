# Password recovery for NaV12

This version uses the existing account database: Neon/PostgreSQL in production and SQLite during local development. It is compatible with the current GitHub deployment. The older laptop Excel installer is a separate version; do not run it over this database version.

## User flow

- Login → **Forgot password?** → enter username and previously verified recovery email.
- Logged in → **Account security** → enter your email and current password → open the email → confirm the named account and address.
- Open a reset email → choose and confirm a new password → log in again.
- Account security → **Change password** → enter current password and the new password twice.

An account without a verified address cannot use email recovery. Someone already locked out must use the site owner's existing manual recovery process. The administrator's `python reset_password.py` command continues to work and also invalidates old sessions and tokens.

## Email configuration

Set these in Render's **Environment** settings, or export them in your local terminal before starting Flask. Keep your existing `DATABASE_URL` and stable `SECRET_KEY`. The `.env.example` file is a reference; the application does not load it automatically. Never commit real provider credentials.

### Resend

| Variable | Value |
| --- | --- |
| `MAIL_PROVIDER` | `resend` |
| `MAIL_FROM` | Your authorized sender, e.g. `NaV12 <security@your-domain.example>` |
| `RESEND_API_KEY` | Your private sending key |
| `PUBLIC_BASE_URL` | Your real HTTPS site origin, such as `https://nav12.onrender.com`, with no path |

Use a sender/domain authorized in your Resend account. Reference: https://resend.com/docs/api-reference/emails/send-email

### SMTP alternative

| Variable | Value |
| --- | --- |
| `MAIL_PROVIDER` | `smtp` |
| `MAIL_FROM` | Your authorized sender |
| `SMTP_HOST` | Your provider's SMTP host |
| `SMTP_PORT` | Your provider's port, usually `587` for STARTTLS or `465` for implicit TLS |
| `SMTP_SECURITY` | `starttls` or `ssl` |
| `SMTP_USERNAME` | SMTP username, if required |
| `SMTP_PASSWORD` | SMTP password/app password |
| `PUBLIC_BASE_URL` | Your real HTTPS site origin |

Both SMTP modes validate TLS certificates; plaintext SMTP is unsupported. SendGrid may be used through its SMTP credentials. For local testing only, a localhost origin such as `http://127.0.0.1:5001` is allowed outside production; it can be opened only on the computer serving Flask.

Once configured, restart/redeploy, create a test account, log in, verify its recovery email, request a reset, and confirm the link works once and the old password no longer works. No provider accounts or domains are created automatically. No real delivery was performed during automated tests.

## Storage and deployment

Startup creates one additional `account_security` table in the configured database. Existing users, password hashes and garage favourites are retained. The table stores verified and pending email, a session version, and SHA-256 token digests with purpose, expiry, email and version binding. Raw tokens and plaintext passwords are never saved in the database.

No Excel account file is created or used by this implementation. There are no destructive migrations and no manual SQL step. Use your normal GitHub/Render deployment process. Keep one Gunicorn worker as documented in README; rate limiting remains process-local.

The existing account write lock also protects recovery writes: a PostgreSQL transaction-scoped advisory lock, or SQLite BEGIN IMMEDIATE. Token consumption, password update, token invalidation and session-version increment commit together. Email uniqueness is rechecked under the same lock and enforced by a database constraint.

## Security behavior

- Reset links expire after 30 minutes; verification links after 24 hours. A newer token of the same purpose replaces the earlier one. Tokens are random, one-use and purpose-bound.
- Current password is required to set/change recovery email or change a password. A pending replacement does not disable the existing verified address. Only one account may own a verified email.
- Password changes, administrator resets and successful email verification increment the session version. Existing sessions are rejected on their next request. Users are not automatically logged in after a reset.
- Verification messages and screens identify the target username and email. Confirm only if this is your intended account.
- ASCII mailbox syntax is supported. Local-part case is preserved for delivery; the domain is lowercased. Lookup and uniqueness are case-insensitive. Non-ASCII addresses are rejected rather than converted into another mailbox.
- All state-changing requests require CSRF validation. GET does not consume a token. Link tokens are placed in URL fragments, removed by same-origin JavaScript, then posted to the app and held in an HttpOnly signed session cookie. They stay out of HTTP request URLs and referrers. JavaScript is required to open these links; disable security-email click tracking/link rewriting if your provider offers it.
- Link pages use no-store and no-referrer policies and no third-party assets. Links use configured PUBLIC_BASE_URL rather than an incoming Host header.
- Forgot-password lookup and delivery run in a bounded background queue; unknown, unverified and matching accounts receive the same response. This confirmation does not guarantee delivery. Failed sends revoke the relevant token. An application restart may discard queued messages; request a new link if none arrives.
- Missing email settings produce a temporary-unavailable message and never display or log a recovery link. Change-password remains available.
- Recovery requests have global, source-IP and identity limits. Limits are in memory and reset on restart. Behind a proxy, the IP limit may be shared; arbitrary forwarded headers are not trusted. Add trusted edge abuse controls before scaling.
- Password-change notifications are best-effort. A delivery failure cannot roll back a completed password change. The existing 8–128-character password policy and distinct login errors remain.

Design reference: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

## Verification

```bash
python -m unittest discover -s tests -v
node --check static/recovery-link.js
```

The tests use disposable SQLite databases and mocked providers. They cover success, expiry, replay, current-password checks, verified email ownership, CSRF, session invalidation, one-winner concurrent resets, persistence across connections, PostgreSQL schema compilation, existing account/garage preservation and Resend/SMTP adapters. A live Neon database and real email delivery are not exercised.
