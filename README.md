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
| `/conversations` | Server-rendered anonymous conversation feed |
| `/conversations/<id>` | Permanent conversation and approved replies |
| `/enclave.html` | Compatible feed URL; old `?thread=` links redirect |
| `/admin` | Trusted owner login, assistant grants and approvals |
| `/admin/editorial` | Editorial studio |
| `/moderation.html` | Community moderation |
| `/mcp` | Authenticated MCP Streamable HTTP endpoint |
| `/api/health` | Backend readiness |
| `/sitemap.xml`, `/feed.xml` | Published content distribution |

Set a strong, unique `ENCLAVE_ADMIN_KEY` securely in the process environment before startup to enable owner access. Do not reuse a hosting key or commit secrets. Connect each assistant with its own scoped token or OAuth grant, never the owner key.

## What is implemented

- Shared header search across published articles and approved community conversations; inline social-style anonymous posting.
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

## Editorial format samples

The ten magazine samples cover interviews, checklists, photo stories (one to three inline images), how-to steps, personal essays, video, image galleries, discussion-led articles, researched profiles and opinion. `content/stories.json` is the sample source; `node scripts/build.mjs` rebuilds static pages. Python 3 is also used by that build for the shared, escaping block renderer. Runtime pages, owner previews, search and MCP all use the same block model; legacy heading/body sections remain supported.

Use `content_create_draft` / `content_update` with `data.format`, `data.blocks` and optional `data.hero_layout`. The `menclave://content-schema` MCP resource includes the block schema and available formats. Blocks contain plain text, never arbitrary HTML. Image/video URLs are restricted to approved hosts or local assets. Available hero layouts: `overlay-left`, `overlay-center`, `overlay-right`, `overlay-bottom`, `split`. Placement is an editorial setting; there is no automatic AI image analysis service configured. Lawal and Huang use split covers, stacked on mobile.

The example conversations are visibly labelled samples and closed to new replies. Set `MENCLAVE_SAMPLE_THREADS=0` before first startup to skip seeding them. They are excluded from the sitemap and marked noindex. Real approved conversations have canonical URLs, server-rendered posts/replies, descriptions, Open Graph metadata and DiscussionForumPosting structured data. Pending/removed posts are never rendered. Search and story conversation blocks point to the permanent pages; legacy thread URLs redirect. Backend hosting is required for conversation pages.

Bootstrap upgrades only untouched sample articles whose latest revision was created by bootstrap. Human edits and moderation actions are preserved. Migration 008 adds the sample flag without changing existing posts.

### Media and research credits

- Ibidapo Lawal portrait: supplied by the project owner. Profile references appear at the end of the story: Neveah’s company biography, The Guardian’s 14 October 2024 profile and Opeyemi Awoyemi’s public LinkedIn account. The draft attributes the bankruptcy account and does not assert four formal bankruptcies.
- Jensen Huang portrait: official NVIDIA newsroom press headshot, downloaded from its biography page. The article links NVIDIA’s 8 November 2026 message, 12 November transition announcement, biography and the referenced WSJ analysis. It is presented as Menclave opinion.
- Landscape/interior/style photographs: illustrative Unsplash images, credited in captions where they occur; they do not represent people or locations in the fictional stories.
- Video-player fixture: MDN’s flower clip at `https://mdn.github.io/shared-assets/videos/flower.mp4`; replace it with the finished editorial film for launch. Native controls, no autoplay, and an accessible description are included.

Run `sh scripts/check.sh` for JavaScript syntax, static integrity and Python integration checks. Browser verification covers mobile/desktop portraits, permanent thread navigation, gallery arrows/Escape, checkboxes and native video playback.
