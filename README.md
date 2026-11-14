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
- Anonymous community teaser, not the production community
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
- `/enclave` existing anonymous discussion experience
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