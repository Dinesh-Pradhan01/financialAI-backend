from __future__ import annotations

import logging
import os
from typing import Any, Dict, List
from urllib.parse import quote_plus

import feedparser
import httpx

from development.config import get_source_by_id
from development.query_builder import build_google_news_query
from development.sources.base import BaseDevelopmentSource

logger = logging.getLogger(__name__)


class GoogleNewsSource(BaseDevelopmentSource):
    source_id = "google_news_rss"
    source_name = "Google News RSS"

    @staticmethod
    def _parse_feed(xml_payload: str) -> List[Dict[str, Any]]:
        parsed = feedparser.parse(xml_payload)
        items: List[Dict[str, Any]] = []
        for entry in getattr(parsed, "entries", []) or []:
            title = entry.get("title") or "Untitled Google News entry"
            link = entry.get("link") or entry.get("link", "")
            summary = entry.get("summary") or entry.get("description") or ""
            published_at = entry.get("published") or entry.get("updated")
            source_name = "Google News RSS"
            source = entry.get("source")
            if isinstance(source, dict):
                source_name = source.get("title") or source_name
            items.append({
                "title": title,
                "source_name": source_name,
                "source_url": link,
                "summary": summary,
                "published_at": published_at,
                "source_id": "google_news_rss",
                "category": "other",
                "event_type": "other",
            })
        return items

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        source_config = get_source_by_id(self.source_id)
        if not source_config:
            return []
        query = query_context.get("search_query") or build_google_news_query(query_context)
        if query_context.get("days"):
            try:
                days = max(1, int(query_context["days"]))
            except (TypeError, ValueError):
                days = 7
            query = f"{query} when:{days}d"
        url = source_config["request_template"].format(URL_ENCODED_QUERY=quote_plus(query))
        async with httpx.AsyncClient(timeout=float(os.getenv("DEVELOPMENTS_SOURCE_TIMEOUT", "3.5"))) as client:
            response = await client.get(url)
            response.raise_for_status()
            return self._parse_feed(response.text)
