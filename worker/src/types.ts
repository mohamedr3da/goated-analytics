export interface Env {
  DB: D1Database;
  ENVIRONMENT: string;
  X_PROVIDER_MODE?: string;
  X_BEARER_TOKEN?: string;
  DISCORD_APPLICATION_PUBLIC_KEY: string;
  DISCORD_APPLICATION_ID: string;
  DISCORD_BOT_TOKEN?: string;
  X_INITIAL_BACKFILL_DAYS: string;
  X_INITIAL_BACKFILL_MAX_POSTS: string;
  X_RECENT_POSTS_LIMIT: string;
  PUBLIC_ANALYTICS_ENABLED: string;
}

export interface DiscordInteraction {
  id: string;
  token: string;
  type: number;
  data?: {
    name: string;
    options?: Array<{ name: string; value: string }>;
  };
  member?: {
    permissions?: string;
    user?: { id: string };
    roles?: string[];
  };
  user?: { id: string };
}

export interface XAccount {
  id: string;
  username: string;
  name: string;
  protected?: boolean;
  verified?: boolean;
  verified_type?: string;
  profile_image_url?: string;
  created_at?: string;
  public_metrics?: {
    followers_count?: number;
    following_count?: number;
    post_count?: number;
    tweet_count?: number;
    listed_count?: number;
  };
}

export interface XPost {
  id: string;
  author_id?: string;
  created_at: string;
  text?: string;
  conversation_id?: string;
  lang?: string;
  possibly_sensitive?: boolean;
  referenced_tweets?: Array<{ type: string; id: string }>;
  attachments?: { media_keys?: string[] };
  url?: string;
  public_metrics?: {
    impression_count?: number;
    like_count?: number;
    reply_count?: number;
    retweet_count?: number;
    repost_count?: number;
    quote_count?: number;
    bookmark_count?: number;
  };
}

export interface XPostWithMedia extends XPost {
  video_view_count?: number;
}
