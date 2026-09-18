import { compactNumber } from "./formatting";
import { periodStart } from "./analytics";
import { recordAccountSnapshot, recordPostMetrics, upsertPost, upsertTrackedAccount } from "./db";
import { optionValue } from "./discord";
import { createXProvider, providerAuthLabel, providerModeLabel } from "./provider";
import type { DiscordInteraction, Env } from "./types";
import { normalizeUsername } from "./x-api";

export async function handleImmediateCommand(interaction: DiscordInteraction, env: Env): Promise<string> {
  const name = interaction.data?.name;
  if (name === "status") {
    const tracked = await env.DB.prepare(
      "SELECT COUNT(*) AS count FROM tracked_accounts WHERE is_tracking_enabled = 1"
    ).first<{ count: number }>();
    return [
      "Discord Interactions: Healthy",
      "Database: D1",
      `X Data Provider: ${providerModeLabel(env)}`,
      `Authentication: ${providerAuthLabel(env)}`,
      `Tracked Accounts: ${tracked?.count ?? 0}`,
      `Environment: ${env.ENVIRONMENT}`
    ].join("\n");
  }
  if (name === "tracked") {
    const accounts = await env.DB.prepare(
      `SELECT username
       FROM tracked_accounts
       WHERE is_tracking_enabled = 1
       ORDER BY username COLLATE NOCASE
       LIMIT 25`
    ).all<{ username: string }>();
    const usernames = accounts.results?.map((account) => `@${account.username}`) ?? [];
    if (usernames.length === 0) {
      return "No accounts are being tracked yet.";
    }
    return `Tracked accounts:\n${usernames.join("\n")}`;
  }
  if (name === "twitter") {
    return twitterCommand(interaction, env);
  }
  if (name === "analytics") {
    const username = normalizeUsername(optionValue(interaction, "username") ?? "");
    const period = optionValue(interaction, "period") ?? "1d";
    const start = periodStart(period);
    const account = await env.DB.prepare(
      "SELECT id, username FROM tracked_accounts WHERE lower(username) = lower(?)"
    ).bind(username).first<{ id: number; username: string }>();
    if (!account) {
      return `@${username} is not being tracked yet.`;
    }
    const posts = await env.DB.prepare(
      `SELECT COUNT(*) AS count
       FROM posts
       WHERE account_id = ? AND created_at >= ?`
    ).bind(account.id, start.toISOString()).first<{ count: number }>();
    return `@${account.username} ${period} analytics\nPosts published: ${posts?.count ?? 0}\nHistorical metric-growth uses stored D1 snapshots.`;
  }
  if (name === "untrack") {
    const username = normalizeUsername(optionValue(interaction, "username") ?? "");
    const result = await env.DB.prepare(
      "UPDATE tracked_accounts SET is_tracking_enabled = 0, updated_at = ? WHERE lower(username) = lower(?)"
    ).bind(new Date().toISOString(), username).run();
    if ((result.meta.changes ?? 0) === 0) {
      return `@${username} is not currently tracked.`;
    }
    return `Stopped tracking @${username}. Historical data was kept.`;
  }
  return "Unknown command.";
}

export async function twitterCommand(interaction: DiscordInteraction, env: Env): Promise<string> {
  const username = optionValue(interaction, "username");
  if (!username) {
    return "Please provide a username.";
  }
  const account = await createXProvider(env).getAccountByUsername(username);
  return `@${account.username}\nFollowers: ${compactNumber(account.public_metrics?.followers_count)}\nPosts: ${compactNumber(account.public_metrics?.post_count ?? account.public_metrics?.tweet_count)}`;
}

export async function trackCommand(interaction: DiscordInteraction, env: Env): Promise<string> {
  const username = optionValue(interaction, "username");
  if (!username) {
    return "Please provide a username.";
  }
  const now = new Date();
  const client = createXProvider(env);
  const account = await client.getAccountByUsername(username);
  const accountId = await upsertTrackedAccount(env.DB, account, now.toISOString());
  await recordAccountSnapshot(env.DB, accountId, account, now.toISOString());
  const posts = await client.getPostsWindow(
    account.id,
    new Date(now.getTime() - Number(env.X_INITIAL_BACKFILL_DAYS) * 24 * 60 * 60 * 1000),
    now,
    Number(env.X_INITIAL_BACKFILL_MAX_POSTS)
  );
  for (const post of posts) {
    const postId = await upsertPost(env.DB, accountId, post, now.toISOString());
    await recordPostMetrics(env.DB, postId, post, now.toISOString());
  }
  return `Now tracking @${account.username}\nProvider: ${providerModeLabel(env)}\nFollowers: ${compactNumber(account.public_metrics?.followers_count)}\nPosts imported: ${posts.length}`;
}

export async function refreshCommand(interaction: DiscordInteraction, env: Env): Promise<string> {
  const username = normalizeUsername(optionValue(interaction, "username") ?? "");
  const account = await env.DB.prepare(
    "SELECT id, username FROM tracked_accounts WHERE lower(username) = lower(?) AND is_tracking_enabled = 1"
  ).bind(username).first<{ id: number; username: string }>();
  if (!account) {
    return `@${username} is not being tracked.`;
  }
  const now = new Date();
  const client = createXProvider(env);
  const fresh = await client.getAccountByUsername(username);
  const accountId = await upsertTrackedAccount(env.DB, fresh, now.toISOString());
  await recordAccountSnapshot(env.DB, accountId, fresh, now.toISOString());
  const posts = await client.getPostsWindow(
    fresh.id,
    new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000),
    now,
    Number(env.X_RECENT_POSTS_LIMIT)
  );
  for (const post of posts) {
    const postId = await upsertPost(env.DB, accountId, post, now.toISOString());
    await recordPostMetrics(env.DB, postId, post, now.toISOString());
  }
  return `Refreshed @${fresh.username}. Posts checked: ${posts.length}.`;
}

export async function runCollection(env: Env): Promise<{ successes: number; failures: number }> {
  const now = new Date().toISOString();
  const accounts = await env.DB.prepare(
    "SELECT id, username, x_user_id FROM tracked_accounts WHERE is_tracking_enabled = 1"
  ).all<{ id: number; username: string; x_user_id: string }>();
  const client = createXProvider(env);
  let successes = 0;
  let failures = 0;
  for (const account of accounts.results ?? []) {
    try {
      const fresh = await client.getAccountByUsername(account.username);
      const accountId = await upsertTrackedAccount(env.DB, fresh, now);
      await recordAccountSnapshot(env.DB, accountId, fresh, now);
      const posts = await client.getPostsWindow(
        fresh.id,
        new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
        new Date(),
        Number(env.X_RECENT_POSTS_LIMIT)
      );
      for (const post of posts) {
        const postId = await upsertPost(env.DB, accountId, post, now);
        await recordPostMetrics(env.DB, postId, post, now);
      }
      successes += 1;
    } catch (error) {
      failures += 1;
      console.log(JSON.stringify({ event: "collection_account_failed", username: account.username, error: String(error) }));
    }
  }
  await env.DB.prepare(
    "INSERT INTO collection_runs (started_at, finished_at, successes, failures, status) VALUES (?, ?, ?, ?, ?)"
  ).bind(now, new Date().toISOString(), successes, failures, "finished").run();
  return { successes, failures };
}
