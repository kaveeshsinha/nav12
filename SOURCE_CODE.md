# NaV12 source code

The executable source files in this repository are authoritative. This index replaces the earlier combined listing, which described the obsolete Excel account backend.

| File or folder | Purpose |
|---|---|
| app.py | Flask pages, authentication routes, sessions, CSRF, HTTP security |
| accounts.py | PostgreSQL account storage and local development SQLite |
| collection.py, catalogue/ | Car and engine catalogue |
| templates/, static/ | Page markup, styling, JavaScript, local media |
| import_users.py | Private, explicit migration from an Excel backup |
| reset_password.py | Interactive database account password reset |
| requirements.txt | Pinned Python dependencies |
| Procfile, render.yaml | Render startup and deployment configuration |
| tests/ | Authentication, database, catalogue, and navigation regressions |

Follow README.md for Render + Neon setup. Production requires DATABASE_URL and SECRET_KEY in the host's private environment settings; neither belongs in this repository. Account data is not stored in Excel after migration.
