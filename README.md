# Menclave

**The Art of Being a Man.** A premium editorial publication for men of faith: life, purpose, relationships, ambition, health, style, and brotherhood.

## Run locally

This is a zero-build HTML/CSS/JavaScript prototype. Open `index.html`, or serve the repository:

```sh
python3 -m http.server 8000
```

Visit http://localhost:8000. The featured interview template is at `/interview.html`.

## Status

- Responsive magazine homepage
- Mobile navigation and category rail
- Feature-interview page template
- Standalone anonymous community with persistent SQLite storage and moderation; local development only
- Newsletter interface, not yet attached to a mailing service
- Editorial copy and interviewees are clearly labeled **concept/demo content**
- Photography references external Unsplash images for prototyping, replace with approved licensed images for launch

**Do not deploy this over the current Menclave site or modify its production database until the existing app and its anonymous Q&A data have been audited.**

## Planned information architecture

- `/` home
- `/magazine` editorial archive
- `/magazine/[slug]` articles and interviews
- `/magazine/category/[slug]` categories
- `/news` curated news
- `/enclave.html` fresh standalone discussion experience
- `/newsletter` newsletter archive and subscription

## Build next

1. Audit the current Menclave production application, hosting, auth, anonymous question and comment storage, permissions, and route structure.
2. Choose the existing application stack or a justified new stack. Preserve data and legacy URLs.
3. Build reusable magazine modules and CMS-managed articles, authors, sections, interviews, media, drafts, and preview.
4. Wire the real community to the new site, with privacy-safe anonymous identity handling and moderation.
5. Add verified newsletter double opt-in, unsubscribes, transactional state, and privacy disclosure.
6. Add tests, CI, analytics, SEO, accessibility, performance budgets and production deployment workflow.

## Design

Black/cream editorial palette, oxblood accents, condensed display type and serif body copy. The design brief is in `AGENTS.md`. Avoid a generic blog template.

## Editorial content foundation

`content/stories.json` is the source for the magazine archive and eight concept story pages.
Edit the title, category, deck, image, alt text and sections, then run:

```sh
node scripts/build.mjs
node --test tests/site.test.cjs
```

Commit the generated HTML alongside the content. CI checks that generated pages are current.
The magazine archive supports search, category filters and shareable filter URLs; without JavaScript all stories remain accessible. Homepage and interview HTML remain hand-authored.

This is a file-based content foundation, not an integrated CMS or editorial admin. Before selecting a hosted CMS or connecting the community, audit the existing production application and its data contracts. Newsletter submission still stores nothing.


## Run The Enclave

Use `python3 server/app.py` instead of the static server to enable anonymous questions, replies, reports, topic browsing and moderation. Open `/enclave.html`. New posts await approval; the fresh database starts empty. Set `ENCLAVE_ADMIN_KEY` in the server environment before using `/moderation.html`. The current preview has moderation disabled until a key is configured.

See [community operation and hosting requirements](docs/enclave.md). No legacy community data is migrated. This implementation is local and has not been publicly deployed.


## Deployable backend

Install dependencies in a virtual environment with `python3 -m venv .venv` and `.venv/bin/pip install -r requirements.txt`. Start local development with `.venv/bin/python server/app.py`. Production uses Flask behind Gunicorn through `server.wsgi:app`, with versioned SQLite migrations, an anonymous community API, private moderation, metadata-only moderation audit records, health checks and backup/integrity commands.

See [Pxxl deployment configuration](docs/pxxl-deployment.md). Hosting and persistent storage still require configuration in Pxxl.
