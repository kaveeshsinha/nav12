# NaV12

Flask automotive website with car collections, brand previews, engine guides, personal garages, and secure account storage. Production accounts live in PostgreSQL on Neon. SQLite is used only for local development when DATABASE_URL is unset. Signup and login no longer read or write Excel.

## My Garage and favourites

Signed-in members can save or remove cars from catalogue cards and individual car pages, then open **My Garage** from the header. Choose a dream rank and select **Update** to reorder favourites; position #1 is the dream car. Select 2–4 saved cars to compare their specifications.

Favourites and ranks are stored in `garage_favourites` in the same database as accounts: Neon PostgreSQL in production, SQLite for local development. Startup creates this additional table automatically using the existing `DATABASE_URL`; no installer or Excel workbook is needed. Existing accounts and password hashes remain intact. Favourites saved by the old local Excel installer are not imported automatically.

The four exploration menus open on hover with one shared panel that moves page content down. The search icon opens its panel on click or keyboard activation. Keyboard and touch controls are supported. Login uses a headlight password toggle; signup has a Show/Hide control. Successful login opens the dashboard without a success banner.

## Local development

Use Python 3.11 or newer. From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. A private development database is created at data/nav12.sqlite3. Test signup, login, and logout. Development accounts are separate from Neon unless you explicitly set DATABASE_URL.

## Deploy on Render with Neon

1. Create a Neon project named nav12 on the Free plan. Choose AWS Singapore so the database is near the Render service.
2. In Neon, select Connect, the production branch, and the database (usually neondb). Use the pooled connection URL, including its sslmode and channel_binding parameters. Copy only the URL, without a psql command. This URL contains a password: keep it out of GitHub, screenshots, logs, and chat.
3. In Render, create a Web Service from kaveeshsinha/nav12, branch main. Select Python, Singapore, and the Free instance. Leave Root Directory blank.
4. Build command: pip install -r requirements.txt
5. Start command:

```bash
gunicorn --workers 1 --threads 1 --bind 0.0.0.0:$PORT --timeout 60 --access-logfile - --error-logfile - app:app
```

6. Add these environment variables in Render's private settings:

| Name | Value |
|---|---|
| APP_ENV | production |
| DATABASE_URL | Paste the full pooled Neon PostgreSQL URL |
| SECRET_KEY | A private random value of at least 32 characters |

Generate SECRET_KEY locally with python -c "import secrets; print(secrets.token_hex(32))" and paste the result only in Render. Keep the value stable across deployments. Render supplies PORT. DATA_DIR is unnecessary in production.

7. Set Health Check Path to /healthz and deploy. Startup creates the users and garage_favourites tables if absent; it never drops or empties an existing table. Production refuses to start without an external PostgreSQL DATABASE_URL.
8. Open the HTTPS onrender.com address supplied by Render. Register a test account, log in and out, redeploy, and verify the same account can still log in. Neon holds the accounts outside Render's temporary filesystem.

Alternatively, use the included render.yaml Blueprint. It selects the Free instance, prompts for DATABASE_URL, and generates SECRET_KEY. Do not create a Render Postgres service: this setup uses the existing Neon database.

Render's Free instance sleeps after inactivity, so the next visitor can see a startup delay. Both services have Free-plan usage limits. The old avada.pythonanywhere.com site is separate and is not changed by this deployment.

## Existing accounts from Excel

Old accounts are not transferred automatically. Obtain a current private backup of the old users.xlsx from the old server when account access is restored. An older downloaded workbook contains only the accounts present when it was copied.

Run the importer in a private environment with DATABASE_URL set to the destination database:

```bash
python import_users.py /private/path/users.xlsx
python import_users.py /private/path/users.xlsx --apply
```

The first command previews counts without changing accounts. The second imports them in one transaction. Existing Werkzeug password hashes are copied unchanged so users keep their passwords. Plaintext passwords, malformed rows, and duplicate usernames are rejected. An existing identical account is skipped; a different existing hash aborts the import rather than replacing that account. The workbook is never modified. Do not upload it to GitHub or place it in static/.

## Password recovery

Login includes **Forgot password?**. Signed-in users can open **Account security** to add a recovery email (current password required), confirm the verification link, or change their password. Recovery is available only after an address has been verified. Signup and existing usernames remain unchanged.

Reset links are single-use and expire after 30 minutes; verification links expire after 24 hours. Password changes, recovery and successful email verification sign out old sessions on their next request. Users must log in once again after installing this update. Recovery state is stored in the new `account_security` table in the same Neon/PostgreSQL database, or in the existing local SQLite database during development. Startup adds the table without changing existing account or garage rows.

Email delivery requires Resend or SMTP settings. See [PASSWORD-RECOVERY.md](PASSWORD-RECOVERY.md) for configuration, behavior and verification. Change-password works before email delivery is configured.

## Administrator password reset

With the same DATABASE_URL configured:

```bash
python reset_password.py
```

The tool asks for the username and a hidden, confirmed new password. It changes only an existing account; no credentials are embedded in source.

## Operating behavior

- Usernames are case-insensitive, 3–30 ASCII letters/digits/underscores; passwords are case-sensitive, 8–128 characters.
- The users table stores username, a unique normalized username_key, password_hash, created_at, and id. Passwords are salted Werkzeug hashes, never plaintext.
- Bound SQL parameters and a database uniqueness constraint protect account queries and duplicate registrations. Write transactions serialize the registration cap and imports. MAX_USERS defaults to 1000 and can be adjusted deliberately.
- Production requires TLS, a stable signing key, Secure/HttpOnly/SameSite cookies, CSRF checks, and HTTPS. Database errors produce a generic 503 page without credentials or SQL parameters.
- Keep one Gunicorn worker/thread: the existing in-memory auth rate limiter is designed for one process. PostgreSQL itself handles persistent account data.
- /healthz checks the application process without continually querying Neon, allowing idle database compute to sleep.
- Follow the providers' backup, recovery, billing, and usage controls. Automatic table creation supports this initial schema; future schema changes should use reviewed migrations.

## Verification

```bash
python -m unittest discover -s tests -v
node --check static/collection/collection.js
```

Tests use disposable development databases and synthetic credentials. They never use DATABASE_URL from your normal environment. NAV12_TEST_DATABASE_URL is an optional explicit override for a disposable PostgreSQL test database only.

## Source layout

app.py contains Flask routes and session/CSRF behavior; accounts.py contains database transactions; recovery.py and recovery_store.py handle verified email and password recovery; mailer.py provides Resend/SMTP delivery; garage.py handles member favourites, rankings and comparisons; collection.py and catalogue/ provide automotive content; templates/ and static/ provide the UI; import_users.py is a private one-time Excel migration tool. openpyxl remains a dependency only for that importer.

COLLECTION-UPDATE.md, NAVIGATION-UPDATE.md, and docs/ record the earlier UI work; their older Excel storage references are historical. Use this README for current deployment and storage configuration.

Official documentation: https://render.com/docs/deploy-flask, https://render.com/docs/free, https://neon.com/docs/connect/connect-from-any-app, https://neon.com/docs/connect/connection-pooling.
