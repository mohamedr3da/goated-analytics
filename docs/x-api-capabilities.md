# Current X API Capability Notes

Checked on 18 September 2026 against official X documentation.

## Public Account/User Metrics

The X user lookup endpoints support `user.fields=public_metrics`. The public user metrics documented in current API responses include:

- `followers_count`
- `following_count`
- `listed_count`
- `post_count`
- `like_count`
- `media_count`

The bot stores the account-level values that are useful for analytics now: followers, following, listed, and post count.

Source: https://docs.x.com/x-api/users/get-user-by-username

## Public Post Metrics

Current post public metrics include:

- reposts/retweets
- replies
- likes
- quotes
- impressions via `public_metrics.impression_count`
- bookmarks via `public_metrics.bookmark_count`

The metrics documentation says public metrics can be accessed with bearer-token authentication.

Source: https://docs.x.com/x-api/fundamentals/metrics

## Post Timestamps and Recent Posts

User posts can be fetched through `GET /2/users/{id}/tweets`. The bot requests `created_at`, `author_id`, `text`, `attachments`, and `public_metrics`, then stores static post details separately from metric snapshots.

Source: https://docs.x.com/x-api/users/get-posts

## Video Views

Video media public metrics can expose `public_metrics.view_count` when media expansions are requested. X documents video views as aggregated across all posts containing the video, so it should not be treated as identical to post impressions.

Source: https://docs.x.com/x-api/fundamentals/metrics

## Private, Organic, and Promoted Metrics

The metrics documentation separates:

- `public_metrics`: bearer token, visible metrics.
- `non_public_metrics`: user context, owned posts only.
- `organic_metrics`: user context, owned posts only.
- `promoted_metrics`: user context for promoted posts.

The same page documents a 30-day limit for non-public, organic, and promoted metrics.

Source: https://docs.x.com/x-api/fundamentals/metrics

## Analytics Endpoints

The current docs include `GET /2/tweets/analytics` with fields such as impressions, engagements, follows, bookmarks, media views, replies, retweets, and timestamped metrics. This is a future extension point for owned/managed account analytics.

The MVP provider intentionally uses the broadly useful public lookup/timeline paths first, then stores snapshots. This keeps analytics available for public accounts while leaving a clean path to add owned-account analytics later.

Source: https://docs.x.com/x-api/posts/get-post-analytics

## Unavailable or Not Retroactive Through Public Lookup

The regular public lookup endpoints return current cumulative metrics, not arbitrary historical account-level views. Follower growth, views gained in a period, and engagement gained in a period must be calculated from stored snapshots after tracking starts.

The bot therefore reports insufficient history when the required baseline snapshot is missing.

