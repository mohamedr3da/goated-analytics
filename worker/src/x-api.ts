import type { XAccount, XPost, XPostWithMedia } from "./types";

export class XApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly retryAfterSeconds?: number
  ) {
    super(message);
  }
}

export class XApiClient {
  constructor(private readonly bearerToken: string) {}

  async getAccountByUsername(username: string): Promise<XAccount> {
    const payload = await this.request(`/users/by/username/${normalizeUsername(username)}`, {
      "user.fields": [
        "id",
        "username",
        "name",
        "created_at",
        "protected",
        "verified",
        "verified_type",
        "profile_image_url",
        "public_metrics"
      ].join(",")
    });
    if (!payload.data?.id || !payload.data?.username) {
      throw new XApiError("X did not return a valid user payload.");
    }
    return payload.data as XAccount;
  }

  async getPostsWindow(
    xUserId: string,
    startTime: Date,
    endTime: Date,
    maxPosts: number
  ): Promise<XPostWithMedia[]> {
    const posts: XPostWithMedia[] = [];
    let nextToken: string | undefined;
    const seenTokens = new Set<string>();
    while (posts.length < maxPosts) {
      const payload = await this.request(`/users/${xUserId}/tweets`, {
        max_results: String(Math.max(5, Math.min(100, maxPosts - posts.length))),
        exclude: "retweets",
        "tweet.fields": [
          "id",
          "text",
          "author_id",
          "created_at",
          "public_metrics",
          "attachments",
          "conversation_id",
          "lang",
          "possibly_sensitive",
          "referenced_tweets"
        ].join(","),
        expansions: "attachments.media_keys",
        "media.fields": "public_metrics,type",
        start_time: startTime.toISOString(),
        end_time: endTime.toISOString(),
        ...(nextToken ? { pagination_token: nextToken } : {})
      });
      const media = new Map<string, number>();
      for (const item of payload.includes?.media ?? []) {
        if (item.media_key && item.public_metrics?.view_count !== undefined) {
          media.set(item.media_key, item.public_metrics.view_count);
        }
      }
      for (const item of payload.data ?? []) {
        const videoViews = (item.attachments?.media_keys ?? [])
          .map((key: string) => media.get(key) ?? 0)
          .reduce((total: number, value: number) => total + value, 0);
        posts.push({ ...item, video_view_count: videoViews || undefined });
      }
      nextToken = payload.meta?.next_token;
      if (!nextToken || seenTokens.has(nextToken)) {
        break;
      }
      seenTokens.add(nextToken);
    }
    return posts.slice(0, maxPosts);
  }

  private async request(path: string, params: Record<string, string>): Promise<any> {
    const url = new URL(`https://api.x.com/2${path}`);
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, value);
    }
    const response = await fetch(url, {
      headers: { authorization: `Bearer ${this.bearerToken}` }
    });
    if (response.status === 429) {
      throw new XApiError("X rate limit reached.", 429, retryAfter(response));
    }
    if (response.status === 401 || response.status === 403) {
      throw new XApiError("X API authentication failed.", response.status);
    }
    if (response.status === 404) {
      throw new XApiError("X account or resource was not found.", 404);
    }
    if (!response.ok) {
      throw new XApiError(`X API request failed with HTTP ${response.status}.`, response.status);
    }
    return response.json();
  }
}

export function normalizeUsername(username: string): string {
  const normalized = username.trim().replace(/^@/, "");
  if (!/^[A-Za-z0-9_]{1,15}$/.test(normalized)) {
    throw new XApiError("X usernames must be 1-15 letters, numbers, or underscores.");
  }
  return normalized;
}

function retryAfter(response: Response): number | undefined {
  const value = response.headers.get("retry-after");
  if (!value) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

