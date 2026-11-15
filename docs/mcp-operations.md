# Menclave MCP: implementation and operation

The first-party endpoint is `/mcp` on the same ASGI application as the Menclave website and browser APIs. It uses the official MCP Python SDK 2.3.0, Streamable HTTP, stateless JSON responses, standard protocol negotiation, tools, resources and prompts. Python 3.11 or newer is required.

## Implemented surfaces

The registry defines 116 explicit tools with JSON schemas. By default 107 are enabled; nine depend on external configuration (three SMTP sending tools, five Pxxl deployment tools and webhook creation). Tool discovery is filtered by granted scope. Calling a hidden or disabled tool directly still fails server-side authorization. Capability discovery reports the actual configuration. `outputs/menclave-mcp-tools.json` is a generated inventory, not a substitute for live `tools/list`.

Implemented local services include database-backed articles/interviews/news/pages/newsletter drafts, public rendering, author/category/tag records, revision history, editorial review and scheduling, media upload and image variants, site composition and theme/navigation, SEO metadata and feeds, anonymous community moderation/locks/guidelines/rate limits, consent/suppression, aggregate analytics, jobs, database health/migrations/backups, offline restore preparation, assistant access and auditing.

Updating a published article creates a draft revision while the previous approved snapshot stays public. Publish/unpublish/archive/restore and scheduled publication require an approved change. Content and community text is escaped on public pages and is treated as untrusted data in MCP responses.

## Local startup

```sh
python3.11 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install -r requirements.txt -c requirements.lock.txt
.venv-mcp/bin/python server/app.py
```

Local startup binds to 127.0.0.1:8000 by default. It does not create a public route or an owner password. Set `ENCLAVE_ADMIN_KEY` securely in the process environment before startup to enable owner administration and moderation. Use a strong, unique value of at least 32 characters; never reuse a hosting-provider key. Do not put a real key in the repository, command arguments or assistant chat.

Open `/admin` to sign in, create a scoped assistant token, revoke clients and approve exact change plans. `/admin/editorial` is the owner content studio. `/moderation.html` retains the existing moderator interface. Credentials appear only once when issued; assistant token digests are stored in SQLite. Owner cookies are HttpOnly, SameSite=Strict, one hour, and Secure in production.

An operator can also issue or revoke a client with `python -m server.manage issue-client --name NAME --scopes read editorial:read editorial:write`, or `revoke-client --client-id ID`. Issuance prints a one-time token to that operator's terminal; do not run it in a shared/logged terminal. Prefer the trusted owner UI.

## Connect an assistant

Use a remote MCP endpoint such as `https://your-menclave-domain/mcp`. Two paths are supported:

1. OAuth discovery and authorization-code flow with S256 PKCE. Dynamic client registration accepts exact HTTPS redirect URIs or loopback HTTP callbacks. Owner consent is required; scopes, redirect, resource audience and single-use authorization code are bound together. Tokens expire after one hour. Refresh tokens are not implemented; clients reauthorize when expired.
2. A scoped, expiring personal bearer token created for that assistant. Configure the assistant to send `Authorization: Bearer <assistant-token>`. Exact configuration syntax depends on its MCP client. Grokbot itself has not been tested; the official MCP client has been tested over real HTTP.

Never expose the owner key as the assistant credential. The Pxxl key is an independent deployment credential, held only in server environment variables when the provider adapter is configured.

Resources: `menclave://brand`, `editorial-guidelines`, `community-guidelines`, `content-schema`, `capabilities`, `publishing-calendar`, `operations/runbook`. Each has its own scope check. Prompts cover drafting, interviewing, moderation, newsletter assembly, SEO, weekly metrics and deployment diagnosis.

## Approval and concurrency

All mutating tools require an `idempotency_key`. Reusing it with different arguments fails. Results are persisted transactionally, and content updates require `expected_revision`.

A protected action returns a `plan_id` and proposed arguments instead of immediately taking effect. The owner signs in at `/admin`, inspects the exact plan, and approves or rejects it. The originating assistant then calls `changes_commit`. Newsletter approvals include an audience count and fingerprint; delivery jobs freeze that recipient set and still recheck suppression. A changed audience requires a new approval. Plans expire after 15 minutes, are bound to the originating client, and recheck permissions and current revisions at commit. Assistants cannot approve plans through MCP. Owner-studio plans can be applied through the owner UI after approval.

Assistant calls and moderation decisions produce metadata-only audit records. No anonymous ownership digest, session cookie, subscriber list or provider secret is included in normal tool outputs. Sensitive consent lookups have separate audience scopes. Diagnostics return redacted failures and request IDs.

## Jobs and provider configuration

The ASGI lifespan runs one durable worker every 15 seconds by default. Set `MENCLAVE_WORKER=0` only when running a separate `python -m server.worker` process; never run two workers against the same jobs without coordinated startup recovery. Only one application replica may use this SQLite volume. The embedded and standalone workers share an exclusive worker lock, so a second worker refuses startup. A runtime filesystem lock prevents a second application instance and protects offline restore.

- SMTP: configure `MENCLAVE_SMTP_HOST`, `MENCLAVE_SMTP_PORT` (default 465, TLS), `MENCLAVE_SMTP_FROM`, and, if needed, `MENCLAVE_SMTP_USER`/`MENCLAVE_SMTP_PASSWORD`. Set `MENCLAVE_TEST_RECIPIENTS` to the exact comma-separated test-address allowlist. Public signup queues a confirmation message; no newsletter is sent until the subscriber confirms. Unsubscribe and suppression are checked again immediately before each delivery. Send-test and broadcast use the real provider only when configured. Live SMTP delivery has not been verified in this task.
- Pxxl: configure `MENCLAVE_PXXL_API_KEY`, `MENCLAVE_PXXL_PROJECT_ID`, and `MENCLAVE_PXXL_TOOL_MAP`. The trusted map binds Menclave's five deployment actions to actual Pxxl MCP tool names and parameter fields discovered in your provider connection. Example shape: `{"deployments_list":{"name":"<actual-provider-tool>","project_field":"project_id"}}`. Names must be verified from Pxxl, not guessed. Only the fixed Menclave project is accessible. Mutations are durable jobs. No live Pxxl action was verified because its direct API client was blocked and persistent hosting storage remains unconfigured.
- Webhooks: configure an exact comma-separated `MENCLAVE_WEBHOOK_HOSTS` allowlist and an environment signing secret referenced by each webhook. Only approved HTTPS destinations on port 443 are accepted; public DNS resolution is checked and redirects are refused. Deliveries carry metadata-only events, a unique event ID, and an HMAC SHA-256 signature. Treat allowlisted hosts and their DNS as trusted infrastructure; this is not an arbitrary URL ingestion service.

SMTP and deployment mutations are queued before outbound effects. Ambiguous/interrupted sends become `unknown`/`needs_review` and are not retried automatically. This avoids claiming exactly-once SMTP delivery, which cannot be guaranteed across a crash. Inspect delivery state before creating a new attempt. Worker recovery marks interrupted jobs for review. `jobs_cancel` cancels only queued work.

Analytics record aggregate daily public page requests by path and referring hostname; they are request counts, not unique-human counts. No raw network address, browser fingerprint or visitor cookie is stored for analytics. Historical traffic is not backfilled.

## Backup and restore

`backups_create` creates a private SQLite online backup. It does not copy media files: back up the entire durable volume separately for full disaster recovery and encrypt offsite copies. `backups_verify` checks the database snapshot. These files are never served as public assets.

`backups_restore` requires an approved plan and creates a `waiting_maintenance` job. It never overwrites a live database. Stop the app, then execute `python -m server.manage restore --job-id ID --maintenance`. The command refuses while the application holds its runtime lock, validates the backup, restores using SQLite's backup API, migrates it and revokes all assistant tokens/owner sessions/pending jobs, invalidates pending upload/confirmation links and requires newsletter consent to be reconfirmed to avoid resurrecting old permissions. Restart the app and issue fresh grants afterward. `backups_plan_restore` reports these effects before approval.

## Validation and limits

Run `sh scripts/check.sh` with the isolated environment, or set `PYTHON` to a Python 3.11+ interpreter with requirements installed. Tests cover official SDK interoperability, scoped discovery/execution, OAuth consent/PKCE/resource binding/replay, owner CSRF and revocation, idempotency, stale-plan rejection, public snapshots, media bytes, moderation/privacy/locking, newsletter confirmation/unsubscribe/suppression, interrupted SMTP sends, scheduling, backup integrity and restore interlocks.

Deployment still requires durable Pxxl storage and runtime secrets. No external newsletter provider, production Pxxl action, Grokbot client or public deployment was verified. Granular scopes are implemented; per-record ACLs, distinct human administrator accounts/MFA, refresh tokens and external secret-manager synchronization are not implemented. Configuration/secret changes require a server restart.


The owner studio provides private rendered draft previews at `/admin/preview/<content-id>`. MCP preview tools return escaped preview HTML and that owner-only path; draft content is never made public merely to preview it.
