"""Shared interface and exceptions for product source scrapers."""

from abc import ABC, abstractmethod

from models import Product


class ScraperError(Exception):
    """Base exception for expected scraper failures."""


class ScraperFetchError(ScraperError):
    """Raised when a scraper cannot retrieve or parse source data."""


class BaseScraper(ABC):
    """Abstract interface implemented by every product source scraper.

    Implementations should raise :class:`ScraperFetchError` for expected
    retrieval or parsing failures instead of returning fabricated products.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the stable name of the scraper's source platform."""
        raise NotImplementedError

    @abstractmethod
    def fetch(self) -> list[Product]:
        """Fetch and normalize products from the source platform.

        Returns:
            Products normalized to the shared :class:`Product` model.

        Raises:
            ScraperFetchError: If source retrieval or parsing fails.
        """
        raise NotImplementedError
