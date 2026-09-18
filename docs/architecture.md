# Architecture Plan

## Goal

Build a maintainable Discord bot base that tracks X/Twitter accounts, stores historical snapshots, and exposes early Discord commands without coupling Discord, analytics, and X API details together.

## Approach

The system uses a provider abstraction named `XAnalyticsProvider`. The rest of the application asks for account info and recent posts through that interface, so the real X API provider can be replaced later by another official provider, a richer owned-account provider, or a test double.

The local application remains a Python `discord.py` gateway bot for development and
small local runs. Production is prepared separately as a TypeScript Cloudflare Worker
under `worker/`. The Worker uses Discord HTTP Interactions instead of a persistent
Gateway connection, Cloudflare D1 instead of local SQLite, and Cron Triggers instead
of an always-running Python scheduler.

The data model separates mostly static records from time-series snapshots:

- `TrackedAccount` stores stable identity by X user ID.
- `AccountSnapshot` stores account-level counters at collection time.
- `Post` stores one row per X post.
- `PostMetricSnapshot` stores cumulative metrics for each post over time.

Analytics are calculated from deltas between snapshots. The service refuses to return period metrics when a required baseline is missing, which prevents retroactive data fabrication.

Analytics also reports "current performance of posts published during the period."
That is explicitly separate from "metrics gained during the period."

## Data Flow

1. A Discord administrator runs `/track`.
2. The tracking service validates the username and resolves it through the provider.
3. The account is stored by X user ID, so username changes update the same row.
4. The scheduler periodically asks the collector for active accounts.
5. The collector refreshes account details, fetches recent posts, upserts static post records, and writes metric snapshots.
6. Discord analytics commands read from the database and calculate period deltas.

## Production Data Flow

1. Discord sends an HTTP interaction to the Worker.
2. The Worker verifies `X-Signature-Ed25519` and `X-Signature-Timestamp`.
3. The Worker handles commands against D1 and the official X API.
4. Cloudflare Cron periodically invokes the scheduled handler.
5. Scheduled collection refreshes tracked accounts and writes D1 snapshots.

## Error Handling

Collection is per-account isolated. One provider failure rolls back that account's collection attempt and logs the issue, but the collector continues with the next account.

The X API provider handles timeouts, server retries, authentication failures, not-found responses, and rate limits with structured exceptions. Secrets are never logged.

The Worker follows the same safety rules: no secret logging, no scraping, no global
request state, D1 bindings instead of Cloudflare REST calls, and structured logs.

## Security

Secrets live in environment variables only. The bot validates X usernames, uses SQLAlchemy parameterized queries, avoids scraping and cookies, and restricts account-management commands to Discord administrators or configured user/role IDs.

## Testing

The test suite covers:

- username validation;
- stable account identity across username changes;
- idempotent account and post snapshots;
- period analytics from snapshot deltas;
- posts created inside a period;
- refusal to fake metrics without baseline snapshots;
- missing metrics;
- per-account collection failure isolation.
