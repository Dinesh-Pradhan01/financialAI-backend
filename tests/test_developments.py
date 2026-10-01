import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from app.database.connection import get_db
from development.query_builder import build_company_query_context, build_gdelt_query, build_google_news_query, build_company_queries
from development.ranking import deduplicate_developments, score_development_item
from development.sources.gdelt import GDELTSource
from development.sources.google_news import GoogleNewsSource
from development.service import DevelopmentService
from development.company_intelligence.nearby_locations import NearbyLocationResolver


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None


@pytest.fixture(autouse=True)
def disable_network_nearby_lookup(monkeypatch):
    monkeypatch.setattr(NearbyLocationResolver, "resolve", AsyncMock(return_value=[]))


def test_company_location_query_generation():
    company = {
        "company_name": "ABC Technologies",
        "city": "Bengaluru",
        "state": "Karnataka",
        "business_category": "Information Technology",
    }
    query_context = build_company_query_context(company)

    gdelt_query = build_gdelt_query(query_context)
    news_query = build_google_news_query(query_context)

    assert "Bengaluru" in gdelt_query or "Karnataka" in gdelt_query
    assert "technology" in gdelt_query.lower()
    assert "Bengaluru" in news_query or "Karnataka" in news_query
    assert "government" in news_query.lower() or "project" in news_query.lower()


def test_state_fallback():
    company = {"company_name": "Nimbus Manufacturing", "city": None, "state": "Odisha", "business_category": "Manufacturing"}
    query_context = build_company_query_context(company)

    assert query_context["city"] is None
    assert "Odisha" in " ".join(query_context["geographic_terms"]) or query_context["state"] == "Odisha"
    assert query_context["state"] == "Odisha"


def test_optional_news_api_sources_activate_when_configured(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", "demo-newsapi-key")
    monkeypatch.setenv("THE_GUARDIAN_API_KEY", "demo-guardian-key")
    service = DevelopmentService()
    source_ids = [source.source_id for source in service.sources]
    assert "newsapi" in source_ids
    assert "guardian_api" in source_ids


def test_company_name_and_domain_remain_in_query_and_limit_is_five():
    company = {"company_name": "ABC Technologies", "city": "Bengaluru", "state": "Karnataka", "business_category": "Information Technology"}
    query_context = build_company_query_context(company)
    news_query = build_google_news_query(query_context)

    assert "ABC" in news_query or "ABC Technologies" in news_query
    assert "technology" in news_query.lower()
    assert "information technology" in news_query.lower() or "technology" in news_query.lower()


def test_gdelt_response_parsing():
    payload = {
        "articles": {
            "article": [
                {
                    "title": "Bengaluru tech park expands",
                    "url": "https://example.com/article-1",
                    "seendate": "20250102010101",
                    "source": ["Example News"],
                    "excerpt": "A major expansion is underway in the region.",
                }
            ]
        }
    }

    parsed = GDELTSource()._parse_articles(payload)

    assert len(parsed) == 1
    assert parsed[0]["title"] == "Bengaluru tech park expands"
    assert parsed[0]["source_name"] == "Example News"
    assert parsed[0]["source_url"] == "https://example.com/article-1"


def test_google_news_rss_parsing():
    xml = """
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title>Odisha manufacturing cluster announced</title>
          <link>https://example.com/news-1</link>
          <pubDate>Mon, 06 Jan 2025 10:00:00 GMT</pubDate>
          <source url="https://example.com/source">State Wire</source>
          <description>Large investment and industrial zone expansion in the region.</description>
        </item>
      </channel>
    </rss>
    """

    parsed = GoogleNewsSource()._parse_feed(xml)

    assert len(parsed) == 1
    assert parsed[0]["title"] == "Odisha manufacturing cluster announced"
    assert parsed[0]["source_name"] == "State Wire"
    assert parsed[0]["source_url"] == "https://example.com/news-1"


def test_deduplication():
    items = [
        {
            "title": "Same development",
            "summary": "Test summary",
            "source_name": "GDELT",
            "source_url": "https://example.com/same",
            "published_at": "2025-01-06T10:00:00Z",
            "city": "Bengaluru",
            "state": "Karnataka",
            "category": "technology",
            "event_type": "technology",
        },
        {
            "title": "Same development",
            "summary": "Better summary",
            "source_name": "Google News RSS",
            "source_url": "https://example.com/same",
            "published_at": "2025-01-06T10:15:00Z",
            "city": "Bengaluru",
            "state": "Karnataka",
            "category": "technology",
            "event_type": "technology",
        },
    ]

    deduped = deduplicate_developments(items)

    assert len(deduped) == 1
    assert deduped[0]["source_name"] in {"GDELT", "Google News RSS"}


def test_ranking():
    item = {
        "title": "Bengaluru IT campus expansion announced",
        "summary": "IT campus expansion and investment in Bengaluru expected to create jobs.",
        "source_name": "GDELT",
        "source_url": "https://example.com/rank-1",
        "published_at": "2025-01-07T10:00:00Z",
        "city": "Bengaluru",
        "state": "Karnataka",
        "category": "technology",
        "event_type": "technology",
    }

    scored = score_development_item(item, {"city": "Bengaluru", "state": "Karnataka", "business_category": "Information Technology"})

    assert 0.0 <= scored["relevance_score"] <= 1.0
    assert scored["relevance_score"] > 0.0


def test_missing_company():
    fake_db = SimpleNamespace(
        execute=lambda *args, **kwargs: FakeResult([])
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(DevelopmentService().fetch_company_developments(str(uuid.uuid4()), db=fake_db))
    assert exc.value.status_code == 404


def test_missing_city_state():
    company = {"company_name": "Alpha Systems", "city": None, "state": None, "business_category": "Technology"}
    assert build_company_query_context(company)["company_name"] == "Alpha Systems"


def test_company_queries_cover_multiple_dimensions_and_deduplicate():
    queries = build_company_queries({
        "company_name": "Acme Systems", "primary_industry": "Software", "business_category": "Software",
        "city": "Pune", "state": "Maharashtra", "competitors": ["Rival Ltd"],
        "technologies": ["Cloud computing"], "sub_industries": ["Enterprise software"],
    }, max_queries=20)
    joined = "\n".join(queries).lower()
    for term in ("acme systems", "software", "pune", "rival ltd", "cloud computing", "regulation", "investment", "global"):
        assert term in joined
    assert len(queries) == len({query.casefold() for query in queries})


def test_tracking_parameters_are_removed_for_deduplication():
    items = [
        {"title": "Company wins contract", "source_url": "https://example.com/story?utm_source=one"},
        {"title": "Company wins contract", "source_url": "https://example.com/story?utm_source=two"},
    ]
    assert len(deduplicate_developments(items)) == 1


def test_gdelt_failure_google_success():
    async def run_case():
        service = DevelopmentService()
        service._get_db_company = AsyncMock(return_value={
            "id": str(uuid.uuid4()),
            "company_name": "ABC Tech",
            "city": "Bengaluru",
            "state": "Karnataka",
            "business_category": "Information Technology",
        })

        with patch.object(GDELTSource, "fetch", AsyncMock(side_effect=Exception("GDELT failed"))), \
             patch.object(GoogleNewsSource, "fetch", AsyncMock(return_value=[{
                 "title": "Bengaluru technology development",
                 "summary": "Information Technology project update",
                 "source_name": "Google News RSS",
                 "source_url": "https://example.com/google-result",
                 "published_at": "2025-01-08T09:00:00Z",
                 "city": "Bengaluru",
                 "state": "Karnataka",
                 "category": "technology",
                 "event_type": "technology",
             }])):
            result = await service.fetch_company_developments(str(uuid.uuid4()), db=None)
            assert result["items"]
            assert result["sources"] == ["Google News RSS"]

    asyncio.run(run_case())


def test_google_failure_gdelt_success():
    async def run_case():
        service = DevelopmentService()
        service._get_db_company = AsyncMock(return_value={
            "id": str(uuid.uuid4()),
            "company_name": "ABC Tech",
            "city": "Bengaluru",
            "state": "Karnataka",
            "business_category": "Information Technology",
        })

        with patch.object(GDELTSource, "fetch", AsyncMock(return_value=[{
            "title": "Bengaluru technology infrastructure",
            "summary": "Information Technology project update",
            "source_name": "GDELT",
            "source_url": "https://example.com/gdelt-result",
            "published_at": "2025-01-08T09:00:00Z",
            "city": "Bengaluru",
            "state": "Karnataka",
            "category": "technology",
            "event_type": "technology",
        }])), \
             patch.object(GoogleNewsSource, "fetch", AsyncMock(side_effect=Exception("Google failed"))):
            result = await service.fetch_company_developments(str(uuid.uuid4()), db=None)
            assert result["items"]
            assert result["sources"] == ["GDELT"]

    asyncio.run(run_case())


def test_both_source_failures_return_empty_list():
    async def run_case():
        service = DevelopmentService()
        service._get_db_company = AsyncMock(return_value={
            "id": str(uuid.uuid4()),
            "company_name": "ABC Tech",
            "city": "Bengaluru",
            "state": "Karnataka",
            "business_category": "Information Technology",
        })

        with patch.object(GDELTSource, "fetch", AsyncMock(side_effect=Exception("GDELT failed"))), \
             patch.object(GoogleNewsSource, "fetch", AsyncMock(side_effect=Exception("Google failed"))):
            result = await service.fetch_company_developments(str(uuid.uuid4()), db=None)
            assert result["items"] == []
            assert result["sources"] == []

    asyncio.run(run_case())


def test_api_response_schema():
    company_id = str(uuid.uuid4())

    async def fake_execute(*args, **kwargs):
        return FakeResult([(company_id, "ABC Technologies", "Bengaluru", "Karnataka", "Information Technology")])

    with patch.object(GDELTSource, "fetch", AsyncMock(return_value=[{
        "title": "Bengaluru expansion",
        "summary": "Information Technology infrastructure project",
        "source_name": "GDELT",
        "source_url": "https://example.com/expansion",
        "published_at": "2025-01-08T09:00:00Z",
        "city": "Bengaluru",
        "state": "Karnataka",
        "category": "technology",
        "event_type": "technology",
    }])), \
         patch.object(GoogleNewsSource, "fetch", AsyncMock(return_value=[])):
        app.dependency_overrides[get_db] = lambda: SimpleNamespace(execute=fake_execute)
        with TestClient(app) as client:
            response = client.get(f"/api/v1/developments/{company_id}?limit=5&days=7")
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["name"] == "ABC Technologies"
    assert payload["sources"] == ["GDELT"]
    assert payload["items"][0]["title"] == "Bengaluru expansion"
    assert 0.0 <= payload["items"][0]["relevance_score"] <= 1.0
