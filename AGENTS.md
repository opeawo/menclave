# Codex instructions: Menclave

## Mission
Build **Menclave, the GQ for men of faith**, combining premium men's magazine editorial design with a spiritual worldview and an existing anonymous men's discussion community.

## Visual system
- Art direction: high-end men's magazine, bold photography and sophisticated typography, NOT a SaaS dashboard or conventional church template.
- Ink black `#121212`, warm paper `#f4f0e9`, oxblood `#a32e2b`, dark charcoal.
- Headlines: Barlow Condensed 700-900. Body: Instrument Sans. Editorial prose and pull quotes: Libre Baskerville.
- Mobile-first. Keep hero photography cinematic and Q&A pages single-column on mobile.
- Use CSS Grid/Flexbox, semantic HTML, accessible markup. Keep page fast and avoid unnecessary dependencies.

## Editorial sections
Faith & Purpose; Relationships & Family; Money & Ambition; Health & Fitness; Style & Living; Culture & Society; Men's Stories.

## Community
- Existing anonymous Q&A/comment functionality must be preserved, not rebuilt blindly.
- Do not link public content to an identifying user account or expose identifying metadata.
- Implement moderation, abuse reporting, rate limiting and clear user safety notices when community integration occurs.

## Content / integrity
- Placeholder interviews, quotes and story summaries must be marked demonstrably fictional or editorial concept until real content is approved.
- Never fake subscriber confirmations, published news, authors, usage statistics or discussion counts.
- Do not copy other magazines' design assets or copyrighted articles.
- Do not claim the anonymous community or newsletter is integrated until it actually works.

## Workflow
- Inspect the existing project before changing architecture.
- Keep small, reviewable commits; maintain a working page at each step.
- Test accessibility, keyboard navigation, mobile breakpoints, contrast and image fallback.
- No production site replacement, destructive migrations, or secret commits without explicit approval.
