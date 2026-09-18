# Cloudflare Deployment

## Chosen Architecture

Production uses a TypeScript Cloudflare Worker with Discord HTTP Interactions, D1, and Cron Triggers.

The existing local Python bot remains available for development. Production does not require your Windows PC, PowerShell, VS Code, or the Python virtual environment to stay running.

## Why HTTP Interactions Instead of Discord Gateway

The current feature set is slash-command based. Discord HTTP Interactions can handle slash commands without maintaining a long-lived Gateway session. That fits Cloudflare Workers better than trying to keep a persistent `discord.py` process alive.

The Worker validates:

- `X-Signature-Ed25519`
- `X-Signature-Timestamp`
- Discord PING verification

Long-running commands such as `/track` use deferred responses and followups.

## Resources

Use a separate Cloudflare account and new resources:

- Worker: `goated-analytics`
- D1 database: `goated-analytics-db`

Do not reuse Cliproom resources.

## Local Worker Validation

```powershell
cd worker
npm install
npm test
npm run typecheck
npx wrangler deploy --dry-run
```

## Cloudflare Setup

Log in to the separate Cloudflare account:

```powershell
cd worker
npx wrangler login
npx wrangler whoami
```

Create D1:

```powershell
npx wrangler d1 create goated-analytics-db
```

Copy the returned `database_id` into `worker/wrangler.jsonc` in the `d1_databases` binding.

Apply migrations:

```powershell
npx wrangler d1 migrations apply goated-analytics-db --remote
```

Set secrets:

```powershell
npx wrangler secret put X_BEARER_TOKEN
npx wrangler secret put DISCORD_APPLICATION_PUBLIC_KEY
npx wrangler secret put DISCORD_APPLICATION_ID
npx wrangler secret put DISCORD_BOT_TOKEN
```

Deploy:

```powershell
npx wrangler deploy
```

## Discord Setup

In the Discord Developer Portal, set the Interactions Endpoint URL to:

```text
https://goated-analytics.<your-subdomain>.workers.dev
```

Discord will send a PING validation request. The Worker responds with PONG if signatures validate.

## Smoke Test

1. Run `/status`.
2. Run `/twitter openai`.
3. Run `/track <test_account>`.
4. Wait for the hourly Cron Trigger or use Wrangler logs to inspect scheduled collection.
5. Confirm D1 rows exist:

```powershell
npx wrangler d1 execute goated-analytics-db --remote --command "SELECT COUNT(*) FROM tracked_accounts"
npx wrangler d1 execute goated-analytics-db --remote --command "SELECT COUNT(*) FROM post_metric_snapshots"
```

## Rollback

Use Wrangler versions:

```powershell
npx wrangler versions list
npx wrangler rollback
```

D1 data persists independently from Worker deployments.

## Troubleshooting

- Invalid Discord endpoint: check `DISCORD_APPLICATION_PUBLIC_KEY`.
- Deferred command never follows up: check `DISCORD_BOT_TOKEN` and Worker logs.
- X API unavailable: check `X_BEARER_TOKEN`, rate limits, and X API plan access.
- D1 binding missing: check `database_id` in `wrangler.jsonc`.

