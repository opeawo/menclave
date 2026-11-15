# Pxxl deployment

Status: prepared, not deployed. GitHub is connected in Pxxl. The dashboard currently shows the Free plan with database and storage access locked; a durable volume or a supported external database must be arranged before accepting public community posts. Do not run this SQLite configuration on an ephemeral app filesystem.

## Deployment configuration

Use a GitHub import for `opeawo/menclave`. The tracked `pxxl.toml` sets Python 3.12, dependency installation, compilation and Gunicorn startup on port 8000. The optional Dockerfile is under `deploy/` so Pxxl does not automatically choose Docker for a normal GitHub import.

Configure a persistent volume at `/data`, readable/writable by the runtime user, and run exactly one replica. SQLite WAL requires a local filesystem with locking; do not mount object storage or an arbitrary network filesystem. The backend uses one worker with four threads. The database schema migrates on startup without dropping existing tables.

Set runtime environment variables in the Pxxl dashboard:

| Variable | Value |
| --- | --- |
| `ENCLAVE_ENV` | `production` (also enforced by the WSGI entry point default) |
| `ENCLAVE_ORIGIN` | Exact HTTPS origin of the project, without a path |
| `ENCLAVE_DB` | `/data/enclave.sqlite3` |
| `ENCLAVE_ADMIN_KEY` | Strong private value of at least 32 characters, generated and stored outside the repository |
| `ENCLAVE_SECURE_COOKIE` | `1` |
| `PORT` | `8000` |

The WSGI application refuses production startup without the HTTPS origin, moderator key and explicit absolute database path. Set the HTTP health check to `/api/health`. The planned domain shown in the current dashboard is `https://menclave.pxxlspace.cv`; it is not yet a deployed URL or confirmed domain assignment.

Run migrations locally with `.venv/bin/python -m server.manage migrate`; check storage with `.venv/bin/python -m server.manage check`. Back up using `.venv/bin/python -m server.manage backup --output /private/backup/location/enclave.sqlite3`. The backup command refuses to overwrite files and uses SQLite's online backup API. Encrypt backups and arrange retention outside this application. For restore, stop writes, validate a backup separately, replace the database while stopped, then restart and verify approved post counts and moderation access. Do not overwrite a running WAL database.

Production startup does not automatically generate or display administrator credentials. The Pxxl key authenticates deployment operations only; it must never be reused as Menclave's moderator key or a future Menclave MCP token.

## Verification after deployment

1. `/api/health` returns `{"status":"ok"}` over HTTPS.
2. Session cookies include Secure, HttpOnly and SameSite=Strict.
3. A question remains pending and invisible until approved through `/moderation.html`.
4. Approved replies appear; reports enter the queue; removed text is hidden.
5. A restart/redeploy retains approved posts and schema version.
6. Backup/restore is tested against an isolated environment.

## Platform references

- https://docs.pxxl.app/reference/pxxl-toml
- https://docs.pxxl.app/deploy/environment-variables

The direct MCP connection was blocked by Cloudflare before authentication completed. No Pxxl key is stored in the repository. The normal dashboard was accessible. No upgrade, purchase, domain change or production replacement has been performed.
