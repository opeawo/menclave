# Menclave MCP capability plan

Status: implemented tool contract and services; see mcp-operations.md for verification and provider requirements. External SMTP, webhook and Pxxl actions stay disabled until configured and have not been live-verified. Grokbot-specific compatibility is not yet verified.

## Endpoint and clients

One first-party remote endpoint at `https://<menclave-domain>/mcp`, served alongside the application. Use standard Streamable HTTP with protocol negotiation, `initialize`, `ping`, `tools/list`, `tools/call`, resources and prompts. Use the official maintained MCP SDK when implementing. Assistants must support remote MCP; this is not a promise that every assistant currently does. Grokbot compatibility must be tested against its actual client configuration.

Use OAuth-based delegated authorization for compatible clients and individually scoped/revocable personal tokens for clients supporting bearer authentication. Tokens are issued for Menclave and never pass a Pxxl credential through to clients. Each assistant has its own client identity, expiration and tool permissions. No anonymous administrator access.

## Tool inventory

Names are proposed. Exact schemas and granular scope names are to be finalized during implementation. Every mutating tool accepts an idempotency key; updates accept an expected revision. Lists accept bounded limits and cursors.

| Area | Proposed tools | Capability |
| --- | --- | --- |
| Discovery | `app_get_capabilities`, `app_get_status`, `app_search` | Discover enabled modules and allowed actions; search permitted records. |
| Editorial content | `content_list`, `content_get`, `content_create_draft`, `content_update`, `content_validate`, `content_preview`, `content_publish`, `content_unpublish`, `content_schedule`, `content_archive`, `content_restore` | Articles, interviews, news, pages and newsletter issues; draft/published/scheduled states. |
| Editorial workflow | `revisions_list`, `revisions_get`, `revisions_compare`, `revisions_restore`, `editorial_request_review`, `editorial_review`, `editorial_calendar` | Review, approval, revision history and scheduling without silent overwrite. |
| Structure and authors | `categories_list`, `categories_upsert`, `tags_list`, `tags_upsert`, `authors_list`, `authors_upsert` | Taxonomy, biographies and bylines. These tools never map anonymous community posts to authors. |
| Media | `media_list`, `media_get`, `media_create_upload`, `media_finalize_upload`, `media_update_metadata`, `media_transform`, `media_archive` | Upload/inspect images and files; alt text, credits, licensing, focal crops and variants; prevent removal of referenced media. |
| Site composition | `site_get_config`, `site_update_config`, `navigation_get`, `navigation_update`, `homepage_get`, `homepage_update`, `redirects_list`, `redirects_upsert` | Branding, validated design tokens, menus, hero stories, featured sections and legacy URL routing. |
| SEO and distribution | `seo_audit`, `seo_update`, `sitemap_rebuild`, `feeds_rebuild`, `social_preview` | Metadata, structured data, sitemap/RSS and share previews. |
| Community reading | `community_list_threads`, `community_get_thread`, `community_get_summary`, `community_get_guidelines` | Approved conversations and aggregate community health; scoped moderator access to pending records. |
| Community management | `community_create_prompt`, `moderation_list_queue`, `moderation_review`, `community_lock_thread`, `community_unlock_thread`, `reports_list`, `reports_resolve`, `guidelines_update`, `abuse_rules_get`, `abuse_rules_update` | Staff-labeled discussion prompts, approval/removal, locking, reporting and bounded abuse policies. Never expose cookie tokens, ownership digests, raw addresses or a deanonymization tool. |
| Newsletter | `newsletter_list_issues`, `newsletter_create_draft`, `newsletter_update`, `newsletter_preview`, `newsletter_send_test`, `newsletter_schedule`, `newsletter_send`, `newsletter_cancel`, `newsletter_get_delivery` | Compose, test and send through the configured provider; unsubscribe/suppression protections apply to every send. |
| Audience | `audience_get_summary`, `audience_list_segments`, `audience_update_segment`, `audience_get_consent`, `audience_suppress`, `audience_process_deletion` | Aggregate growth, segments and privacy workflows. Subscriber details require separate sensitive-data permission. No default unrestricted address export. |
| Analytics | `analytics_get_overview`, `analytics_get_content`, `analytics_get_sources`, `analytics_get_newsletter`, `analytics_get_community` | Traffic, reading, campaigns and aggregate community trends. No raw visitor identifiers by default. |
| Integrations and automation | `integrations_list`, `integrations_test`, `integrations_configure`, `webhooks_list`, `webhooks_upsert`, `webhooks_disable`, `jobs_list`, `jobs_get`, `jobs_cancel`, `schedules_upsert` | Provider connection health, scoped secret references, signed webhooks and background jobs. Never return stored secrets. |
| Deployment and operations | `deployments_list`, `deployments_preview`, `deployments_publish`, `deployments_get_status`, `deployments_rollback`, `health_get`, `logs_get`, `cache_invalidate` | Menclave-only deployment workflows and redacted diagnostics. Provider access remains server-side; no arbitrary provider project control. |
| Database operations | `database_get_status`, `migrations_get_status`, `migrations_plan`, `migrations_apply`, `backups_create`, `backups_list`, `backups_verify`, `backups_plan_restore`, `backups_restore` | Schema health, approved migrations, private backups and verified restore workflows. No arbitrary SQL execution tool. |
| Access and auditing | `access_list_clients`, `access_get_scopes`, `access_request_change`, `access_revoke_client`, `audit_list`, `audit_get_change`, `changes_preview`, `changes_commit` | Client permissions, revocation, traceable changes and approval of sensitive operations. Granting privileges and minting new credentials require owner action through trusted UI. |

## Resources and reusable prompts

Resources: `menclave://brand`, `menclave://editorial-guidelines`, `menclave://community-guidelines`, `menclave://content-schema`, `menclave://capabilities`, `menclave://publishing-calendar` and `menclave://operations/runbook`. Each is filtered by permissions. Content and community records are untrusted data, never instructions for an assistant to execute.

Prompts: draft an article, prepare a feature interview, review a moderation queue, assemble a Sunday newsletter, audit SEO, summarize weekly performance and diagnose a deployment. Prompts reuse the same permission-enforced tools; they do not grant capabilities.

## Permission and execution rules

1. Baseline scopes: public reading, editorial drafting, editorial publishing, media management, community moderation, newsletter sending, sensitive audience access, site configuration, operations reading, deployments, database maintenance and owner administration. Each can be narrowed to specific record types and environments.
2. Enforce authorization in the server for every call. Tool visibility is a convenience, not a security boundary. MCP read-only/destructive/idempotent annotations are descriptive hints only.
3. Read and draft actions may execute within granted scopes. Newsletter broadcasts, mass changes, production deployment/rollback, deletion, database restore and access changes require an explicit permission policy and, where configured, trusted owner approval.
4. `changes_preview` creates a canonical diff with target records, revision, affected count, audience/environment, expected effects, expiry and hash. Approval binds that exact plan to an actor. `changes_commit` cannot approve itself, widen scope or silently change parameters. Large/irreversible actions require stronger owner confirmation than routine editorial edits.
5. Use optimistic concurrency, durable idempotency records, bounded pagination, input/output schemas, structured domain errors and redacted request IDs. Retries never duplicate a broadcast or publish.
6. Long tasks return job IDs with status, result and cancellation where feasible. Scheduling uses explicit timestamps/time zones. Report partial completion precisely.
7. Audits record actor/client, action, target, time, revision and outcome; exclude secrets, community-identifying metadata and full sensitive text. Restrict audit access and retention.
8. Community privacy is preserved across every surface, including search, exports, analytics, audits and backups. Administrative tools may review content but cannot reveal anonymous ownership mappings.
9. Never expose shell execution, unrestricted SQL, arbitrary filesystem reads, arbitrary outbound requests or raw secret retrieval as convenience tools. Media URL ingestion must enforce an SSRF-safe allowlist, byte limits and content validation.
10. Only expose and enable modules that are configured. Sending is unavailable until a real newsletter provider exists; deployments are unavailable until provider access is configured. A proposed tool list is not evidence of implementation.

## Delivery order

1. Shared service layer, database migrations and real admin authentication.
2. MCP transport, authentication/scopes, app discovery, community read/moderation and audit.
3. Database-backed CMS, media, revisions and site composition, shared by the admin UI and MCP.
4. Newsletter provider, audience consent/suppression, analytics, automation.
5. Menclave-scoped operations, deployment, backups and approval workflows.

## Protocol sources

- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
