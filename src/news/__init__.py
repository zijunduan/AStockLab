"""Future news adapters.

News is explanatory context only.  It must never be mapped directly to a
buy/sell state without an independently validated strategy rule.
"""

from src.news.service import NewsItem, NewsProvider

__all__ = ["NewsItem", "NewsProvider"]
