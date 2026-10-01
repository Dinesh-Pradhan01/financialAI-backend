import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from development.company_intelligence.nearby_locations import NearbyLocationResolver
from development.normalizer import normalize_development_record
from development.query.query_builder import QueryBuilder
from development.query.query_types import DevelopmentQueryType
from development.ranking import deduplicate_developments, rank_development_items
from development.service import CompanyIntelligenceService, DevelopmentService, classify_development, select_diverse_developments, _evidence_opportunity_score, _opportunity_relevance, _parse_company_intelligence, _parse_development_insights, _fallback_company_implication
from development.sources.gdelt import GDELTSource
from development.sources.google_news import GoogleNewsSource


def _profile():
    return {
        "company_name": "Northstar Consulting",
        "primary_industry": "Professional Services",
        "business_domains": ["Technology Consulting", "Cybersecurity", "Digital Transformation"],
        "sub_industries": ["Management Consulting"],
        "technologies": ["Artificial Intelligence", "Cloud Computing"],
        "products_services": ["Cybersecurity Advisory"],
        "business_keywords": ["Enterprise Technology"],
        "competitors": ["Example Advisory Group"],
        "city": "Pune", "state": "Maharashtra",
        "nearby_locations": ["Nashik", "Mumbai"],
    }


def test_queries_are_typed_balanced_and_company_query_is_not_primary():
    queries = QueryBuilder(max_queries=20).build(_profile())
    types = {query["type"] for query in queries}
    assert {DevelopmentQueryType.DOMAIN, DevelopmentQueryType.LOCAL, DevelopmentQueryType.NEARBY,
            DevelopmentQueryType.COMPETITOR, DevelopmentQueryType.TENDER, DevelopmentQueryType.OPPORTUNITY,
            DevelopmentQueryType.STATE, DevelopmentQueryType.GLOBAL}.issubset(types)
    company_queries = [query for query in queries if query["type"] == DevelopmentQueryType.COMPANY]
    assert len(company_queries) == 1
    assert queries.index(company_queries[0]) > 0
    assert any("Cybersecurity" in query["query"] for query in queries)


def test_query_builder_adds_domain_variations_with_bounded_family_coverage():
    profile = _profile()
    queries = QueryBuilder(max_queries=30).build(profile)
    text = [query["query"].lower() for query in queries]
    assert len(queries) == 30
    assert any('"cybersecurity"' in q and "tender" in q for q in text)
    assert any('"cybersecurity"' in q and "pune" in q for q in text)
    assert any('"cybersecurity"' in q and "maharashtra" in q for q in text)
    assert {DevelopmentQueryType.DOMAIN, DevelopmentQueryType.TECHNOLOGY,
            DevelopmentQueryType.LOCAL, DevelopmentQueryType.NEARBY,
            DevelopmentQueryType.STATE, DevelopmentQueryType.GOVERNMENT,
            DevelopmentQueryType.TENDER, DevelopmentQueryType.OPPORTUNITY,
            DevelopmentQueryType.COMPETITOR, DevelopmentQueryType.NATIONAL,
            DevelopmentQueryType.GLOBAL}.issubset({query["type"] for query in queries})


def test_nearby_location_resolver_is_bounded_and_degrades_gracefully():
    async def run():
        resolver = NearbyLocationResolver()
        with patch("development.company_intelligence.nearby_locations.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(side_effect=RuntimeError("offline"))
            assert await resolver.resolve("Pune", "Maharashtra", limit=6) == []
        assert await resolver.resolve(None, "Maharashtra") == []
    asyncio.run(run())


def test_company_context_without_website_does_not_invent_profile_details():
    async def run():
        service = CompanyIntelligenceService()
        with patch.object(service, "discover_website", AsyncMock(return_value=[])), \
             patch.object(GDELTSource, "fetch", AsyncMock(return_value=[])), \
             patch.object(GoogleNewsSource, "fetch", AsyncMock(return_value=[])), \
             patch("development.service._get_gemini_service", return_value=None):
            profile = await service.build_profile({"company_name": "Northstar Consulting", "business_category": "Technology & IT", "website": None})
        assert profile["primary_industry"] == "Technology & IT"
        assert profile["business_domains"] == []
        assert profile["competitors"] == []
    asyncio.run(run())


def test_external_domain_event_can_rank_without_company_name_and_local_noise_is_filtered():
    profile = _profile()
    external = {"title": "Maharashtra expands cybersecurity procurement", "summary": "Government agency seeks cybersecurity advisory and digital transformation services", "source_id": "gdelt_doc", "published_at": "2026-10-01T09:00:00Z", "development_type": "tender", "opportunity_type": "tender", "business_opportunity_score": .95, "event_type": "government_tender", "city": None, "state": "Maharashtra"}
    local_noise = {"title": "Pune celebrates local arts festival", "summary": "A city cultural event this weekend", "source_id": "google_news_rss", "published_at": "2026-10-01T09:00:00Z", "development_type": "local", "opportunity_type": "none", "city": "Pune"}
    ranked = rank_development_items([external, local_noise], profile)
    assert len(ranked) == 1
    assert ranked[0]["title"] == external["title"]
    assert ranked[0]["relevance_score"] > .5


def test_tender_needs_domain_overlap_to_receive_high_opportunity_score():
    good = normalize_development_record({"title": "Cybersecurity services tender for Maharashtra agencies", "summary": "RFP for security operations and advisory", "query_type": "tender"}, {})
    unrelated = normalize_development_record({"title": "Catering services tender", "summary": "Food supply procurement", "query_type": "tender"}, {})
    classify_development(good, _profile())
    classify_development(unrelated, _profile())
    assert good["business_opportunity_score"] >= .9
    assert unrelated["business_opportunity_score"] < .5


def test_category_selection_limits_company_news_share():
    categories = ["company", "company", "domain", "domain", "local", "government", "competitor", "global"]
    items = [{"title": category, "development_type": category, "relevance_score": 1 - index / 100} for index, category in enumerate(categories)]
    selected = select_diverse_developments(items, 8)
    assert len(selected) <= 8
    assert sum(item["development_type"] == "company" for item in selected) <= 2
    assert {"domain", "local", "government", "competitor", "global"}.issubset({item["development_type"] for item in selected})


def test_category_selection_fills_limit_when_only_one_relevant_family_exists():
    candidates = [{"title": f"Cybersecurity policy development {index}", "development_type": "domain", "relevance_score": 1 - index / 100} for index in range(12)]
    assert len(select_diverse_developments(candidates, 10)) == 10


def test_near_duplicate_syndicated_headlines_collapse_but_distinct_events_remain():
    base = {"summary": "State government AI programme", "published_at": "2026-10-01T08:00:00Z"}
    duplicate = [
        {**base, "title": "Karnataka launches new state AI program", "source_url": "https://a.test/1"},
        {**base, "title": "Karnataka launches new state AI programme", "source_url": "https://b.test/2"},
        {**base, "title": "Karnataka opens cybersecurity procurement", "source_url": "https://c.test/3"},
    ]
    assert len(deduplicate_developments(duplicate)) == 2


def test_article_text_populates_only_supported_location_and_opportunity_score():
    item = normalize_development_record({"title": "Bengaluru cybersecurity tender for Karnataka agencies", "summary": "RFP seeks cybersecurity services", "query_type": "tender"}, {})
    classify_development(item, _profile())
    assert item["city"] == "Bengaluru" and item["state"] == "Karnataka"
    assert item["business_opportunity_score"] >= .9
    assert item["opportunity_relevance"] == _opportunity_relevance(item["business_opportunity_score"])
    assert _evidence_opportunity_score({"title": "New cafe opens in Bengaluru", "summary": "Local business"}, _profile()) == 0


def test_company_intelligence_parser_normalizes_structured_output_shape_drift():
    parsed = _parse_company_intelligence('```json\n{"primary_industry":"Consulting","business_domains":"Cybersecurity","technologies":[{"name":"AI"}]}\n```')
    assert parsed["business_domains"] == ["Cybersecurity"]
    assert parsed["technologies"] == ["AI"]


def test_insight_parser_recovers_batch_shapes_and_uses_evidence_grounded_fallback():
    items = [{"title": "Karnataka announces cybersecurity project", "summary": "Government project"}]
    insights = _parse_development_insights('{"results":[{"summary":"A cybersecurity project was announced","opportunity_type":"RFP","business_opportunity_score":"0.9"}]}', items, {"company_name": "Northstar Consulting", "business_domains": ["Cybersecurity"]})
    assert len(insights) == 1
    assert "Northstar Consulting" in insights[0].implication
    assert insights[0].opportunity_type == "RFP"
    assert insights[0].confidence == .5


def test_company_implication_fallback_names_verified_company_domain_without_claiming_a_win():
    implication = _fallback_company_implication({"title": "Cybersecurity policy update", "city": "Bengaluru"}, {"company_name": "Northstar Consulting", "business_domains": ["Cybersecurity"]})
    assert "Northstar Consulting" in implication and "Cybersecurity" in implication
    assert "does not establish a direct contract" in implication


def test_content_classification_uses_supported_state_government_and_global_evidence():
    profile = {**_profile(), "city": "Bengaluru", "state": "Karnataka"}
    cases = [
        ({"title": "Karnataka court AI robotics project ruling", "summary": "Artificial intelligence project area", "query_type": "domain"}, "state"),
        ({"title": "Delhi govt sets up AI centre for officers", "summary": "Artificial intelligence and emerging technology", "query_type": "domain"}, "government"),
        ({"title": "India-UK cybersecurity partnership announced", "summary": "Cross-border cyber security cooperation", "query_type": "domain"}, "global"),
    ]
    for raw, expected_type in cases:
        item = normalize_development_record(raw, {})
        classify_development(item, profile)
        assert item["development_type"] == expected_type


def test_ai_alias_counts_as_verified_artificial_intelligence_relevance():
    item = {"title": "Government initiative launches new AI programme", "summary": "Artificial intelligence project", "development_type": "government", "opportunity_type": "market_opportunity", "business_opportunity_score": 0, "published_at": datetime.now(timezone.utc).isoformat(), "source_name": "Google News RSS", "source_url": "https://example.test/ai"}
    ranked = rank_development_items([item], _profile())
    assert len(ranked) == 1 and ranked[0]["relevance_score"] >= .38
    assert ranked[0]["business_opportunity_score"] == .6


def test_service_fills_ten_from_a_large_deduplicated_candidate_pool():
    async def run():
        service = DevelopmentService()
        company = {"id": "84840060-25b4-4550-9e3c-f840d857c697", "company_name": "Northstar Consulting", "city": "Pune", "state": "Maharashtra", "business_category": "Professional Services", "website": None}
        service._get_db_company = AsyncMock(return_value=company)
        service.intelligence.build_profile = AsyncMock(return_value={**_profile(), "_gemini_company_call": False})
        service.nearby_resolver.resolve = AsyncMock(return_value=["Nashik", "Mumbai"])

        async def fake_fetch(context, source_name):
            query = context["search_query"]
            slug = str(abs(hash(query)))
            return [{"title": f"{query} market update", "summary": "Cybersecurity and digital transformation technology consulting government project update", "source_name": source_name, "source_url": f"https://example.test/{slug}", "published_at": datetime.now(timezone.utc).isoformat(), "source_id": source_name.lower().replace(" ", "_")}]

        async def fake_gdelt(context):
            return await fake_fetch(context, "GDELT")

        async def fake_google(context):
            return await fake_fetch(context, "Google News RSS")

        with patch.object(GDELTSource, "fetch", AsyncMock(side_effect=fake_gdelt)), \
             patch.object(GoogleNewsSource, "fetch", AsyncMock(side_effect=fake_google)), \
             patch("development.service._get_gemini_service", return_value=None):
            response = await service.fetch_company_developments(company["id"], db=object(), limit=10, days=7)
        assert len(response["items"]) == 10
        assert len({item["title"] for item in response["items"]}) == 10
        assert len({item["development_type"] for item in response["items"]}) > 1
    asyncio.run(run())


def test_discovery_metadata_survives_normalization():
    candidate = normalize_development_record({"title": "Cybersecurity procurement", "query_type": "tender", "discovery_query": "cybersecurity tender India", "query_priority": .99, "source_id": "gdelt_doc", "source_result": {"url": "https://example.test/a"}}, {})
    assert candidate["query_type"] == "tender"
    assert candidate["discovery_query"] == "cybersecurity tender India"
    assert candidate["source_result"]["url"] == "https://example.test/a"


def test_company_lookup_is_read_only():
    class Result:
        def first(self):
            return ("id", "Northstar Consulting", "Pune", "Maharashtra", "Professional Services", "Consulting", None)

    class DB:
        statements = []
        def execute(self, statement, params):
            self.statements.append(str(statement).strip().lower())
            return Result()

    async def run():
        db = DB()
        profile = await DevelopmentService()._get_db_company("id", db)
        assert profile["company_name"] == "Northstar Consulting"
        assert len(db.statements) == 1 and db.statements[0].startswith("select")
    asyncio.run(run())
