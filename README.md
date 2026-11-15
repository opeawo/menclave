# Menclave

**The Art of Being a Man.** An editorial publication and anonymous community for men of faith, with a first-party MCP management endpoint.

## Run locally

Python 3.11+ is required. Use an isolated environment:

```sh
python3.11 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install -r requirements.txt -c requirements.lock.txt
.venv-mcp/bin/python server/app.py
```

The server defaults to `http://127.0.0.1:8000`. Magazine HTML can still be viewed with a static server, but the CMS, community, administration and MCP require this ASGI server.

| Path | Purpose |
| --- | --- |
| `/` | Magazine homepage |
| `/magazine` | Database-backed publication archive |
| `/magazine/<slug>` | Published editorial content |
| `/enclave.html` | Anonymous community |
| `/admin` | Trusted owner login, assistant grants and approvals |
| `/admin/editorial` | Editorial studio |
| `/moderation.html` | Community moderation |
| `/mcp` | Authenticated MCP Streamable HTTP endpoint |
| `/api/health` | Backend readiness |
| `/sitemap.xml`, `/feed.xml` | Published content distribution |

Set a strong, unique `ENCLAVE_ADMIN_KEY` securely in the process environment before startup to enable owner access. Do not reuse a hosting key or commit secrets. Connect each assistant with its own scoped token or OAuth grant, never the owner key.

## What is implemented

- Responsive magazine design; CMS-managed content with revisions, draft/public snapshots, review and scheduling.
- Anonymous questions/replies, approval queues, reports, thread locks, staff-labeled prompts and editable guidelines/abuse limits.
- Media upload and transformations, branding/navigation/homepage settings, author/category/tag records, redirects and SEO/feed generation.
- Official MCP SDK endpoint: 116 explicit tool definitions, scope-enforced discovery/execution, resources and prompts. Provider-dependent tools stay hidden until configured.
- OAuth authorization code with S256 PKCE and owner consent; expiring personal assistant tokens, revocation, owner CSRF sessions and metadata-only auditing.
- Durable jobs and exact-change approvals, optimistic concurrency and idempotent writes.
- Real SMTP outbox adapter with double opt-in, consent, suppression, unsubscribe and ambiguous-delivery handling; owner-allowlisted test recipients.
- Aggregate page-request analytics, signed allowlisted webhook adapter and Menclave-scoped Pxxl MCP adapter.
- Versioned SQLite migrations, private backups, integrity checks and offline restore with runtime/worker interlocks and grant invalidation.

External SMTP, Pxxl deployment and webhook delivery need provider configuration; no live external delivery or deployment is claimed. The local database starts with clearly labeled editorial concept stories and no fabricated community activity. Photography uses external Unsplash references and should be reviewed for launch.

## Verification

```sh
sh scripts/check.sh
```

The checks include official MCP client interoperability over real HTTP, authorization boundaries, publishing/approval/concurrency, media bytes, moderation/privacy, subscriptions and delivery retry safety, scheduling, backup integrity and offline restore. SMTP is mocked in tests; real provider delivery is a separate launch check.

## Operation and deployment

- [MCP setup, permissions and provider configuration](docs/mcp-operations.md)
- [Pxxl deployment requirements](docs/pxxl-deployment.md)
- [Community operation](docs/enclave.md)
- [Original capability plan](docs/mcp-plan.md)

Production runs `uvicorn server.asgi:app --host 0.0.0.0 --port 8000 --no-access-log --log-level warning`. `pxxl.toml` contains the GitHub deployment configuration; `deploy/Dockerfile` is an optional container build. Production refuses to start without an HTTPS origin, a strong owner key and an explicit database path.

A durable volume is mandatory. Keep one app replica and one worker with SQLite; media/backups default alongside the database. Never put community data on an ephemeral app filesystem. The existing Menclave production site has not been replaced, and no legacy service data is imported.
