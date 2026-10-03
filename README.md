# NaV12 — public deployment edition

Complete Flask/OpenPyXL code, dark/red automotive UI, embedded CSS, an original inline SVG engine illustration, signup/login/logout, and manufacturer-sourced V12 statistics. Python 3.11+ on Linux/macOS; on Windows use WSL. This is a hardened small-app starter, not a claim that Excel is a scalable production identity store.

## Hosting choice — read before deploying

| Hosting path | Free | Workbook survives ordinary reloads/restarts | Server |
|---|---|---|---|
| PythonAnywhere standard web app | Yes, within free limits | Yes, in your account home directory | Provider-managed WSGI |
| Render Free web service | Yes, within free limits | NO: files disappear on restart, redeploy or spin-down | Gunicorn |
| Render paid service + persistent disk | No | Yes, only under the mounted disk path | Gunicorn |

There is no configuration that gives Render Free a persistent local users.xlsx. Use PythonAnywhere for a free persistent Excel app if its managed WSGI server is acceptable. Use Render Free only for disposable demonstrations. If Gunicorn and durable Excel are both mandatory, the documented Render solution needs a paid service and persistent disk. PythonAnywhere has an experimental Gunicorn hosting system, but its documentation does not guarantee long-term free pricing; this guide does not depend on it.

PythonAnywhere currently lists one free web worker, 512 MiB disk space, and a one-month web-app expiry. Renew the app using the expiry/extend control on its Web tab before that date. A public URL is assigned by the provider after YOU deploy; none is created by downloading this project.

## Project structure

```text
NaV12/
  app.py
  requirements.txt
  Procfile
  wsgi_pythonanywhere.py
  README.md
  SOURCE_CODE.md
  .gitignore
  templates/
    base.html
    styles.html
    auth.html
    login.html
    signup.html
    dashboard.html
    error.html
  data/                  # created automatically, not committed
    users.xlsx
    users.xlsx.lock
```

`styles.html` contains embedded CSS included by `base.html`, shared by all three pages. There is no frontend build, JavaScript, CDN or external image dependency. SOURCE_CODE.md contains every source file together for easy reading/copying.

## 1. Local check

Extract the archive. In the extracted NaV12 folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. Sign up, log in, and log out. Ctrl+C stops it. The workbook is created on server boot, including WSGI import. The development entry point binds to `0.0.0.0` and `int(os.environ.get('PORT', 5000))`; cloud production traffic uses WSGI, not this development entry point.

## 2. Push to GitHub

Create an empty GitHub repository named `NaV12` (do not initialize it with a README). From the extracted NaV12 folder, replace YOUR_GITHUB_USERNAME:

```bash
git init
git branch -M main
git add .
git status
git commit -m "Build NaV12 Flask automotive app"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/NaV12.git
git push -u origin main
```

Use GitHub's browser/credential-manager authentication or a token when Git asks; an account password is not a Git HTTPS credential. Never put a token in source or the remote URL. Public repositories are easiest to clone in the PythonAnywhere instructions; source can be public, while account data and secrets must remain private. Inspect git status: .gitignore excludes workbooks, secrets and your virtual environment. Do not force-add them.

## 3A. PythonAnywhere — recommended FREE Excel path

This uses PythonAnywhere's standard managed WSGI server, not Gunicorn or the Procfile.

1. Create a Beginner/free account at https://www.pythonanywhere.com/.
2. Open a **Bash console**. Replace YOUR_GITHUB_USERNAME and clone:

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/NaV12.git ~/NaV12
cd ~/NaV12
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Use another supported Python 3.11+ version if 3.13 is unavailable, and select that SAME version when creating the web app.

3. Create a private signing key once (the following deliberately refuses to overwrite an existing key):

```bash
python - <<'PY'
from pathlib import Path
import os
import secrets
os.umask(0o077)
with (Path.home() / '.nav12-secret').open('x') as f:
    f.write(secrets.token_hex(32))
PY
```

4. Go to **Web → Add a new web app → Manual configuration**. Select the Python version used above.
5. Set the Virtualenv field to `/home/YOUR_PA_USERNAME/NaV12/.venv` and the source directory to `/home/YOUR_PA_USERNAME/NaV12`.
6. Open the **WSGI configuration file linked in the Web tab**. Replace its contents with `wsgi_pythonanywhere.py` from this project. Replace every `YOUR_PA_USERNAME` with your actual PythonAnywhere username. Do not simply edit the project copy and assume the host will discover it.
7. The WSGI file sets `APP_ENV=production`, reads the private signing key, and sets `DATA_DIR=/home/YOUR_PA_USERNAME/nav12-data`. Startup creates the directory/workbook automatically.
8. Enable **Force HTTPS** in the Web tab. Production cookies are Secure and require HTTPS.
9. Click **Reload** and open the HTTPS domain shown on the Web tab. Your provider-assigned domain is the public URL you can share. There is no need to run `python app.py` or Gunicorn in a console.
10. Register a test account, log in, log out, reload the web app and log in again to confirm persistence. Download a private backup of the workbook from the Files tab while registrations are paused.

Updates:

```bash
cd ~/NaV12
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Then click Reload. The account file is outside the repository, so ordinary code updates do not replace it. Check the app's expiry date monthly and extend it. If startup fails, read the error log linked on the Web tab; do not delete the existing workbook as a generic fix.

## 3B. Render Free — Gunicorn demonstration, NONPERSISTENT accounts

1. Sign in at https://render.com/ and choose **New → Web Service**.
2. Connect the GitHub repository and select branch `main`, runtime **Python**, and the **Free** instance type. If app.py is at the repository root, leave Root Directory blank.
3. Build command:

```bash
pip install -r requirements.txt
```

4. Start command (paste it explicitly; do not rely on Render reading Procfile):

```bash
gunicorn --workers 1 --threads 1 --bind 0.0.0.0:$PORT --timeout 60 --access-logfile - --error-logfile - app:app
```

5. Add environment variables:

| Name | Value |
|---|---|
| APP_ENV | production |
| SECRET_KEY | Generate a private random 64-character hex value |

Generate the key locally using:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste it only into Render's secret/environment settings. Render supplies PORT. DATA_DIR can remain unset on the Free demo; choosing another path does not make it persistent.

6. Set Health Check Path to `/healthz` and create the service. Wait for successful deployment. Open the HTTPS `onrender.com` URL displayed by Render and share that exact URL.
7. Test signup/login. Free services spin down after inactivity (currently 15 minutes), and registered accounts are lost on spin-down, restart or redeploy. Do not use this path for real retained accounts.

For durable Gunicorn hosting on Render, choose a paid instance and attach a persistent disk at `/var/data`. Set `DATA_DIR=/var/data/nav12`, keeping SECRET_KEY stable, and redeploy. Only files beneath the disk mount survive. Back up an existing workbook before migrating; do not assume data from an ephemeral deployment will be transferred.

## Security and operating scope

- Passwords are salted Werkzeug hashes in the Excel Password column, never plaintext. Login checks the submitted password against that hash.
- Usernames are case-insensitive, 3–30 ASCII letters/digits/underscores. Passwords are case-sensitive, 8–128 characters.
- Duplicate usernames are checked while holding both a thread lock and an OS file lock; writes use a temporary XLSX and atomic replacement. fcntl is built into Unix Python; no fourth dependency is required.
- Boot validates the existing workbook header. Invalid workbooks are not silently overwritten.
- Production requires a stable SECRET_KEY of at least 32 characters. Secure/HttpOnly/SameSite cookies, CSRF checks, session expiration, security headers and no-cache account pages are configured. The host terminates HTTPS.
- One instance, one worker, one thread are intentional. The in-memory limiter permits at most 60 auth submissions total/minute and 10 per username/minute; it resets on restart and is not a distributed abuse-protection service. Authentication throttling can affect legitimate users during abuse.
- MAX_USERS defaults to 1000 to bound workbook growth. Every login scans Excel, so this is suited to small usage. Do not scale this app across separate filesystems or multiple replicas. Keep the workbook private and closed in desktop editors during use.
- The requested distinct login errors reveal whether a username exists. This behavior is retained intentionally.
- Backups, availability monitoring, abuse handling, password recovery and ongoing dependency updates remain operator responsibilities. Public hosting plus Gunicorn does not turn an Excel file into a full production identity platform.

## Acceptance checklist

- Boot creates a real XLSX with sheet Users and headers Username, Password.
- Signup appends exactly one row; a case-insensitive duplicate does not append.
- Unknown username: User not found. Wrong password: Incorrect credentials.
- Correct login: redirect to dashboard and Successfully logged in.
- Anonymous dashboard request: redirects to login. Logout clears the session.
- After restart on persistent hosting, the same user can log in again.
- Requests to `/data/users.xlsx` cannot download the account workbook.

## Sources (checked October 2, 2026)

- https://render.com/docs/free
- https://render.com/docs/disks
- https://render.com/docs/web-services
- https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
- https://help.pythonanywhere.com/pages/Flask/
- https://help.pythonanywhere.com/pages/FlaskWithTheNewWebsiteSystem/
- https://www.lamborghini.com/en-en/models/revuelto-models/revuelto

Revuelto figures are manufacturer claims: 6498.5 cm³ displacement, 1015 CV combined hybrid output, 2.5 seconds 0–100 km/h and top speed above 350 km/h. The graphic is a stylized original V12 illustration, not a mechanical diagram or a branded engine rendering.
