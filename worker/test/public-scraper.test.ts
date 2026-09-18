import { describe, expect, it } from "vitest";
import { createXProvider } from "../src/provider";
import { parsePublicProfilePage, PublicScraperProvider } from "../src/public-scraper";
import type { Env } from "../src/types";

const USER_REF = "VXNlcjoxMjM=";

function profileRecord(): string {
  return `
    <html><body>
      ${USER_REF}:$R[15]={__id:"${USER_REF}",__typename:"User",rest_id:"1688946553875058689",
        core:$R[17]={__ref:"client:${USER_REF}:core"},
        tweet_counts:$R[19]={__ref:"client:${USER_REF}:tweet_counts"},
        relationship_counts:$R[25]={__ref:"client:${USER_REF}:relationship_counts"},
        verification:$R[26]={__ref:"client:${USER_REF}:verification"}},
      "client:${USER_REF}:core":$R[32]={__id:"client:${USER_REF}:core",__typename:"UserCore",
        name:"Rawdogmoon",screen_name:"rawdogmoon",created_at_ms:1691511227184},
      "client:${USER_REF}:tweet_counts":$R[34]={__id:"client:${USER_REF}:tweet_counts",
        __typename:"UserTweetCounts",tweets:611},
      "client:${USER_REF}:relationship_counts":$R[49]={__id:"client:${USER_REF}:relationship_counts",
        __typename:"UserRelationshipCounts",followers:11030,following:290},
      "client:${USER_REF}:verification":$R[50]={__id:"client:${USER_REF}:verification",
        __typename:"UserVerification",verified:!1,is_blue_verified:!0,verified_type:null}
    </body></html>`;
}

function postRecord(): string {
  const postId = "2100698123983347787";
  const postRef = `VHdlZXQ6${postId}`;
  return `
      "${postRef}":$R[100]={__id:"${postRef}",__typename:"Tweet",rest_id:"${postId}",
        reply_to_results:$R[1]={__ref:"reply"},
        counts:$R[102]={__ref:"client:${postRef}:counts"},
        views:$R[103]={__ref:"client:${postRef}:views"},
        legacy:$R[104]={__ref:"client:${postRef}:legacy"},
        details:$R[105]={__ref:"client:${postRef}:details"}},
      "client:${postRef}:counts":$R[108]={__id:"client:${postRef}:counts",__typename:"ApiCounts",
        reply_count:4,retweet_count:5,favorite_count:1200,quote_count:2,bookmark_count:9},
      "client:${postRef}:views":$R[109]={__id:"client:${postRef}:views",__typename:"ViewCountInfo",
        count:"98.7K"},
      "client:${postRef}:legacy":$R[110]={__id:"client:${postRef}:legacy",__typename:"LegacyTweet",
        retweeted_status_results:null,possibly_sensitive:null,lang:"en"},
      "client:${postRef}:details":$R[111]={__id:"client:${postRef}:details",__typename:"TBirdData",
        full_text:"I like Worker parser tests.",created_at_ms:1789730000000}
    `;
}

describe("public scraper provider", () => {
  it("parses public profile and post metrics without media view fallback", () => {
    const result = parsePublicProfilePage(profileRecord() + postRecord(), "rawdogmoon", 10);

    expect(result.account.id).toBe("1688946553875058689");
    expect(result.account.username).toBe("rawdogmoon");
    expect(result.account.public_metrics?.followers_count).toBe(11030);
    expect(result.account.public_metrics?.following_count).toBe(290);
    expect(result.account.public_metrics?.post_count).toBe(611);
    expect(result.account.verified).toBe(true);
    expect(result.account.verified_type).toBe("blue");
    expect(result.posts).toHaveLength(1);
    expect(result.posts[0]?.id).toBe("2100698123983347787");
    expect(result.posts[0]?.public_metrics?.impression_count).toBe(98700);
    expect(result.posts[0]?.public_metrics?.like_count).toBe(1200);
    expect(result.posts[0]?.public_metrics?.reply_count).toBe(4);
    expect(result.posts[0]?.public_metrics?.retweet_count).toBe(5);
    expect(result.posts[0]?.public_metrics?.quote_count).toBe(2);
    expect(result.posts[0]?.public_metrics?.bookmark_count).toBe(9);
    expect(result.posts[0]?.video_view_count).toBeUndefined();
    expect(result.posts[0]?.referenced_tweets?.[0]?.type).toBe("replied_to");
  });

  it("detects login walls and unexpected layouts", () => {
    expect(() => parsePublicProfilePage("<title>Log in to X</title>", "rawdogmoon", 10))
      .toThrow("requires login");
    expect(() => parsePublicProfilePage("<html>No useful records</html>", "rawdogmoon", 10))
      .toThrow("parseable records");
  });

  it("factory creates scraper without requiring X bearer token", () => {
    const provider = createXProvider({
      X_PROVIDER_MODE: "scraper",
      X_RECENT_POSTS_LIMIT: "10"
    } as Env);

    expect(provider).toBeInstanceOf(PublicScraperProvider);
  });

  it("uses one public fetch for account and recent posts", async () => {
    const requests: string[] = [];
    const provider = new PublicScraperProvider({
      fetcher: async (input) => {
        requests.push(String(input));
        return new Response(profileRecord() + postRecord());
      },
      recentPostLimit: 10
    });

    const account = await provider.getAccountByUsername("@rawdogmoon");
    const posts = await provider.getPostsWindow(
      account.id,
      new Date("2026-09-01T00:00:00Z"),
      new Date("2026-09-30T00:00:00Z"),
      10
    );

    expect(posts).toHaveLength(1);
    expect(requests).toEqual(["https://x.com/rawdogmoon"]);
  });
});
