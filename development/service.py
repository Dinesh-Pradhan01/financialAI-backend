import asyncio
import inspect
import json
import logging
import re
import os
import time
from urllib.robotparser import RobotFileParser
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text

from development.normalizer import normalize_development_record
from development.query_builder import build_company_query_context
from development.query.query_builder import QueryBuilder
from development.company_intelligence import NearbyLocationResolver
from development.config import load_development_config
from development.ranking import deduplicate_developments, rank_development_items
from development.schemas import CompanyIntelligenceSchema, DevelopmentInsightBatchSchema, GeminiDevelopmentInsightBatchSchema, DevelopmentResponse
from development.sources.gdelt import GDELTSource
from development.sources.google_news import GoogleNewsSource
from development.sources.newsapi import NewsAPISource
from development.sources.guardian import GuardianSource

logger = logging.getLogger(__name__)
_gemini_service = None
MAX_QUERIES = int(os.getenv("DEVELOPMENTS_MAX_QUERIES", str(load_development_config().get("company_aware_scoring", {}).get("max_queries", 24))))
MAX_RESULTS_PER_QUERY = int(os.getenv("DEVELOPMENTS_MAX_RESULTS_PER_QUERY", "8"))
MAX_GEMINI_CANDIDATES = int(os.getenv("DEVELOPMENTS_MAX_GEMINI_CANDIDATES", "20"))
SOURCE_TIMEOUT = float(os.getenv("DEVELOPMENTS_SOURCE_TIMEOUT", "3.5"))
GDELT_TIMEOUT = float(os.getenv("DEVELOPMENTS_GDELT_TIMEOUT", "1.5"))
SOURCE_CONCURRENCY = int(os.getenv("DEVELOPMENTS_SOURCE_CONCURRENCY", "10"))
GDELT_CONCURRENCY = int(os.getenv("DEVELOPMENTS_GDELT_CONCURRENCY", "6"))
MIN_RELEVANCE_SCORE = float(os.getenv("DEVELOPMENTS_MIN_RELEVANCE_SCORE", str(load_development_config().get("company_aware_scoring", {}).get("min_relevance_score", 0.38))))


def _get_gemini_service():
    global _gemini_service
    if _gemini_service is None:
        try:
            from app.ai.llm import gemini_service
            _gemini_service = gemini_service
        except Exception as exc:
            logger.warning("Gemini service unavailable (%s)", type(exc).__name__)
            return None
    return _gemini_service


class CompanyIntelligenceService:
    """Request-scoped profile enrichment. No profile or evidence is persisted."""

    async def discover_website(self, website: Optional[str]) -> List[Dict[str, str]]:
        if not website:
            return []
        url = website.strip()
        if not urlparse(url).scheme:
            url = "https://" + url
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return []
        started = time.perf_counter()
        pages = [url]
        evidence = []
        pages_fetched = 0
        try:
            async with httpx.AsyncClient(timeout=2.5, follow_redirects=True, headers={"User-Agent": "SpotliteDevelopments/1.0"}) as client:
                robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
                try:
                    robots_response = await client.get(robots_url)
                    if robots_response.status_code == 200:
                        parser = RobotFileParser(robots_url)
                        parser.parse(robots_response.text.splitlines())
                        if not parser.can_fetch("SpotliteDevelopments", url):
                            logger.info("Company website disallows automated retrieval")
                            return []
                except Exception:
                    logger.debug("robots.txt unavailable; continuing with bounded homepage retrieval")
                response = await client.get(url)
                response.raise_for_status()
                pages_fetched += 1
                html = response.text[:500_000]
                home_text = _html_to_text(html)[:12000]
                if len(home_text) > 150 and not any(token in home_text.lower() for token in ("checking your browser", "enable javascript", "cloudflare", "access denied")):
                    evidence.append({"source": "company_website", "url": str(response.url), "evidence": home_text})
                links = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
                for link in links:
                    candidate = urljoin(str(response.url), link)
                    path = urlparse(candidate).path.lower()
                    if urlparse(candidate).hostname == parsed.hostname and any(k in path for k in ("about", "product", "service", "solution", "industry", "capabilit", "what-we-do", "technology", "cyber", "cloud", "artificial-intelligence", "consult")) and candidate not in pages:
                        pages.append(candidate)
                    if len(pages) >= 6:
                        break
                async def fetch_page(page: str):
                    nonlocal pages_fetched
                    try:
                        page_response = await client.get(page)
                        page_response.raise_for_status()
                        pages_fetched += 1
                        text = _html_to_text(page_response.text[:300_000])[:8000]
                        if len(text) > 150 and not any(token in text.lower() for token in ("checking your browser", "enable javascript", "cloudflare", "access denied")):
                            return {"source": "company_website", "url": str(page_response.url), "evidence": text}
                    except Exception as exc:
                        logger.debug("Company website page unavailable (%s)", type(exc).__name__)
                    return None
                page_evidence = await asyncio.gather(*(fetch_page(page) for page in pages[1:]))
                evidence.extend(item for item in page_evidence if item)
        except Exception as exc:
            logger.info("Company website fetch failed company_website=%s error=%s", bool(website), type(exc).__name__)
        logger.info("Company website discovery website_present=%s fetch_success=%s pages_fetched=%d pages_with_text=%d extracted_chars=%d elapsed_seconds=%.2f", bool(website), bool(evidence), pages_fetched, len(evidence), sum(len(item.get("evidence", "")) for item in evidence), time.perf_counter() - started)
        return evidence

    async def build_profile(self, company: Dict[str, Any]) -> Dict[str, Any]:
        started = time.perf_counter()
        website_task = self.discover_website(company.get("website"))
        name = (company.get("company_name") or "").strip()
        identity_query = f'"{name}"' + (f' "{company.get("city")}"' if company.get("city") else "")
        search_context = {**company, "search_query": identity_query}
        async def company_search_evidence():
            async def fetch_identity(source):
                try:
                    timeout = GDELT_TIMEOUT if source.source_id == "gdelt_doc" else SOURCE_TIMEOUT
                    return await asyncio.wait_for(source.fetch(search_context), timeout=timeout)
                except Exception as exc:
                    logger.info("Company identity search source=%s timeout/failure=%s", source.source_name, type(exc).__name__)
                    return exc
            return await asyncio.gather(fetch_identity(GDELTSource()), fetch_identity(GoogleNewsSource()))
        website_evidence, company_searches = await asyncio.gather(website_task, company_search_evidence())
        public_evidence = []
        for source, results in zip(("GDELT", "Google News RSS"), company_searches):
            if isinstance(results, Exception):
                logger.info("Company identity search %s unavailable (%s)", source, type(results).__name__)
                continue
            for result in results[:5]:
                public_evidence.append({"source": source, "url": result.get("source_url"), "title": result.get("title"), "published_at": result.get("published_at"), "evidence": result.get("summary")})
        evidence = website_evidence + public_evidence
        profile = {
            **company,
            "primary_industry": company.get("business_category"),
            "sub_industries": [], "business_domains": [], "products_services": [], "technologies": [],
            "business_keywords": [], "competitors": [], "target_markets": [],
            "relevant_geographies": [x for x in [company.get("city"), company.get("state"), "India"] if x],
            "regulatory_domains": [], "evidence": evidence,
        }
        profile = _deterministic_profile_enrichment(profile)
        logger.info("Company evidence company=%s website_present=%s website_pages=%d public_evidence=%d total_evidence=%d evidence_chars=%d", name, bool(company.get("website")), len(website_evidence), len(public_evidence), len(evidence), sum(len(item.get("evidence") or item.get("title") or "") for item in evidence))
        gemini = _get_gemini_service()
        profile_has_supported_domains = len(profile.get("business_domains") or []) >= 2 and bool(profile.get("technologies") or profile.get("products_services"))
        gemini_company_call = bool(gemini and gemini.is_available() and evidence and not profile_has_supported_domains)
        profile["_gemini_company_call"] = gemini_company_call
        if gemini_company_call:
            logger.info("Gemini company classification input evidence_count=%d evidence_chars=%d", len(evidence), sum(len(str(item.get("evidence") or item.get("title") or "")) for item in evidence))
            prompt = ("Classify this company using only supplied evidence. Never invent facts; broad category is not definitive. "
                      "Unknown fields must be empty/null. Competitors need explicit evidence. Return JSON object with primary_industry, "
                      "sub_industries, business_domains, products_services, technologies, business_keywords, competitors, target_markets, "
                      "relevant_geographies, regulatory_domains. Input: " + json.dumps({"company": {k: company.get(k) for k in ("company_name", "business_category", "business_type", "city", "state", "website")}, "website_evidence": evidence}, ensure_ascii=False))
            try:
                response = await gemini._generate_content_with_retry(prompt, {"response_mime_type": "application/json"})
                extracted = _parse_company_intelligence(response.text)
                logger.info("Gemini company classification output=%s", {key: extracted.get(key) for key in ("primary_industry", "sub_industries", "business_domains", "products_services", "technologies", "business_keywords", "competitors", "target_markets", "regulatory_domains", "relevant_geographies")})
                for key in ("primary_industry", "sub_industries", "business_domains", "products_services", "technologies", "business_keywords", "competitors", "target_markets", "relevant_geographies", "regulatory_domains"):
                    if key == "primary_industry" and extracted.get(key) is None:
                        continue
                    if key in extracted and isinstance(extracted[key], (str, list)):
                        if isinstance(extracted[key], list):
                            profile[key] = list(dict.fromkeys((profile.get(key) or []) + extracted[key]))
                        else:
                            profile[key] = extracted[key]
            except Exception as exc:
                logger.warning("Company intelligence enrichment failed (%s)", type(exc).__name__)
        logger.info("Company intelligence complete company=%s industry=%s domains=%s technologies=%s products_services=%s competitors=%s gemini_call=%s elapsed_seconds=%.2f", name, profile.get("primary_industry"), profile.get("business_domains"), profile.get("technologies"), profile.get("products_services"), profile.get("competitors"), gemini_company_call, time.perf_counter() - started)
        return profile


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", value)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _parse_company_intelligence(raw: str) -> Dict[str, Any]:
    """Tolerate common structured-output shape drift without accepting new facts."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw or "", flags=re.IGNORECASE)
    payload = json.loads(cleaned)
    if isinstance(payload, list):
        payload = payload[0] if payload and isinstance(payload[0], dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    list_fields = ("sub_industries", "business_domains", "products_services", "technologies", "business_keywords", "competitors", "target_markets", "relevant_geographies", "regulatory_domains")
    for key in list_fields:
        value = payload.get(key)
        if value is None:
            payload[key] = []
        elif isinstance(value, str):
            payload[key] = [value.strip()] if value.strip() else []
        elif isinstance(value, list):
            payload[key] = [str(item.get("name") or item.get("value") or "").strip() if isinstance(item, dict) else str(item).strip() for item in value]
            payload[key] = [value for value in payload[key] if value]
        else:
            payload[key] = []
    for key in ("primary_industry",):
        if not isinstance(payload.get(key), str):
            payload[key] = None
    return CompanyIntelligenceSchema.model_validate(payload).model_dump()


def _parse_development_insights(raw: str, items: List[Dict[str, Any]], profile: Dict[str, Any]):
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw or "", flags=re.IGNORECASE)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        payload = None
        for match in re.finditer(r"[\[{]", cleaned):
            try:
                payload, _ = decoder.raw_decode(cleaned[match.start():])
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            raise
    rows = payload if isinstance(payload, list) else payload.get("insights", payload.get("results", [])) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    allowed_types = {"tender", "rfp", "rfq", "eoi", "RFP", "RFQ", "EOI", "contract", "procurement", "partnership", "expansion", "investment", "infrastructure", "market_opportunity", "regulatory_opportunity", "none"}
    allowed_relevance = {"high", "medium", "low", "none"}
    normalized = []
    company_name = profile.get("company_name") or "the company"
    business_domain = next(iter(profile.get("business_domains") or profile.get("technologies") or ["its verified business domains"]), "its verified business domains")
    for index, item in enumerate(items):
        row = rows[index] if index < len(rows) and isinstance(rows[index], dict) else {}
        title = str(item.get("title") or "This development")
        what_happened = str(row.get("what_happened") or row.get("summary") or row.get("headline") or title).strip()
        implication = str(row.get("implication") or row.get("why_it_matters") or "").strip()
        if not implication:
            implication = (f"This may be relevant to {company_name} because its verified work includes {business_domain}. "
                           "The source does not establish a direct contract or confirmed commercial benefit.")
        opportunity_type = str(row.get("opportunity_type") or "none").strip().lower().replace(" ", "_").replace("-", "_")
        if opportunity_type in {"market", "market_opportunity", "business_opportunity"}:
            opportunity_type = "market_opportunity"
        elif opportunity_type in {"regulatory", "policy_opportunity"}:
            opportunity_type = "regulatory_opportunity"
        elif opportunity_type.upper() in {"RFP", "RFQ", "EOI"}:
            opportunity_type = opportunity_type.upper()
        if opportunity_type not in allowed_types:
            opportunity_type = "none"
        opportunity_relevance = str(row.get("opportunity_relevance") or "none").strip().lower()
        if opportunity_relevance not in allowed_relevance:
            opportunity_relevance = "none"
        try:
            confidence = max(0.0, min(1.0, float(row.get("confidence", .5))))
        except (TypeError, ValueError):
            confidence = .5
        try:
            score = max(0.0, min(1.0, float(row.get("business_opportunity_score", row.get("opportunity_score", 0.0)))))
        except (TypeError, ValueError):
            score = 0.0
        normalized.append({"what_happened": what_happened, "implication": implication, "opportunity_type": opportunity_type, "opportunity_relevance": opportunity_relevance, "business_opportunity_score": score, "confidence": confidence})
    return DevelopmentInsightBatchSchema.model_validate({"insights": normalized}).insights


def _deterministic_profile_enrichment(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only domain terms explicitly present in website/public source evidence."""
    evidence_text = " ".join(str(item.get("evidence") or "") + " " + str(item.get("title") or "") for item in profile.get("evidence", [])).lower()
    supported = {
                "technology consulting": ("technology consulting", "IT consulting", "digital consulting"),
        "consulting": ("consulting", "consultancy", "consulting services"),
        "management consulting": ("management consulting", "business consulting"),
        "enterprise transformation": ("enterprise transformation", "business transformation", "operating model transformation"),
        "digital transformation": ("digital transformation", "digital modernization"),
        "cybersecurity": ("cybersecurity", "cyber security", "security advisory"),
        "artificial intelligence": ("artificial intelligence", "generative ai", "artificial intelligence (ai)", r"\bai\b"),
        "cloud computing": ("cloud computing", "cloud transformation", "cloud services", "cloud solutions"),
        "data analytics": ("data analytics", "data and analytics", "advanced analytics"),
        "enterprise technology": ("enterprise technology", "enterprise systems", "enterprise platforms"),
        "sap": (r"\bsap\b", "s/4hana", "sap ai consulting"),
        "risk advisory": ("risk advisory", "risk consulting", "risk management"),
        "financial advisory": ("financial advisory", "financial consulting"),
        "tax services": ("tax services", "tax advisory", "tax consulting"),
        "audit and assurance": ("audit and assurance", "audit services", "assurance services"),
        "human capital consulting": ("human capital", "workforce transformation"),
        "sustainability consulting": ("sustainability consulting", "climate consulting", "sustainability services"),
    }
    matches = []
    for label, phrases in supported.items():
        if any(re.search(phrase, evidence_text) for phrase in phrases):
            matches.append(label)
    domains = list(profile.get("business_domains") or [])
    domains.extend(matches)
    profile["business_domains"] = list(dict.fromkeys(domains))
    profile["sub_industries"] = list(dict.fromkeys((profile.get("sub_industries") or []) + matches))
    technology_terms = {"artificial intelligence", "cloud computing", "cybersecurity", "data analytics", "enterprise technology", "sap"}
    profile["technologies"] = list(dict.fromkeys((profile.get("technologies") or []) + [term.title() for term in matches if term in technology_terms]))
    profile["products_services"] = list(dict.fromkeys((profile.get("products_services") or []) + [term.title() for term in matches if any(key in term for key in ("consulting", "advisory", "services"))]))
    profile["business_keywords"] = list(dict.fromkeys((profile.get("business_keywords") or []) + [term.title() for term in matches]))
    if any(term in matches for term in ("consulting", "technology consulting", "management consulting", "risk advisory", "financial advisory")):
        profile["primary_industry"] = "Consulting & Professional Services"
    return profile


class DevelopmentService:
    def __init__(self):
        self.sources = []
        if os.getenv("DEVELOPMENTS_GDELT_ENABLED", "true").lower() not in {"0", "false", "no"}:
            self.sources.append(GDELTSource())
        if os.getenv("DEVELOPMENTS_GOOGLE_NEWS_ENABLED", "true").lower() not in {"0", "false", "no"}:
            self.sources.append(GoogleNewsSource())
        if os.getenv("NEWSAPI_KEY"):
            self.sources.append(NewsAPISource())
        if os.getenv("THE_GUARDIAN_API_KEY") or os.getenv("GUARDIAN_API_KEY"):
            self.sources.append(GuardianSource())
        self.intelligence = CompanyIntelligenceService()
        self.query_builder = QueryBuilder(MAX_QUERIES)
        self.nearby_resolver = NearbyLocationResolver()

    async def _get_db_company(self, company_id: str, db: Any) -> Optional[Dict[str, Any]]:
        if db is None:
            return None
        try:
            result = db.execute(text("SELECT id, company_name, city, state, business_category, business_type, website FROM general_info WHERE id = :company_id"), {"company_id": company_id})
            result = await result if inspect.isawaitable(result) else result
        except Exception as exc:
            logger.exception("Failed to load company profile")
            raise HTTPException(status_code=500, detail="Company lookup failed.") from exc
        row = result.first() if hasattr(result, "first") else None
        if row is None:
            return None
        if hasattr(row, "_mapping"):
            return {key: row._mapping.get(key) for key in ("id", "company_name", "city", "state", "business_category", "business_type", "website")}
        return dict(zip(("id", "company_name", "city", "state", "business_category", "business_type", "website"), row))

    async def fetch_company_developments(self, company_id: str, db: Any = None, limit: int = 10, days: int = 7, category: Optional[str] = None) -> Dict[str, Any]:
        try:
            UUID(str(company_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="company_id must be a valid UUID.") from exc
        company = await self._get_db_company(str(company_id), db)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found.")
        request_started = time.perf_counter()
        intelligence_started = time.perf_counter()
        profile_task = asyncio.create_task(self.intelligence.build_profile(company))
        nearby_enabled = os.getenv("DEVELOPMENTS_NEARBY_ENABLED", "true").lower() not in {"0", "false", "no"}
        nearby_limit = int(load_development_config().get("company_aware_scoring", {}).get("nearby_location_limit", 6))
        async def timed_nearby_lookup():
            nearby_started = time.perf_counter()
            try:
                places = await asyncio.wait_for(self.nearby_resolver.resolve(company.get("city"), company.get("state"), nearby_limit), timeout=2.8)
            except Exception as exc:
                logger.info("Nearby location discovery timed out or failed (%s)", type(exc).__name__)
                places = []
            logger.info("Development timing stage=nearby_locations elapsed_seconds=%.2f count=%d", time.perf_counter() - nearby_started, len(places))
            return places
        nearby_task = asyncio.create_task(timed_nearby_lookup()) if nearby_enabled else None
        profile = await profile_task
        logger.info("Development timing stage=company_intelligence elapsed_seconds=%.2f", time.perf_counter() - intelligence_started)
        query_context = build_company_query_context(company)
        profile.update({"city": company.get("city"), "state": company.get("state"), "business_category": company.get("business_category")})
        profile["nearby_locations"] = await nearby_task if nearby_task else []
        self.query_builder.max_queries = min(30, max(self.query_builder.max_queries, int(limit * 1.5)))
        queries = self.query_builder.build(profile)
        query_counts: Dict[str, int] = {}
        for query in queries:
            query_counts[query["type"].value] = query_counts.get(query["type"].value, 0) + 1
        logger.info("Development queries generated count=%d by_type=%s", len(queries), query_counts)
        logger.debug("Development queries company=%s context=%s queries=%s", company.get("company_name"), {key: profile.get(key) for key in ("primary_industry", "business_domains", "technologies", "competitors", "nearby_locations")}, queries)
        semaphores = {
            source.source_id: asyncio.Semaphore(max(1, GDELT_CONCURRENCY if source.source_id == "gdelt_doc" else SOURCE_CONCURRENCY))
            for source in self.sources
        }
        disabled_sources = set()
        source_failures: Dict[str, int] = {}
        async def fetch_one(source, query_info):
            async with semaphores[source.source_id]:
                if source.source_id in disabled_sources:
                    return [], 0.0
                started = time.perf_counter()
                timeout = GDELT_TIMEOUT if source.source_id == "gdelt_doc" else SOURCE_TIMEOUT
                try:
                    result = await asyncio.wait_for(source.fetch({**query_context, **profile, "days": days, "search_query": query_info["query"]}), timeout=timeout)
                    source_failures[source.source_id] = 0
                    return result, time.perf_counter() - started
                except Exception as exc:
                    source_failures[source.source_id] = source_failures.get(source.source_id, 0) + 1
                    if source_failures[source.source_id] >= 3:
                        disabled_sources.add(source.source_id)
                        logger.warning("Development source circuit opened source=%s after repeated failures", source.source_name)
                    raise exc
        calls = [(source, query_info) for source in self.sources for query_info in queries]
        source_started = time.perf_counter()
        results = await asyncio.gather(*(fetch_one(source, query_info) for source, query_info in calls), return_exceptions=True)
        raw_items, used = [], set()
        source_counts: Dict[str, int] = {}
        source_seconds: Dict[str, float] = {}
        for (source, query_info), result in zip(calls, results):
            if isinstance(result, Exception):
                logger.warning("Development source %s request failed (%s)", source.source_name, type(result).__name__)
                continue
            result, elapsed = result
            source_seconds[source.source_name] = source_seconds.get(source.source_name, 0.0) + elapsed
            if result:
                source_counts[source.source_name] = source_counts.get(source.source_name, 0) + len(result)
                for item in result[:MAX_RESULTS_PER_QUERY]:
                    if isinstance(item, dict):
                        raw_items.append({**item, "query_type": query_info["type"].value, "discovery_query": query_info["query"], "query_priority": query_info["priority"], "source_result": item})
                used.add(source.source_name)
        logger.info("Development source retrieval results=%s aggregate_request_seconds=%s raw_candidate_count=%d wall_seconds=%.2f", source_counts, {key: round(value, 2) for key, value in source_seconds.items()}, len(raw_items), time.perf_counter() - source_started)
        processing_started = time.perf_counter()
        items = [normalize_development_record(item, {**query_context, **profile}) for item in raw_items if isinstance(item, dict)]
        deduped = deduplicate_developments(items)
        logger.info("Development retrieval completed: raw=%d normalized=%d deduplicated=%d", len(raw_items), len(items), len(deduped))
        for item in deduped:
            classify_development(item, profile)
        ranked_all = rank_development_items(deduped, {**query_context, **profile})
        ranked = [item for item in ranked_all if item.get("relevance_score", 0.0) >= MIN_RELEVANCE_SCORE]
        relevance_filtered_count = len(ranked)
        logger.info("Development ranking completed: ranked=%d above_threshold=%d threshold=%.2f", len(ranked_all), relevance_filtered_count, MIN_RELEVANCE_SCORE)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        ranked = [item for item in ranked if not item.get("published_at") or _within_days(item["published_at"], cutoff)]
        date_filtered_count = len(ranked)
        if category:
            ranked = [item for item in ranked if category.lower() in {str(item.get("category", "")).lower(), str(item.get("event_type", "")).lower()}]
        selected = select_diverse_developments(ranked, max(1, min(limit, 20)))
        logger.info("Development pipeline counts raw=%d normalized=%d deduplicated=%d relevant=%d within_requested_days=%d selected=%d", len(raw_items), len(items), len(deduped), relevance_filtered_count, date_filtered_count, len(selected))
        logger.info("Development timing stage=normalize_dedupe_rank_select elapsed_seconds=%.2f", time.perf_counter() - processing_started)
        for item in selected:
            item["what_happened"] = item.get("summary") or item.get("title")
            item["implication"] = None
            item["opportunity_relevance"] = "high" if item.get("business_opportunity_score", 0) >= .75 else "medium" if item.get("business_opportunity_score", 0) >= .4 else "none"
        gemini = _get_gemini_service()
        insight_items = selected[:MAX_GEMINI_CANDIDATES]
        gemini_insight_call = bool(insight_items and gemini and gemini.is_available())
        if gemini_insight_call:
            gemini_started = time.perf_counter()
            articles = [{"index": index, "title": item.get("title"), "summary": str(item.get("summary") or "")[:500], "published_at": item.get("published_at"), "source_name": item.get("source_name"), "event_type": item.get("event_type")} for index, item in enumerate(insight_items)]
            prompt = ("Return JSON object {insights:[{what_happened:string,implication:string,opportunity_type:string,opportunity_relevance:string,business_opportunity_score:number,confidence:number}]}, one item for each input article in order. Keep what_happened to one short sentence and implication to at most 40 words. "
                      "Use only the supplied article and company evidence; do not invent facts, relationships or financial impact. "
                      "Implication must explain why this company may care and state uncertainty when evidence is limited. Do not claim the company will win or benefit. "
                      "Only classify a direct tender/RFP opportunity if source evidence describes an actual procurement notice; otherwise use market_opportunity or none and conditional wording. Confidence measures interpretation confidence, not future probability. "
                      "opportunity_type must be one of tender, RFP, RFQ, EOI, contract, procurement, partnership, expansion, investment, infrastructure, market_opportunity, regulatory_opportunity, none. "
                      "opportunity_relevance must be high, medium, low, or none. business_opportunity_score is 0..1 and must be supported by the article, with 0 meaning no identifiable opportunity. "
                      + json.dumps({"company": {k: profile.get(k) for k in ("company_name", "primary_industry", "business_domains", "products_services", "technologies", "business_keywords", "regulatory_domains", "city", "state")}, "articles": [{**article, "development_type": insight_items[idx].get("development_type"), "opportunity_type": insight_items[idx].get("opportunity_type"), "business_opportunity_score": insight_items[idx].get("business_opportunity_score")} for idx, article in enumerate(articles)]}, ensure_ascii=False))
            try:
                from app.ai.llm import genai
                generation_config = genai.GenerationConfig(response_mime_type="application/json", response_schema=GeminiDevelopmentInsightBatchSchema, max_output_tokens=2500, temperature=0.2)
                response = await asyncio.wait_for(gemini._generate_content_with_retry(prompt, generation_config), timeout=float(os.getenv("DEVELOPMENTS_GEMINI_TIMEOUT", "24")))
                insights = _parse_development_insights(response.text, insight_items, profile)
                for item, insight in zip(insight_items, insights):
                    item["what_happened"] = insight.what_happened or item["what_happened"]
                    item["implication"] = insight.implication
                    item["confidence"] = insight.confidence
                    if insight.opportunity_type != "none":
                        item["opportunity_type"] = insight.opportunity_type
                    evidence_cap = _evidence_opportunity_score(item, profile)
                    item["business_opportunity_score"] = round(max(float(item.get("business_opportunity_score", 0.0)), min(insight.business_opportunity_score, evidence_cap)), 4)
                    item["opportunity_relevance"] = _opportunity_relevance(item["business_opportunity_score"])
            except Exception as exc:
                logger.warning("Development insight generation failed type=%s detail=%s", type(exc).__name__, str(exc)[:240])
            logger.info("Development timing stage=gemini_batch elapsed_seconds=%.2f candidates=%d", time.perf_counter() - gemini_started, len(insight_items))
        for item in selected:
            if not item.get("implication"):
                item["implication"] = _fallback_company_implication(item, profile)
        response_items = [{"title": i.get("title") or "Untitled development", "summary": i.get("summary"), "what_happened": i.get("what_happened"), "implication": i.get("implication"), "source_name": i.get("source_name") or "Unknown source", "source_url": i.get("source_url"), "published_at": i.get("published_at"), "city": i.get("city"), "state": i.get("state"), "location": {"city": i.get("city"), "state": i.get("state")}, "source": {"name": i.get("source_name") or "Unknown source", "url": i.get("source_url")}, "category": i.get("development_type") or "domain", "development_type": i.get("development_type") or "domain", "opportunity_type": i.get("opportunity_type") or "none", "opportunity_relevance": i.get("opportunity_relevance", "none"), "business_opportunity_score": i.get("business_opportunity_score", 0.0), "event_type": i.get("event_type") or "other", "relevance": "high" if i.get("relevance_score", 0) >= 0.75 else "medium" if i.get("relevance_score", 0) >= 0.5 else "low", "relevance_score": i.get("relevance_score", 0.0)} for i in selected]
        public_context = {"industry": profile.get("primary_industry"), "sub_industries": profile.get("sub_industries", []), "business_domains": profile.get("business_domains", []), "technologies": profile.get("technologies", []), "products_services": profile.get("products_services", [])}
        distribution: Dict[str, int] = {}
        for item in selected:
            key = item.get("development_type", "domain")
            distribution[key] = distribution.get(key, 0) + 1
        logger.info("Development final category_distribution=%s gemini_calls=%d total_latency_seconds=%.2f", distribution, int(profile.get("_gemini_company_call", False)) + int(gemini_insight_call), time.perf_counter() - request_started)
        return DevelopmentResponse(company={"id": str(company["id"]), "name": company["company_name"], "city": company.get("city"), "state": company.get("state"), "business_category": company.get("business_category")}, company_context=public_context, retrieved_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), sources=sorted(used), items=response_items).model_dump()


def _within_days(value: str, cutoff: datetime) -> bool:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except (ValueError, TypeError):
        return True


def classify_development(item: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Classify why an article matters, retaining discovery-query evidence."""
    text_value = " ".join(str(item.get(key) or "") for key in ("title", "summary", "event_type")).lower()
    query_type = item.get("query_type") or "domain"
    event_type = item.get("event_type") or "other"
    domain_terms = _profile_domain_terms(profile)
    domain_match = any(_contains_term(text_value, term) for term in domain_terms)
    tender_evidence = event_type in {"government_tender", "tender_corrigendum"} or any(term in text_value for term in ("tender", "rfp", "request for proposal", "rfq", "request for quotation", "expression of interest", "eoi", "procurement notice", "invites bids"))
    if tender_evidence:
        item["development_type"] = "tender"
        item["opportunity_type"] = ("RFP" if "rfp" in text_value or "request for proposal" in text_value else "RFQ" if "rfq" in text_value or "request for quotation" in text_value else "EOI" if "eoi" in text_value or "expression of interest" in text_value else "tender")
        item["business_opportunity_score"] = .95 if domain_match else .30
    elif event_type == "contract_award" or any(term in text_value for term in ("contract awarded", "contract award", "wins contract", "contract signed")):
        item["development_type"] = "government" if any(term in text_value for term in ("government", "ministry", "public sector")) else "competitor"
        item["opportunity_type"] = "contract"
        item["business_opportunity_score"] = .75 if domain_match else .30
    else:
        company_name = str(profile.get("company_name") or "").lower()
        competitors = [str(value).lower() for value in (profile.get("competitors") or [])]
        government_signal = any(term in text_value for term in ("government", "ministry", "public sector", "municipal", "state authority", "department of", "govt sets up", "govt launches"))
        local_city = str(profile.get("city") or "").lower()
        nearby_match = any(str(value).lower() in text_value for value in profile.get("nearby_locations") or [])
        state_name = str(profile.get("state") or "").lower()
        if company_name and company_name in text_value:
            item["development_type"] = "company"
        elif any(value in text_value for value in competitors):
            item["development_type"] = "competitor"
        elif local_city and local_city in text_value and domain_match:
            item["development_type"] = "local"
        elif nearby_match and domain_match:
            item["development_type"] = "nearby"
        elif state_name and state_name in text_value and domain_match:
            item["development_type"] = "state"
        elif government_signal and domain_match:
            item["development_type"] = "government"
        elif any(term in text_value for term in ("regulation", "regulatory", "compliance rules", "policy change", "notification", "mandatory", "incident reporting")) and domain_match:
            item["development_type"] = "regulatory"
        elif "infrastructure" in text_value and domain_match:
            item["development_type"] = "infrastructure"
        elif any(term in text_value for term in ("investment", "funding", "capital", "expansion")) and domain_match:
            item["development_type"] = "investment"
        elif domain_match and (any(term in text_value for term in ("international", "cross-border", "global partnership", "worldwide")) or ("india" in text_value and re.search(r"\b(?:uk|u\.s\.|usa|united states|united kingdom)\b", text_value))):
            item["development_type"] = "global"
        elif domain_match and event_type == "technology":
            item["development_type"] = "technology"
        elif domain_match and any(term in text_value for term in ("partnership", "market opportunity", "new market", "adoption program")):
            item["development_type"] = "opportunity"
        elif domain_match and query_type == "technology":
            item["development_type"] = "technology"
        elif domain_match and query_type in {"national", "global"}:
            item["development_type"] = query_type
        elif domain_match:
            item["development_type"] = "domain"
        else:
            item["development_type"] = "domain"
        item["opportunity_type"] = "none"
        item["business_opportunity_score"] = 0.0
        signals = ("government initiative", "government project", "funding program", "investment", "infrastructure program", "adoption program", "new market", "partnership", "expansion")
        if domain_match and (any(signal in text_value for signal in signals) or (government_signal and "project" in text_value)):
            item["opportunity_type"] = "market_opportunity"
            item["business_opportunity_score"] = .60
    item["category"] = item["development_type"]
    item["business_opportunity_score"] = max(float(item.get("business_opportunity_score", 0.0)), _evidence_opportunity_score(item, profile))
    item["opportunity_relevance"] = _opportunity_relevance(item["business_opportunity_score"])
    return item


def _opportunity_relevance(score: float) -> str:
    return "high" if score >= .75 else "medium" if score >= .5 else "low" if score > 0 else "none"


def _evidence_opportunity_score(item: Dict[str, Any], profile: Dict[str, Any]) -> float:
    evidence = " ".join(str(item.get(key) or "") for key in ("title", "summary", "event_type")).lower()
    domain_match = any(_contains_term(evidence, term) for term in _profile_domain_terms(profile))
    direct_procurement = any(term in evidence for term in ("tender", "rfp", "request for proposal", "rfq", "request for quotation", "expression of interest", " eoi", "procurement notice", "invites bids"))
    contract = any(term in evidence for term in ("contract awarded", "contract award", "wins contract", "contract signed"))
    market_signal = any(term in evidence for term in ("government initiative", "funding program", "investment", "infrastructure program", "adoption program", "new market", "partnership", "expansion"))
    if domain_match and direct_procurement:
        return .95
    if domain_match and contract:
        return .85
    if domain_match and market_signal:
        return .60
    if domain_match and "project" in evidence and any(term in evidence for term in ("government", "ministry", "state authority", "public sector")):
        return .60
    return 0.0


def _fallback_company_implication(item: Dict[str, Any], profile: Dict[str, Any]) -> str:
    title = str(item.get("title") or "This development")
    company = str(profile.get("company_name") or "The company")
    evidence = " ".join(str(item.get(key) or "") for key in ("title", "summary")).lower()
    domains = (profile.get("business_domains") or []) + (profile.get("technologies") or [])
    matched_domain = next((term for term in domains if _contains_term(evidence, str(term).lower())), None)
    domain = matched_domain or next(iter(profile.get("business_domains") or []), profile.get("primary_industry") or "its industry")
    location = ", ".join(value for value in (item.get("city"), item.get("state")) if value)
    place = f" in {location}" if location else ""
    return (f"Because {company} has verified {domain} capabilities, this development{place} may affect its market or service planning. "
            "The source does not establish a direct contract or confirmed commercial benefit.")


def _profile_domain_terms(profile: Dict[str, Any]) -> List[str]:
    terms = [str(value).lower() for key in ("primary_industry", "business_category", "business_domains", "sub_industries", "technologies", "products_services", "business_keywords") for value in ([profile.get(key)] if isinstance(profile.get(key), str) else (profile.get(key) or [])) if value]
    expanded = list(terms)
    aliases = {"artificial intelligence": ("ai", "genai", "generative ai"), "cybersecurity": ("cyber security",), "cyber security": ("cybersecurity",), "enterprise transformation": ("digital transformation",), "digital transformation": ("enterprise transformation",)}
    for term in terms:
        expanded.extend(aliases.get(term, ()))
    return list(dict.fromkeys(term for term in expanded if len(term.strip()) > 2 or term == "ai"))


def _contains_term(text_value: str, term: str) -> bool:
    if term == "ai":
        return bool(re.search(r"\bai\b", text_value))
    return term in text_value


def select_diverse_developments(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Select by configured result families so exact-company stories cannot dominate."""
    if limit <= 0:
        return []
    mix = load_development_config().get("company_aware_scoring", {}).get("development_mix", {})
    families = {
        "external_domain": {"domain", "technology"},
        "local_nearby_state": {"local", "nearby", "state"},
        "government_opportunity": {"government", "tender", "opportunity"},
        "competitor": {"competitor"},
        "national_global": {"regulatory", "investment", "infrastructure", "national", "global"},
        "company": {"company"},
    }
    weights = {key: float(mix.get(key, 0.0)) for key in families}
    raw = {key: limit * weight for key, weight in weights.items()}
    quotas = {key: int(value) for key, value in raw.items()}
    remaining = limit - sum(quotas.values())
    for key in sorted(raw, key=lambda family: raw[family] - quotas[family], reverse=True)[:remaining]:
        quotas[key] += 1
    selected, used = [], set()
    for family, categories in families.items():
        matches = [item for item in items if item.get("development_type") in categories]
        take = quotas.get(family, 0)
        if family == "company":
            take = min(take, max(1, int(limit * .15)))
        selected.extend(matches[:take])
        used.update(id(item) for item in matches[:take])
    # Diversity is a preference: consume any remaining external candidate
    # before using extra company-only coverage to fill the response.
    fill_order = [row for row in items if row.get("development_type") != "company"] + [row for row in items if row.get("development_type") == "company"]
    for item in fill_order:
        if len(selected) >= limit:
            break
        if id(item) not in used:
            selected.append(item)
            used.add(id(item))
    return sorted(selected, key=lambda row: (row.get("relevance_score", 0), row.get("published_at") or ""), reverse=True)
