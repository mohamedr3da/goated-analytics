from __future__ import annotations

from bot.providers.base import XNotFoundError, XProviderError, XRateLimitError


class ScraperError(XProviderError):
    """Base error for the public scraper provider."""


class ScraperBlocked(ScraperError):
    """X blocked public automated access."""


class LoginRequired(ScraperBlocked):
    """The public page could not be viewed without logging in."""


class AccountNotFound(XNotFoundError, ScraperError):
    """The requested public account does not exist."""


class MetricUnavailable(ScraperError):
    """A metric is not publicly exposed in the current page."""


class ParseFailure(ScraperError):
    """The public page did not contain the expected parseable records."""


class NavigationTimeout(ScraperError):
    """The public page request timed out."""


class UnexpectedPage(ParseFailure):
    """The public page loaded, but it was not the expected X profile page."""


class RateLimited(XRateLimitError, ScraperError):
    """Public page access was rate limited."""
