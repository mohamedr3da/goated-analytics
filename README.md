# X/Twitter Analytics Discord Bot

Production-quality foundation for a Discord bot that tracks X/Twitter accounts, stores historical snapshots, and calculates analytics from observed metric deltas.

The important design choice is that the bot never fabricates unavailable history. Public X metrics are cumulative point-in-time values, so period analytics become reliable only after the collector has captured snapshots before and after the requested period.

## Architecture

- `bot/discord_app`: Discord slash commands and embeds.
- `bot/services`: business workflows such as tracking and summaries.
- `bot/tasks`: scheduled collection.
- `bot/providers`: `XAnalyticsProvider` abstraction, real X API provider, and mock provider.
- `bot/repositories`: async SQLAlchemy data access.
- `bot/database`: models and session setup.
- `bot/analytics`: snapshot delta calculations.
- `docs`: architecture and current X API capability notes.
- `tests`: unit tests with mocked providers and in-memory SQLite.

The Discord layer depends on services, services depend on repositories and the provider interface, and only the provider implementation knows X API details.

## Current Features

- `/track <username>`: add or re-enable a tracked X account.
- `/untrack <username>`: disable tracking without deleting history.
- `/tracked`: list active tracked accounts.
- `/twitter <username>`: show current stored account summary.
- `/analytics <username> <period>`: scaffolded period analytics for `24h`, `1d`, `7d`, and `30d`.
- `/status`: check database, scheduler, and provider health.
- Background collection of account snapshots, recent posts, and post metric snapshots.
- Mock provider for local development without X API credentials.
- Async SQLAlchemy models with SQLite locally and PostgreSQL-friendly schema choices.
- Alembic initial migration scaffold.
- TypeScript Cloudflare Worker production target in `worker/` using Discord HTTP Interactions,
  D1, and Cron Triggers.
- Real X API provider with pagination, rate-limit metadata, retries for transient failures,
  media/video metrics kept separate from post impressions, and robust error mapping.

## X API Limitations

See [docs/x-api-capabilities.md](docs/x-api-capabilities.md) for the research notes.

Short version:

- Public user metrics include follower, following, listed, and post counts.
- Public post metrics include impressions, likes, replies, reposts/retweets, quotes, and bookmarks.
- Public video media can expose video view count.
- Non-public, organic, and promoted metrics require user-context auth and are for owned or managed content.
- Exact account-level historical views for arbitrary public accounts are not available retroactively through the normal public lookup path.
- Follower growth and views gained over a period should be calculated from this bot's stored snapshots.

## Setup

Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -e .[dev]
```

Create `.env` from [.env.example](.env.example) and set at least:

```dotenv
DISCORD_TOKEN=your_discord_bot_token
X_PROVIDER_MODE=mock
```

For real X API access:

```dotenv
X_PROVIDER_MODE=x_api
X_BEARER_TOKEN=your_x_api_bearer_token
```

Additional local settings:

```dotenv
X_INITIAL_BACKFILL_DAYS=30
X_INITIAL_BACKFILL_MAX_POSTS=200
X_REQUEST_TIMEOUT_SECONDS=20
X_MAX_RETRIES=3
X_MAX_CONCURRENCY=2
SNAPSHOT_MIN_INTERVAL_MINUTES=60
```

## Discord Configuration

Create a Discord application and bot in the Discord developer portal, invite it to your server with application command scope, then set `DISCORD_TOKEN`.

Management commands are allowed for Discord administrators or users/roles configured with:

```dotenv
AUTHORIZED_DISCORD_USER_IDS=123,456
AUTHORIZED_DISCORD_ROLE_IDS=789
```

## Running Locally

```powershell
.\.venv\Scripts\python -m bot.main
```

By default the app creates `data/x_analytics.db` and starts a collector loop every 60 minutes.

## Tests and Linting

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
```

Tests do not call live Discord or X APIs.

## Database

Core tables:

- `tracked_accounts`: stable tracked identity by X user ID, not username.
- `account_snapshots`: follower/following/post-count snapshots over time.
- `posts`: static post records keyed by X post ID.
- `post_metric_snapshots`: cumulative metric snapshots for each post over time.

Indexes support account/time and post/time queries. Static post data is stored once; changing metrics are stored in snapshot rows.

## Historical Analytics

Views gained during a period are calculated from cumulative post metric snapshots:

```text
latest snapshot at or before period end
- baseline snapshot at or before period start
```

For posts created inside the period, the baseline is zero. For posts created before the period, the bot requires a pre-period baseline snapshot. If the baseline is missing, `/analytics` reports insufficient history instead of inventing numbers.

This is different from "total current views on posts created during the period." The code is intentionally built around true metric growth over time.

The `/analytics` command also reports current cumulative performance for posts created in
the selected period. That is useful immediately after tracking starts, but it is labelled
separately from metric growth during the period.

## Cloudflare Production

Production lives under `worker/` and is intentionally separate from the local `discord.py`
gateway bot. The Worker uses Discord HTTP Interactions, validates Ed25519 signatures,
responds to Discord PING verification, stores data in D1, and runs scheduled collection
through Cloudflare Cron Triggers.

See [docs/cloudflare-deployment.md](docs/cloudflare-deployment.md).

## Credentials Needed

- `DISCORD_TOKEN`: Discord bot token.
- `X_BEARER_TOKEN`: X API bearer token, required only when `X_PROVIDER_MODE=x_api`.
- Optional Discord allowlist IDs for account-management commands.
- Cloudflare production secrets:
  - `X_BEARER_TOKEN`
  - `DISCORD_APPLICATION_PUBLIC_KEY`
  - `DISCORD_APPLICATION_ID`
  - `DISCORD_BOT_TOKEN` for deferred followups and command registration.

Do not put real credentials in Git. `.env` is ignored.

## Development Notes

- SQLite is the local default.
- Alembic migration files are included for production-style schema management.
- The mock provider lets the bot and tests run without external API access.
- The real provider uses official X API endpoints and avoids scraping or browser cookies.

## Recommended Next Feature

After the Cloudflare Worker is deployed and the Discord Interactions Endpoint is set,
register production slash commands through Discord's API and add richer D1 analytics
queries for top posts by engagement.
