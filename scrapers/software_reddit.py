"""Software-focused expansion using the existing Arctic Shift transport."""

from __future__ import annotations

from scrapers.arctic_shift import ArcticShiftScraper


class SoftwareRedditScraper(ArcticShiftScraper):
    """Discover launched tools and concrete needs in four maintainable communities.

    SideProject contributes launch posts, selfhosted and opensource contribute
    inspectable tools, and productivity contributes end-user utilities/needs.
    """

    SUBREDDITS = ("SideProject", "selfhosted", "opensource", "productivity")
    SOFTWARE_INTENTS = (
        "app", "tool", "software", "extension", "self-hosted", "self hosted",
        "open source", "utility", "saas", "local-first", "local first",
        "looking for", "need", "alternative", "organize", "productivity",
    )
    QUERY_BATCHES = {
        # A no-query request is a legitimate fallback on communities where
        # Arctic Shift rejects its optional full-text query parameter (422).
        "sideproject": (None, "app"),
        "selfhosted": (None, "app"),
        "opensource": (None, "tool"),
        "productivity": (None, "app"),
    }

    def __init__(self, subreddits=None, limit_per_subreddit: int = 30) -> None:
        super().__init__(subreddits or self.SUBREDDITS, limit_per_subreddit)

    @property
    def source_name(self) -> str:
        return "reddit_software"

    def _intent_batches(self, subreddit: str) -> tuple[str | None, str | None]:
        return self.QUERY_BATCHES.get(subreddit.casefold(), ("app", "tool"))

    @classmethod
    def _matched_intents(cls, title: str, selftext: str, subreddit: str) -> list[str]:
        text = f"{title} {selftext}".casefold()
        return [intent for intent in cls.SOFTWARE_INTENTS if intent in text]

    @staticmethod
    def _intent_source(title: str, selftext: str, subreddit: str) -> str:
        return subreddit
