import { PublicScraperProvider } from "./public-scraper";
import type { Env, XAccount, XPostWithMedia } from "./types";
import { XApiClient } from "./x-api";

export interface XDataProvider {
  getAccountByUsername(username: string): Promise<XAccount>;
  getPostsWindow(
    xUserId: string,
    startTime: Date,
    endTime: Date,
    maxPosts: number
  ): Promise<XPostWithMedia[]>;
}

export function createXProvider(env: Env): XDataProvider {
  if ((env.X_PROVIDER_MODE ?? "x_api").toLowerCase() === "scraper") {
    return new PublicScraperProvider({
      recentPostLimit: Math.min(Number(env.X_RECENT_POSTS_LIMIT ?? "10"), 10)
    });
  }
  if (!env.X_BEARER_TOKEN) {
    throw new Error("X_BEARER_TOKEN is required when X_PROVIDER_MODE=x_api.");
  }
  return new XApiClient(env.X_BEARER_TOKEN);
}

export function providerModeLabel(env: Env): string {
  if ((env.X_PROVIDER_MODE ?? "x_api").toLowerCase() === "scraper") {
    return "Public Scraper";
  }
  return "Official X API";
}

export function providerAuthLabel(env: Env): string {
  if ((env.X_PROVIDER_MODE ?? "x_api").toLowerCase() === "scraper") {
    return "None";
  }
  return "Bearer token";
}
