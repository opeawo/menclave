# The Enclave

Fresh standalone community implementation. No previous data is imported. No legacy service is required.

## Local operation

Install `requirements.txt` in a virtual environment, then run `.venv/bin/python server/app.py` from the project directory. Open `/enclave.html` on the printed URL. The standard static server can still preview the magazine but cannot handle community requests.

SQLite storage defaults to `.local/enclave.sqlite3`, which is ignored by Git. Storage persists across restarts. No fake community posts or activity counts are seeded.

For moderation, set `ENCLAVE_ADMIN_KEY` in the server environment to a randomly generated secret of at least 32 characters. Use a password manager to generate and retain it; never commit it or put it in a URL. Restart the server and open `/moderation.html`. The moderator page holds the entered key in memory, clears the input and includes an explicit lock action. Without a configured key, moderation API access is disabled, including the local preview started without that variable.

New questions and replies are pending until a moderator approves them. The public feed includes only approved questions and approved replies. Removing a question purges its body/title and those of its replies, hides the thread, and resolves associated reports. Removing a reply purges that reply. Reports may also be dismissed. Backup copies can retain previous text until their retention period expires.

## Privacy and abuse controls

- No name, email, account or public user identifier. Public API responses contain only post IDs, category, text, timestamps and approved reply counts/content.
- HttpOnly, SameSite=Strict anonymous session cookie, 30-day lifetime. The database stores a keyed digest for ownership/report deduplication rather than the cookie itself.
- Request logging is disabled. Network addresses are used transiently for keyed rate-limit buckets, not saved in clear text. Hosting/proxy logs need their own privacy settings.
- Server-side input limits; parameterized SQL; client renders submitted content with textContent; JSON response content type and restrictive CSP.
- Writes require the configured same origin and a CSRF token bound to the cookie. No cross-origin API access.
- Write limits: 10 attempts per anonymous session per 10 minutes and 30 per network address per hour. Moderator requests are limited to 60 per address per 10 minutes. Abuse counters are bounded to the newest 10,000 rows during periodic cleanup. Cookie resets cannot bypass the network limit. These are baseline controls, not comprehensive bot protection.
- Reports deduplicate per post/session. No attachments, rich HTML, direct messages or public profiles.
- Posts remain identifying if their authors include identifying details. Moderators must review that risk; the interface explains it before submission.

## API

GET `/api/session` issues a cookie and CSRF token. GET `/api/threads?q=&topic=` lists up to 100 recent questions. GET `/api/threads/:id` includes up to 200 approved replies. POST `/api/threads`, `/api/replies`, `/api/reports` require JSON and X-CSRF-Token. GET/POST `/api/moderation` additionally require an Authorization Bearer moderator key. Pending and removed posts are never publicly retrievable.

## Before public launch

Local development uses Flask's development server. The production entry point uses Gunicorn and refuses incomplete production settings. Configure a hosting proxy with TLS, request/body limits, connection limits and managed process supervision; see pxxl-deployment.md. Configure `ENCLAVE_ORIGIN` to the exact HTTPS public origin, `ENCLAVE_SECURE_COOKIE=1`, a private persistent `ENCLAVE_DB` path, and a moderator secret. `ENCLAVE_HOST` and `PORT` control listening; keep the app unreachable except through the intended proxy. Do not trust arbitrary forwarded address headers; this implementation uses the direct peer address, so behind a proxy the network rate limit is shared unless adapted safely.

Set up encrypted SQLite backups using SQLite's online backup API, test restores, and define retention/deletion procedures. Restrict database and backup access. Add edge abuse protection and review moderation staffing, privacy copy and incident handling before opening to the public. Moderation decisions are recorded in a metadata-only audit table. The current moderator credential is shared; individual moderator accounts and MFA are future work. The new site has not replaced existing production hosting.

## Checks

```sh
node --test tests/site.test.cjs
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Integration tests use isolated temporary databases and local HTTP servers. They cover pending visibility, approval, replies, reports, purging, persistence, filtering, private field exclusion, origin/CSRF enforcement, private asset protection, moderator authentication and write rate limiting.
