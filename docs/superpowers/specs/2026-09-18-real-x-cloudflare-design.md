# Real X Analytics and Cloudflare Production Design

## Scope

Upgrade the existing Python Discord analytics bot without rebuilding it from scratch. The local Python gateway bot remains useful for development and small self-hosted runs. Production is prepared as a Cloudflare-native TypeScript Worker using Discord HTTP interactions, D1, Cron Triggers, and Cloudflare secrets.

## Local Python Architecture

The existing provider/repository/service layers stay in place. The real X provider becomes a robust public X API client with pagination, rate-limit metadata, request retry/backoff for transient failures, malformed-response errors, richer account/post fields, and no secret logging. Tracking performs an initial backfill: resolve the account, save the first account snapshot, paginate recent posts within configured limits, save posts, and save real metric snapshots.

The database keeps historical snapshots as the source of truth for period growth. Migrations add only fields needed for real API data quality: profile image URL, account creation time, verified type, provider metadata, post type/referenced tweet metadata, conversation ID, language, possibly-sensitive flag, and collection status rows.

Analytics clearly separates:

- metric growth during a period, calculated from stored snapshots;
- current cumulative performance of posts created during a period, using latest stored/current metrics.

Missing metric values remain `NULL`/`None`, never zero. Partial historical coverage is displayed explicitly.

## Cloudflare Production Architecture

Production uses a TypeScript Cloudflare Worker rather than a persistent Discord Gateway connection.

Discord slash command:

1. Discord sends an HTTP interaction to the Worker.
2. Worker validates Ed25519 signature using `DISCORD_APPLICATION_PUBLIC_KEY`.
3. Worker handles PING verification and slash commands.
4. Worker reads/writes D1 and calls the official X API.
5. Longer operations use deferred interaction responses and followups.

Background collection:

1. Cloudflare Cron Trigger invokes the Worker scheduled handler.
2. Worker finds tracked accounts requiring refresh.
3. Worker calls X API with configured safety limits.
4. Worker writes D1 snapshots and collection status.

D1 schema mirrors local SQLite semantics, but D1 migrations are plain SQL managed through Wrangler. No Cliproom resources are reused.

## Secrets

Local development uses `.env`, which is gitignored. Production uses Cloudflare secrets:

- `X_BEARER_TOKEN`
- `DISCORD_APPLICATION_PUBLIC_KEY`
- `DISCORD_APPLICATION_ID`
- `DISCORD_BOT_TOKEN` only if needed for command registration/followups.

Secrets are never written to source, docs, Wrangler config, or logs.

## Deployment

The repo includes Wrangler config and D1 migrations. Deployment requires a separate Cloudflare account, new D1 database, secrets, and Discord Interactions Endpoint URL configuration. Production must continue running when the local PC is off.

