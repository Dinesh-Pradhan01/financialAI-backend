from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx

from development.config import get_source_by_id
from development.query_builder import build_gdelt_query
from development.sources.base import BaseDevelopmentSource

logger = logging.getLogger(__name__)


class GDELTSource(BaseDevelopmentSource):
    source_id = "gdelt_doc"
    source_name = "GDELT"

    def _parse_articles(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        articles = payload.get("articles", {}).get("article", []) if isinstance(payload.get("articles"), dict) else payload.get("articles", [])
        if isinstance(articles, dict):
            articles = [articles]
        parsed: List[Dict[str, Any]] = []
        for item in articles:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "Untitled GDELT entry"
            url = item.get("url") or item.get("url_mobile") or item.get("shareImage")
            summary = item.get("excerpt") or item.get("snippet") or item.get("description") or ""
            published = item.get("seendate") or item.get("date") or item.get("published")
            source_name = item.get("source")
            if isinstance(source_name, list):
                source_name = source_name[0] if source_name else "GDELT"
            parsed.append({
                "title": title,
                "source_name": source_name or self.source_name,
                "source_url": url,
                "summary": summary,
                "published_at": published,
                "source_id": self.source_id,
                "category": "other",
                "event_type": "other",
            })
        return parsed

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        source_config = get_source_by_id(self.source_id)
        if not source_config:
            return []
        query = query_context.get("search_query") or build_gdelt_query(query_context)
        url = source_config["request_template"].format(URL_ENCODED_QUERY=quote_plus(query))
        try:
            days = max(1, int(query_context.get("days", 7)))
        except (TypeError, ValueError):
            days = 7
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d%H%M%S")
        url += f"&startdatetime={start}"
        async with httpx.AsyncClient(timeout=float(os.getenv("DEVELOPMENTS_SOURCE_TIMEOUT", "3.5"))) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
            return self._parse_articles(payload)
