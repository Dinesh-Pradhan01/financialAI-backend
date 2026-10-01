from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

from development.query_builder import build_google_news_query
from development.sources.base import BaseDevelopmentSource


class GuardianSource(BaseDevelopmentSource):
    source_id = "guardian_api"
    source_name = "The Guardian"

    @staticmethod
    def _parse_articles(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        results = payload.get("response", {}).get("results") or []
        parsed: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            parsed.append({
                "title": item.get("webTitle") or "Untitled Guardian story",
                "source_name": "The Guardian",
                "source_url": item.get("webUrl"),
                "summary": item.get("fields", {}).get("trailText") or item.get("sectionName") or "",
                "published_at": item.get("webPublicationDate"),
                "source_id": "guardian_api",
                "category": "other",
                "event_type": "other",
            })
        return parsed

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_key = os.getenv("THE_GUARDIAN_API_KEY") or os.getenv("GUARDIAN_API_KEY")
        if not api_key:
            return []

        query = query_context.get("search_query") or build_google_news_query(query_context)
        try:
            days = max(1, int(query_context.get("days", 7)))
        except (TypeError, ValueError):
            days = 7
        params = {
            "q": query,
            "api-key": api_key,
            "page-size": 5,
            "show-fields": "trailText",
            "order-by": "relevance",
            "from-date": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),
        }
        async with httpx.AsyncClient(timeout=float(os.getenv("DEVELOPMENTS_SOURCE_TIMEOUT", "3.5"))) as client:
            response = await client.get("https://content.guardianapis.com/search", params=params)
            response.raise_for_status()
            return self._parse_articles(response.json())
