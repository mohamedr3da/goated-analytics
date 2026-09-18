# Experimental Public Scraper Provider

This provider is a local proof of concept for logged-out public X profile pages. It is selected with:

```dotenv
X_PROVIDER_MODE=scraper
```

It intentionally does not use X credentials, login cookies, browser session state, proxies, CAPTCHA
bypass, or anti-bot bypass techniques. The provider fetches the public profile page HTML and parses
embedded profile/timeline records when they are present.

## Extraction Boundary

- `bot/providers/public_scraper.py` implements the `XAnalyticsProvider` contract.
- `bot/providers/scraper/parser.py` parses public HTML into isolated scraper dataclasses.
- `bot/providers/scraper/errors.py` defines explicit scraper failure types:
  `ScraperBlocked`, `LoginRequired`, `AccountNotFound`, `MetricUnavailable`, `ParseFailure`,
  `NavigationTimeout`, `UnexpectedPage`, and `RateLimited`.

Unavailable profile or post metrics are represented as `None`, never fabricated as zero. Post
impressions from public view counts remain separate from `video_view_count`, which is left as `None`
unless a distinct media/video view source is added later.

## Local Probe

Run:

```powershell
.\.venv\Scripts\python scripts\probe_public_scraper.py rawdogmoon
```

Automated tests use saved/sanitized HTML snippets only; they do not call live X pages.

## Production Status

This mode is not switched on for production by this change. A production Cloudflare Worker version
would need either a TypeScript port of the parser or a separate Python service. Cloudflare Browser
Run may be useful later if X removes the currently visible HTML records and requires JavaScript
execution, but the current proof does not need a browser.
