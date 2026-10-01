from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

from development.query_builder import build_google_news_query
from development.sources.base import BaseDevelopmentSource


class NewsAPISource(BaseDevelopmentSource):
    source_id = "newsapi"
    source_name = "NewsAPI"

    @staticmethod
    def _parse_articles(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = payload.get("articles") or []
        parsed: List[Dict[str, Any]] = []
        for article in items:
            if not isinstance(article, dict):
                continue
            title = article.get("title") or "Untitled NewsAPI story"
            url = article.get("url")
            summary = article.get("description") or article.get("content") or ""
            published_at = article.get("publishedAt")
            source = article.get("source") or {}
            source_name = source.get("name") or "NewsAPI"
            parsed.append({
                "title": title,
                "source_name": source_name,
                "source_url": url,
                "summary": summary,
                "published_at": published_at,
                "source_id": "newsapi",
                "category": "other",
                "event_type": "other",
            })
        return parsed

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_key = os.getenv("NEWSAPI_KEY")
        if not api_key:
            return []

        query = query_context.get("search_query") or build_google_news_query(query_context)
        try:
            days = max(1, int(query_context.get("days", 7)))
        except (TypeError, ValueError):
            days = 7
        from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "q": query,
            "language": "en",
            "from": from_date,
            "sortBy": "relevancy",
            "pageSize": 5,
            "apiKey": api_key,
        }
        async with httpx.AsyncClient(timeout=float(os.getenv("DEVELOPMENTS_SOURCE_TIMEOUT", "3.5"))) as client:
            response = await client.get("https://newsapi.org/v2/everything", params=params)
            response.raise_for_status()
            return self._parse_articles(response.json())
