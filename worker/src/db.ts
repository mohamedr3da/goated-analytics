import { safePreview } from "./formatting";
import type { XAccount, XPostWithMedia } from "./types";

export async function upsertTrackedAccount(db: D1Database, account: XAccount, now: string) {
  const existing = await db
    .prepare("SELECT id FROM tracked_accounts WHERE x_user_id = ?")
    .bind(account.id)
    .first<{ id: number }>();
  if (existing) {
    await db
      .prepare(
        `UPDATE tracked_accounts
         SET username = ?, display_name = ?, profile_image_url = ?, account_created_at = ?,
             verified = ?, verified_type = ?, protected = ?, updated_at = ?
         WHERE id = ?`
      )
      .bind(
        account.username,
        account.name,
        account.profile_image_url ?? null,
        account.created_at ?? null,
        account.verified ? 1 : 0,
        account.verified_type ?? null,
        account.protected ? 1 : 0,
        now,
        existing.id
      )
      .run();
    return existing.id;
  }
  const result = await db
    .prepare(
      `INSERT INTO tracked_accounts
       (x_user_id, username, display_name, profile_image_url, account_created_at,
        verified, verified_type, protected, tracking_started_at, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      account.id,
      account.username,
      account.name,
      account.profile_image_url ?? null,
      account.created_at ?? null,
      account.verified ? 1 : 0,
      account.verified_type ?? null,
      account.protected ? 1 : 0,
      now,
      now,
      now
    )
    .run();
  return Number(result.meta.last_row_id);
}

export async function recordAccountSnapshot(db: D1Database, accountId: number, account: XAccount, now: string) {
  await db
    .prepare(
      `INSERT OR IGNORE INTO account_snapshots
       (account_id, captured_at, followers_count, following_count, post_count, listed_count, raw_metrics)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      accountId,
      now,
      account.public_metrics?.followers_count ?? null,
      account.public_metrics?.following_count ?? null,
      account.public_metrics?.post_count ?? account.public_metrics?.tweet_count ?? null,
      account.public_metrics?.listed_count ?? null,
      JSON.stringify(account.public_metrics ?? {})
    )
    .run();
}

export async function upsertPost(db: D1Database, accountId: number, post: XPostWithMedia, now: string) {
  const postType = post.referenced_tweets?.[0]?.type === "quoted"
    ? "quote"
    : post.referenced_tweets?.[0]?.type === "replied_to"
      ? "reply"
      : "post";
  await db
    .prepare(
      `INSERT INTO posts
       (x_post_id, account_id, created_at, text_preview, url, post_type, referenced_post_id,
        conversation_id, lang, possibly_sensitive, first_seen_at, last_seen_at, raw_data)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(x_post_id) DO UPDATE SET
        account_id = excluded.account_id,
        text_preview = excluded.text_preview,
        url = excluded.url,
        post_type = excluded.post_type,
        referenced_post_id = excluded.referenced_post_id,
        conversation_id = excluded.conversation_id,
        lang = excluded.lang,
        possibly_sensitive = excluded.possibly_sensitive,
        last_seen_at = excluded.last_seen_at,
        raw_data = excluded.raw_data`
    )
    .bind(
      post.id,
      accountId,
      post.created_at,
      safePreview(post.text ?? "", 500),
      post.url ?? `https://x.com/i/status/${post.id}`,
      postType,
      post.referenced_tweets?.[0]?.id ?? null,
      post.conversation_id ?? null,
      post.lang ?? null,
      post.possibly_sensitive === undefined ? null : post.possibly_sensitive ? 1 : 0,
      now,
      now,
      JSON.stringify(post)
    )
    .run();
  const row = await db.prepare("SELECT id FROM posts WHERE x_post_id = ?").bind(post.id).first<{ id: number }>();
  if (!row) {
    throw new Error("Post upsert did not return a row.");
  }
  return row.id;
}

export async function recordPostMetrics(db: D1Database, postId: number, post: XPostWithMedia, now: string) {
  await db
    .prepare(
      `INSERT OR IGNORE INTO post_metric_snapshots
       (post_id, captured_at, impression_count, like_count, reply_count, repost_count,
        quote_count, bookmark_count, video_view_count, raw_metrics)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      postId,
      now,
      post.public_metrics?.impression_count ?? null,
      post.public_metrics?.like_count ?? null,
      post.public_metrics?.reply_count ?? null,
      post.public_metrics?.retweet_count ?? post.public_metrics?.repost_count ?? null,
      post.public_metrics?.quote_count ?? null,
      post.public_metrics?.bookmark_count ?? null,
      post.video_view_count ?? null,
      JSON.stringify(post.public_metrics ?? {})
    )
    .run();
}
