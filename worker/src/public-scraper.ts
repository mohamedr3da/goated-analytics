import type { XAccount, XPostWithMedia } from "./types";
import { normalizeUsername } from "./x-api";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type ScraperLogger = (payload: PublicXFetchDiagnostics & { event: string }) => void;

export type PublicXPageKind =
  | "normal_x_html"
  | "login_wall"
  | "rate_limit"
  | "block_challenge"
  | "account_not_found"
  | "generic_error_page"
  | "unknown";

export interface PublicXFetchDiagnostics {
  requestedHost: string;
  requestedPath: string;
  fetchThrew: boolean;
  errorName?: string;
  errorMessage?: string;
  httpStatus?: number;
  statusText?: string;
  finalUrl?: string;
  contentType?: string;
  bodyLength?: number;
  pageKind?: PublicXPageKind;
  excerpt?: string;
}

interface ScrapeResult {
  account: XAccount;
  posts: XPostWithMedia[];
  stats: {
    pagesLoaded: number;
    postsExtracted: number;
    metricsExtracted: number;
    missingMetrics: number;
    loginWall: boolean;
    blocked: boolean;
    parseFailures: number;
  };
}

export class ScraperError extends Error {}
export class ScraperBlocked extends ScraperError {}
export class LoginRequired extends ScraperBlocked {}
export class AccountNotFound extends ScraperError {}
export class MetricUnavailable extends ScraperError {}
export class ParseFailure extends ScraperError {}
export class NavigationTimeout extends ScraperError {}
export class UnexpectedPage extends ParseFailure {}
export class RateLimited extends ScraperError {}

export class PublicScraperProvider {
  private readonly fetcher: Fetcher;
  private readonly logger: ScraperLogger;
  private readonly recentPostLimit: number;
  private readonly usernamesById = new Map<string, string>();
  private readonly scrapesByUsername = new Map<string, ScrapeResult>();
  private readonly scrapeLimitsByUsername = new Map<string, number>();
  lastScrapeStats: ScrapeResult["stats"] | undefined;

  constructor(options: {
    fetcher?: Fetcher;
    logger?: ScraperLogger;
    recentPostLimit?: number;
  } = {}) {
    this.fetcher = options.fetcher ?? fetch;
    this.logger = options.logger ?? ((payload) => console.log(JSON.stringify(payload)));
    this.recentPostLimit = options.recentPostLimit ?? 10;
  }

  async getAccountByUsername(username: string): Promise<XAccount> {
    const scrape = await this.scrapeUsername(username, this.recentPostLimit);
    this.usernamesById.set(scrape.account.id, scrape.account.username);
    return scrape.account;
  }

  async getPostsWindow(
    xUserId: string,
    startTime: Date,
    endTime: Date,
    maxPosts: number
  ): Promise<XPostWithMedia[]> {
    const username = this.usernamesById.get(xUserId);
    if (!username) {
      throw new ScraperError("Public scraper needs an account lookup before fetching posts.");
    }
    const limit = Math.min(maxPosts, this.recentPostLimit);
    const key = username.toLowerCase();
    let scrape = this.scrapesByUsername.get(key);
    const cachedLimit = this.scrapeLimitsByUsername.get(key) ?? -1;
    if (!scrape || cachedLimit < limit) {
      scrape = await this.scrapeUsername(username, limit);
    }
    return scrape.posts
      .filter((post) => {
        const createdAt = new Date(post.created_at);
        return createdAt >= startTime && createdAt <= endTime;
      })
      .slice(0, maxPosts);
  }

  private async scrapeUsername(username: string, maxPosts: number): Promise<ScrapeResult> {
    const normalized = normalizeUsername(username);
    const result = await fetchPublicXProfile(normalized, this.fetcher);
    if (result.diagnostics.fetchThrew) {
      this.logFailure("public_scraper_fetch_failure", result.diagnostics);
      if (result.diagnostics.errorName === "AbortError") {
        throw new NavigationTimeout("Public X page request timed out.");
      }
      throw new ScraperError("Public X page request failed.");
    }
    if (result.diagnostics.httpStatus === 429) {
      this.logFailure("public_scraper_fetch_response_failure", result.diagnostics);
      throw new RateLimited("Public X page access was rate limited.");
    }
    if ((result.diagnostics.httpStatus ?? 0) >= 400) {
      this.logFailure("public_scraper_fetch_response_failure", result.diagnostics);
      throw new ScraperError(`Public X page returned HTTP ${result.diagnostics.httpStatus}.`);
    }
    if (result.body === undefined) {
      this.logFailure("public_scraper_fetch_response_failure", result.diagnostics);
      throw new ScraperError("Public X page response body was unavailable.");
    }
    let scrape: ScrapeResult;
    try {
      scrape = parsePublicProfilePage(result.body, normalized, maxPosts);
    } catch (error) {
      this.logFailure("public_scraper_parse_failure", result.diagnostics);
      throw error;
    }
    this.cacheScrape(normalized, scrape, maxPosts);
    this.lastScrapeStats = scrape.stats;
    return scrape;
  }

  private logFailure(event: string, diagnostics: PublicXFetchDiagnostics): void {
    this.logger({ event, ...diagnostics });
  }

  private cacheScrape(username: string, scrape: ScrapeResult, maxPosts: number): void {
    for (const key of [username.toLowerCase(), scrape.account.username.toLowerCase()]) {
      this.scrapesByUsername.set(key, scrape);
      this.scrapeLimitsByUsername.set(key, maxPosts);
    }
    this.usernamesById.set(scrape.account.id, scrape.account.username);
  }
}

async function fetchPublicXProfile(
  username: string,
  fetcher: Fetcher = fetch
): Promise<{ diagnostics: PublicXFetchDiagnostics; body?: string }> {
  const normalized = normalizeUsername(username);
  const target = new URL(`https://x.com/${normalized}`);
  const baseDiagnostics = {
    requestedHost: target.hostname,
    requestedPath: target.pathname
  };
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  let response: Response;
  try {
    response = await fetcher(target.toString(), {
      headers: {
        accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "user-agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
          "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
      },
      signal: controller.signal
    });
  } catch (error) {
    return {
      diagnostics: {
        ...baseDiagnostics,
        fetchThrew: true,
        ...(error instanceof Error
          ? { errorName: error.name, errorMessage: sanitizeErrorMessage(error.message) }
          : { errorName: "UnknownError" })
      }
    };
  } finally {
    clearTimeout(timeout);
  }

  const body = await response.text();
  const pageKind = classifyPublicXPage(body, response.status);
  const contentType = response.headers.get("content-type") ?? undefined;
  return {
    body,
    diagnostics: {
      ...baseDiagnostics,
      fetchThrew: false,
      httpStatus: response.status,
      statusText: response.statusText,
      finalUrl: response.url || target.toString(),
      ...(contentType !== undefined ? { contentType } : {}),
      bodyLength: body.length,
      pageKind,
      ...(pageKind === "normal_x_html" ? {} : { excerpt: sanitizedExcerpt(body) })
    }
  };
}

export async function fetchPublicXDiagnostics(
  username: string,
  fetcher: Fetcher = fetch
): Promise<PublicXFetchDiagnostics> {
  return (await fetchPublicXProfile(username, fetcher)).diagnostics;
}

export function classifyPublicXPage(body: string, status: number): PublicXPageKind {
  const lowered = body.toLowerCase();
  if (status === 429 || lowered.includes("rate limit") || lowered.includes("too many requests")) {
    return "rate_limit";
  }
  if (lowered.includes("this account doesn't exist") || lowered.includes("this account does not exist")) {
    return "account_not_found";
  }
  if (lowered.includes("log in to x") || lowered.includes("sign in to x")) {
    return "login_wall";
  }
  if (
    lowered.includes("just a moment") ||
    lowered.includes("captcha") ||
    lowered.includes("challenge") ||
    lowered.includes("cf-chl") ||
    lowered.includes("access denied") ||
    lowered.includes("blocked")
  ) {
    return "block_challenge";
  }
  if (body.includes('__typename:"User"') || body.includes('__typename:"Tweet"')) {
    return "normal_x_html";
  }
  if (status >= 400 || lowered.includes("error") || lowered.includes("unavailable")) {
    return "generic_error_page";
  }
  return "unknown";
}

export function parsePublicProfilePage(
  html: string,
  requestedUsername: string,
  maxPosts: number
): ScrapeResult {
  raiseForKnownFailure(html);
  const records = extractRecords(html);
  const account = parseAccount(html, records, requestedUsername);
  const posts = parsePosts(records, account, maxPosts);
  if (!account.id && posts.length === 0) {
    throw new ParseFailure("Public X page did not contain profile or timeline parseable records.");
  }
  return {
    account,
    posts,
    stats: statsForPosts(posts)
  };
}

function raiseForKnownFailure(html: string): void {
  const lowered = html.toLowerCase();
  if (lowered.includes("this account doesn't exist") || lowered.includes("this account does not exist")) {
    throw new AccountNotFound("X account was not found.");
  }
  if (lowered.includes("account suspended")) {
    throw new AccountNotFound("X account is suspended or unavailable.");
  }
  if (lowered.includes("log in to x") || lowered.includes("sign in to x")) {
    throw new LoginRequired("X public page requires login.");
  }
}

function extractRecords(text: string): Map<string, string> {
  const records = new Map<string, string>();
  for (const marker of text.matchAll(/__typename:"/g)) {
    const markerIndex = marker.index ?? 0;
    const start = text.lastIndexOf("{", markerIndex);
    if (start === -1) {
      continue;
    }
    const end = findMatchingBrace(text, start);
    if (end === undefined) {
      continue;
    }
    const body = text.slice(start + 1, end);
    const id = extractJsString(body, "__id");
    if (id) {
      records.set(id, body);
    }
  }
  return records;
}

function findMatchingBrace(text: string, start: number): number | undefined {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }
    if (char === "\"") {
      inString = true;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return index;
      }
    }
  }
  return undefined;
}

function parseAccount(
  html: string,
  records: Map<string, string>,
  requestedUsername: string
): XAccount {
  const userBody = [...records.values()].find((body) => body.includes('__typename:"User"')) ?? "";
  const core = records.get(extractRef(userBody, "core") ?? "") ?? "";
  const relationship = records.get(extractRef(userBody, "relationship_counts") ?? "") ?? "";
  const tweetCounts = records.get(extractRef(userBody, "tweet_counts") ?? "") ?? "";
  const avatar = records.get(extractRef(userBody, "avatar") ?? "") ?? "";
  const verification = records.get(extractRef(userBody, "verification") ?? "") ?? "";
  const createdAtMs = extractJsInt(core, "created_at_ms") ?? extractJsInt(html, "createdAtMs");
  const blueVerified = extractJsBool(verification, "is_blue_verified");
  const verified = blueVerified
    ? true
    : (extractJsBool(verification, "verified") ?? extractJsBool(html, "isVerified") ?? false);
  const verifiedType = extractJsString(verification, "verified_type") ?? (blueVerified ? "blue" : undefined);
  const profileImageUrl = extractJsString(avatar, "image_url") ?? extractJsString(html, "avatarUrl");
  const id = extractJsString(userBody, "rest_id") ?? extractJsString(html, "restId") ?? "";
  const username =
    extractJsString(core, "screen_name") ??
    extractJsString(html, "screenName") ??
    normalizeUsername(requestedUsername);

  if (!id && !username) {
    throw new UnexpectedPage("Public X profile fields were not found.");
  }

  const publicMetrics: XAccount["public_metrics"] = {};
  setMetric(publicMetrics, "followers_count", extractJsInt(relationship, "followers") ?? extractJsInt(html, "followers"));
  setMetric(publicMetrics, "following_count", extractJsInt(relationship, "following") ?? extractJsInt(html, "following"));
  setMetric(publicMetrics, "post_count", extractJsInt(tweetCounts, "tweets") ?? extractJsInt(html, "tweets"));

  return {
    id,
    username,
    name: extractJsString(core, "name") ?? extractJsString(html, "name") ?? username,
    protected: extractJsBool(html, "protected") ?? false,
    verified,
    ...(verifiedType !== undefined ? { verified_type: verifiedType } : {}),
    ...(profileImageUrl !== undefined ? { profile_image_url: profileImageUrl } : {}),
    ...(createdAtMs === undefined ? {} : { created_at: new Date(createdAtMs).toISOString() }),
    public_metrics: publicMetrics
  };
}

function parsePosts(
  records: Map<string, string>,
  account: XAccount,
  maxPosts: number
): XPostWithMedia[] {
  if (maxPosts <= 0) {
    return [];
  }
  const posts: XPostWithMedia[] = [];
  const seen = new Set<string>();
  for (const body of records.values()) {
    if (!body.includes('__typename:"Tweet"')) {
      continue;
    }
    const postId = extractJsString(body, "rest_id");
    if (!postId || seen.has(postId)) {
      continue;
    }
    const details = records.get(extractRef(body, "details") ?? "") ?? "";
    const createdAtMs = extractJsInt(details, "created_at_ms");
    const text = extractJsString(details, "full_text");
    if (createdAtMs === undefined || text === undefined) {
      continue;
    }
    const counts = records.get(extractRef(body, "counts") ?? "") ?? "";
    const views = records.get(extractRef(body, "views") ?? "") ?? "";
    const legacy = records.get(extractRef(body, "legacy") ?? "") ?? "";
    const referenced = referencedTweet(body, legacy);
    const publicMetrics: XPostWithMedia["public_metrics"] = {};
    setMetric(publicMetrics, "impression_count", parsePublicCount(extractJsString(views, "count")));
    setMetric(publicMetrics, "like_count", extractJsInt(counts, "favorite_count"));
    setMetric(publicMetrics, "reply_count", extractJsInt(counts, "reply_count"));
    setMetric(publicMetrics, "retweet_count", extractJsInt(counts, "retweet_count"));
    setMetric(publicMetrics, "quote_count", extractJsInt(counts, "quote_count"));
    setMetric(publicMetrics, "bookmark_count", extractJsInt(counts, "bookmark_count"));
    const post: XPostWithMedia = {
      id: postId,
      author_id: account.id,
      created_at: new Date(createdAtMs).toISOString(),
      text,
      conversation_id: postId,
      public_metrics: publicMetrics,
      url: `https://x.com/${account.username}/status/${postId}`
    };
    const lang = extractJsString(legacy, "lang");
    if (lang !== undefined) {
      post.lang = lang;
    }
    const possiblySensitive = extractJsBool(legacy, "possibly_sensitive");
    if (possiblySensitive !== undefined) {
      post.possibly_sensitive = possiblySensitive;
    }
    if (referenced) {
      post.referenced_tweets = [referenced];
    }
    posts.push(post);
    seen.add(postId);
    if (posts.length >= maxPosts) {
      break;
    }
  }
  return posts;
}

function referencedTweet(
  tweetBody: string,
  legacyBody: string
): { type: string; id: string } | undefined {
  if (fieldNonNull(legacyBody, "retweeted_status_results")) {
    return { type: "retweeted", id: "unknown" };
  }
  if (fieldNonNull(tweetBody, "quoted_tweet_results")) {
    return { type: "quoted", id: "unknown" };
  }
  if (fieldNonNull(tweetBody, "reply_to_results")) {
    return { type: "replied_to", id: "unknown" };
  }
  return undefined;
}

function statsForPosts(posts: XPostWithMedia[]): ScrapeResult["stats"] {
  let metricsExtracted = 0;
  let missingMetrics = 0;
  for (const post of posts) {
    const metrics = post.public_metrics ?? {};
    for (const value of [
      metrics.impression_count,
      metrics.like_count,
      metrics.reply_count,
      metrics.retweet_count,
      metrics.quote_count,
      metrics.bookmark_count
    ]) {
      if (value === undefined) {
        missingMetrics += 1;
      } else {
        metricsExtracted += 1;
      }
    }
  }
  return {
    pagesLoaded: 1,
    postsExtracted: posts.length,
    metricsExtracted,
    missingMetrics,
    loginWall: false,
    blocked: false,
    parseFailures: 0
  };
}

export function parsePublicCount(value: string | undefined): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  const normalized = decodeHtml(value).trim().replace(/[, ]/g, "");
  if (!normalized || ["unavailable", "n/a", "none", "-"].includes(normalized.toLowerCase())) {
    return undefined;
  }
  const suffix = normalized.at(-1)?.toUpperCase();
  const multipliers: Record<string, number> = { K: 1_000, M: 1_000_000, B: 1_000_000_000 };
  const multiplier = suffix && multipliers[suffix] ? multipliers[suffix] : 1;
  const numeric = multiplier === 1 ? normalized : normalized.slice(0, -1);
  const parsed = Number.parseFloat(numeric);
  return Number.isFinite(parsed) ? Math.trunc(parsed * multiplier) : undefined;
}

function extractRef(body: string, field: string): string | undefined {
  const match = new RegExp(
    `(?<![A-Za-z0-9_])${escapeRegExp(field)}:\\$R\\[\\d+\\]=\\{__ref:${stringPattern()}\\}`
  ).exec(body);
  return match?.[1] ? decodeJsString(match[1]) : undefined;
}

function extractJsString(body: string, field: string): string | undefined {
  const match = new RegExp(`(?<![A-Za-z0-9_])${escapeRegExp(field)}:${stringPattern()}`).exec(body);
  return match?.[1] ? decodeJsString(match[1]) : undefined;
}

function extractJsInt(body: string, field: string): number | undefined {
  const match = new RegExp(`(?<![A-Za-z0-9_])${escapeRegExp(field)}:(?<value>-?\\d+|null)`).exec(body);
  const raw = match?.groups?.value;
  if (!raw || raw === "null") {
    return undefined;
  }
  return Number.parseInt(raw, 10);
}

function extractJsBool(body: string, field: string): boolean | undefined {
  const match = new RegExp(
    `(?<![A-Za-z0-9_])${escapeRegExp(field)}:(?<value>!0|!1|true|false|null)`
  ).exec(body);
  if (!match?.groups || match.groups.value === "null") {
    return undefined;
  }
  return match.groups.value === "!0" || match.groups.value === "true";
}

function fieldNonNull(body: string, field: string): boolean {
  const match = new RegExp(
    `(?<![A-Za-z0-9_])${escapeRegExp(field)}:(?<value>null|\\$R\\[\\d+\\]=\\{__ref:${stringPattern()}\\})`
  ).exec(body);
  return match !== null && match.groups?.value !== "null";
}

function setMetric<T extends Record<string, number | undefined>>(
  target: T,
  key: keyof T,
  value: number | undefined
): void {
  if (value !== undefined) {
    target[key] = value as T[keyof T];
  }
}

function stringPattern(): string {
  return "\"((?:\\\\.|[^\"\\\\])*)\"";
}

function decodeJsString(value: string): string {
  try {
    return decodeHtml(JSON.parse(`"${value}"`) as string);
  } catch {
    return decodeHtml(value);
  }
}

function decodeHtml(value: string): string {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function sanitizedExcerpt(body: string): string {
  return decodeHtml(
    body
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/\b(auth_token|ct0|bearer|authorization|cookie|token)\b[^\s]*/gi, "[redacted]")
      .replace(/\s+/g, " ")
      .trim()
  ).slice(0, 300);
}

function sanitizeErrorMessage(message: string): string {
  return message
    .replace(/\b(auth_token|ct0|bearer|authorization|cookie|token)\b[^\s]*/gi, "[redacted]")
    .slice(0, 300);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
