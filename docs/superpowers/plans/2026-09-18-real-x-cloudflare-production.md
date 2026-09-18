# Real X Cloudflare Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing bot into a real-X analytics foundation and prepare a Cloudflare-native production deployment path.

**Architecture:** Preserve the Python local gateway bot and enhance its provider, collection, analytics, and Discord UX. Add a TypeScript Cloudflare Worker production target using Discord HTTP interactions, D1, Cron Triggers, and Cloudflare secrets.

**Tech Stack:** Python 3.12+, discord.py, SQLAlchemy, Alembic, pytest, httpx, TypeScript, Cloudflare Workers, D1, Wrangler, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-18-real-x-cloudflare-design.md`

## Global Constraints

- Never commit `.env`, tokens, cookies, credentials, or database files.
- Use official X API only; no scraping or browser-cookie fallback.
- Preserve historical snapshots and never fabricate unavailable history.
- Keep immutable X user IDs and X post IDs as identity keys.
- Local dev remains SQLite/Python; production uses Cloudflare Worker/D1.
- Production Cloudflare resources are separate from Cliproom.

---

### Task 1: Configuration and Types

**Files:**
- Modify: `bot/config/settings.py`
- Modify: `bot/providers/types.py`
- Modify: `.env.example`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces settings for backfill, X request timeout/retries/concurrency, snapshot policy, and Discord IDs.
- Produces richer `XAccount`, `XPost`, `XPostMetrics`, and rate-limit metadata dataclasses.

- [ ] Write tests for blank, JSON-list, comma-separated, and invalid Discord ID settings.
- [ ] Add config fields with safe defaults.
- [ ] Extend provider dataclasses without breaking existing tests.
- [ ] Run targeted tests and then full suite.

### Task 2: Robust X API Provider

**Files:**
- Modify: `bot/providers/base.py`
- Modify: `bot/providers/x_api.py`
- Modify: `bot/providers/mock.py`
- Test: `tests/test_x_api_provider.py`

**Interfaces:**
- Produces `get_account_by_username`, `get_recent_posts`, `get_posts_window`, rate-limit metadata, robust exceptions.

- [ ] Expand tests for pagination, 401, 403, 404, 429, 500 retry, timeout, malformed JSON, malformed payloads, and rate-limit headers.
- [ ] Implement request abstraction with retry/backoff/jitter and safe logging.
- [ ] Implement timeline pagination with date/window and max-post stopping rules.
- [ ] Parse public user/post/media metrics without adding media views to post impressions.
- [ ] Run targeted X provider tests.

### Task 3: Database and Repositories

**Files:**
- Modify: `bot/database/models.py`
- Modify: `bot/repositories/accounts.py`
- Modify: `bot/repositories/posts.py`
- Add: `alembic/versions/20260918_0002_real_x_metadata.py`
- Test: `tests/test_repositories.py`

**Interfaces:**
- Produces storage for richer account/post metadata and collection status.

- [ ] Write repository tests for profile metadata, post type/reference metadata, latest snapshot lookup, and skip-unchanged snapshot policy.
- [ ] Add SQLAlchemy columns/indexes and Alembic migration.
- [ ] Update repositories to persist real metadata and optionally skip unchanged snapshots.
- [ ] Smoke-test Alembic against SQLite.

### Task 4: Backfill and Collection

**Files:**
- Modify: `bot/services/tracking.py`
- Modify: `bot/tasks/collector.py`
- Modify: `bot/tasks/scheduler.py`
- Test: `tests/test_tracking.py`
- Test: `tests/test_collector.py`

**Interfaces:**
- Produces `track()` result with imported post/snapshot counts and `collect_account()` stats.

- [ ] Write tests for initial backfill, no tracked accounts, username changes, duplicate prevention, one-account isolation, and collection lock.
- [ ] Implement initial backfill with configured days/max posts.
- [ ] Implement single-account refresh and whole-cycle concurrency protection.
- [ ] Store collection status without aborting historical data.

### Task 5: Analytics

**Files:**
- Modify: `bot/analytics/service.py`
- Modify: `bot/analytics/periods.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces period coverage, metric growth, current posts-created-in-period performance, top posts, and human-readable availability reasons.

- [ ] Add tests for exact/partial coverage, old-post period gains, posts-created current totals, missing fields, metric decreases, top posts, zero posts, and timezone boundaries.
- [ ] Implement reusable coverage and metric delta helpers.
- [ ] Implement top-post ranking and current period-content performance.

### Task 6: Local Discord Commands

**Files:**
- Modify: `bot/discord_app/commands.py`
- Add: `bot/discord_app/formatting.py`
- Test: `tests/test_discord_formatting.py`

**Interfaces:**
- Produces polished embed builders and adds `/refresh` and `/collectnow`.

- [ ] Write formatting tests for compact numbers, coverage labels, embed-safe previews, and permission-sensitive command paths.
- [ ] Improve `/track`, `/twitter`, `/analytics`, `/status`.
- [ ] Add `/refresh` and `/collectnow` with management permissions and no overlapping runs.

### Task 7: Cloudflare Worker Production Target

**Files:**
- Add: `worker/package.json`
- Add: `worker/tsconfig.json`
- Add: `worker/vitest.config.ts`
- Add: `worker/wrangler.jsonc`
- Add: `worker/src/index.ts`
- Add: `worker/src/discord.ts`
- Add: `worker/src/x-api.ts`
- Add: `worker/src/db.ts`
- Add: `worker/src/analytics.ts`
- Add: `worker/src/commands.ts`
- Add: `worker/migrations/0001_initial.sql`
- Test: `worker/test/*.test.ts`

**Interfaces:**
- Produces Discord HTTP interaction endpoint, D1 schema, scheduled collector, and production command handlers.

- [ ] Write Vitest tests for signature verification, PING, command routing, analytics helpers, X parsing, and scheduled collection units.
- [ ] Implement Worker with strict TypeScript and generated Env bindings.
- [ ] Configure Wrangler D1 binding, Cron Trigger, observability, and non-secret vars.
- [ ] Validate with `npm test`, `npm run typecheck`, and `wrangler deploy --dry-run` when possible.

### Task 8: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/x-api-capabilities.md`
- Add: `docs/cloudflare-deployment.md`

**Interfaces:**
- Produces setup, restart, Cloudflare deployment, D1 migration, secrets, and limitation docs.

- [ ] Update public/owned/historical capability matrix.
- [ ] Document local vs production architecture and operational commands.
- [ ] Run Python tests/lint/migrations.
- [ ] Run Worker tests/typecheck/config validation.
- [ ] Report anything blocked by missing real secrets or Cloudflare account interaction.

