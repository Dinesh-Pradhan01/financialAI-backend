import hashlib
import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from development.config import load_development_config
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


SOURCE_AUTHORITY = {
    "gdelt": 0.75,
    "google news rss": 0.7,
    "unknown": 0.4,
}
SCORING_WEIGHTS = load_development_config().get("scoring", {}).get("weights", {})
COMPANY_WEIGHTS = load_development_config().get("company_aware_scoring", {}).get("weights", {})


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    return " ".join(title.lower().split())


def _canonical_key(item: Dict[str, Any]) -> str:
    url = (item.get("source_url") or item.get("canonical_url") or "").strip()
    if url:
        try:
            parts = urlsplit(url)
            query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(("utm_", "fbclid", "gclid", "ocid"))])
            url = urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), query, ""))
        except ValueError:
            pass
        return f"url:{url.lower()}"
    title = _normalize_title(item.get("title") or "")
    if title:
        return f"title:{hashlib.sha256(title.encode('utf-8')).hexdigest()}"
    return f"source:{(item.get('source_name') or 'unknown').lower()}"


def deduplicate_developments(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_key: Dict[str, Dict[str, Any]] = {}
    title_groups: Dict[str, List[Any]] = {}

    for item in items:
        key = _canonical_key(item)
        title = _normalize_title(item.get("title") or "")
        published = str(item.get("published_at") or "")[:10]
        if title and published:
            words = set(re.findall(r"[a-z0-9]+", title))
            for existing_key, existing_title, existing_words in title_groups.get(published, []):
                similarity = SequenceMatcher(None, title, existing_title).ratio()
                overlap = len(words & existing_words) / max(1, len(words | existing_words))
                if similarity >= .93 and overlap >= .70:
                    key = existing_key
                    break
            else:
                title_groups.setdefault(published, []).append((key, title, words))
        current = best_by_key.get(key)
        if current is None:
            best_by_key[key] = item
            continue

        current_quality = (
            float(current.get("query_priority", 0.0)),
            bool(current.get("published_at")),
            len((current.get("summary") or "")),
            bool(current.get("source_url")),
            bool(current.get("title") or current.get("normalized_title")),
        )
        new_quality = (
            float(item.get("query_priority", 0.0)),
            bool(item.get("published_at")),
            len((item.get("summary") or "")),
            bool(item.get("source_url")),
            bool(item.get("title") or item.get("normalized_title")),
        )

        if new_quality > current_quality:
            best_by_key[key] = item

    ordered = list(best_by_key.values())
    ordered.sort(key=lambda row: (row.get("published_at") or "", row.get("title") or ""), reverse=True)
    return ordered


def _calculate_topic_relevance(item: Dict[str, Any], query_context: Dict[str, Any]) -> float:
    haystack = ((item.get("title") or "") + " " + (item.get("summary") or "") + " " + (item.get("category") or "")).lower()
    terms = list(query_context.get("topic_terms", []))
    terms += [query_context.get(key) for key in ("primary_industry", "business_category")]
    for key in ("sub_industries", "business_keywords", "products_services", "technologies", "competitors", "regulatory_domains"):
        terms += query_context.get(key, []) or []
    valid_terms = [term.lower() for term in terms if term and term.lower() not in {"none", "null"}]
    if not valid_terms:
        return 0.5
    matches = sum(1 for term in valid_terms if term.lower() in haystack)
    score = min(1.0, matches / max(1, len(valid_terms)))

    company_name = (query_context.get("company_name") or "").lower()
    if company_name and company_name in haystack:
        score += 0.25
    return min(1.0, score)


def _calculate_geographic_relevance(item: Dict[str, Any], query_context: Dict[str, Any]) -> float:
    haystack = ((item.get("title") or "") + " " + (item.get("summary") or "") + " " + (item.get("state") or "") + " " + (item.get("city") or "")).lower()
    city = (query_context.get("city") or "").lower()
    state = (query_context.get("state") or "").lower()
    if city and city in haystack:
        return 1.0
    if state and state in haystack:
        return 0.8
    nearby = _context_terms(query_context, "nearby_locations")
    if any(place in haystack for place in nearby):
        return 0.7
    return 0.3


def _calculate_recency(item: Dict[str, Any]) -> float:
    value = item.get("published_at")
    if not value:
        return 0.2
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.2
    now = datetime.now(timezone.utc)
    age_days = (now - dt).total_seconds() / 86400
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.8
    if age_days <= 14:
        return 0.6
    if age_days <= 30:
        return 0.4
    return 0.2


def _calculate_source_authority(item: Dict[str, Any]) -> float:
    source_name = (item.get("source_name") or "unknown").lower()
    source_id = (item.get("source_id") or "").lower()
    if "gdelt" in source_id or "gdelt" in source_name:
        return 0.75
    if "google_news" in source_id or "google news" in source_name:
        return 0.70
    if "procurement" in source_id:
        return 0.95
    return SOURCE_AUTHORITY.get(source_name, 0.5)


def _calculate_document_completeness(item: Dict[str, Any]) -> float:
    parts = [bool(item.get("title")), bool(item.get("summary")), bool(item.get("source_url")), bool(item.get("published_at"))]
    return sum(parts) / len(parts)


def score_development_item(item: Dict[str, Any], query_context: Dict[str, Any]) -> Dict[str, Any]:
    haystack = " ".join(str(item.get(key) or "") for key in ("title", "summary", "event_type", "development_type")).lower()
    company = str(query_context.get("company_name") or "").lower()
    company_relevance = 1.0 if company and company in haystack else 0.0
    domains = _context_terms(query_context, "primary_industry", "sub_industries", "business_domains")
    technologies = _context_terms(query_context, "technologies")
    services = _context_terms(query_context, "business_keywords", "products_services")
    competitors = _context_terms(query_context, "competitors")
    domain_relevance = _term_match(haystack, _expand_profile_terms(domains))
    business_relevance = max(_term_match(haystack, _expand_profile_terms(technologies)), _term_match(haystack, _expand_profile_terms(services)))
    competitor_relevance = _term_match(haystack, competitors)
    geography = _calculate_geographic_relevance(item, query_context)
    category = item.get("development_type") or item.get("query_type") or "domain"
    local_relevance = geography if category in {"local", "nearby", "state"} else 0.0
    government = 1.0 if any(t in haystack for t in ("government", "ministry", "public sector", "municipal", "state authority")) else 0.0
    opportunity = float(item.get("business_opportunity_score", 0.0))
    opportunity_text = " ".join(str(item.get(key) or "") for key in ("title", "summary", "event_type")).lower()
    if opportunity <= 0 and (domain_relevance or business_relevance):
        if item.get("opportunity_type") in {"tender", "RFP", "RFQ", "EOI", "procurement"} and any(token in opportunity_text for token in ("tender", "rfp", "rfq", "eoi", "procurement", "request for proposal")):
            opportunity = .95
        elif item.get("opportunity_type") == "contract" and any(token in opportunity_text for token in ("contract award", "contract awarded", "contract signed", "wins contract")):
            opportunity = .85
        elif item.get("opportunity_type") == "market_opportunity" and any(token in opportunity_text for token in ("investment", "partnership", "expansion", "government project", "government initiative", "funding", "new market")):
            opportunity = .60
    recency, authority, completeness = _calculate_recency(item), _calculate_source_authority(item), _calculate_document_completeness(item)
    # Company mentions are deliberately capped; external domain, business, and opportunity evidence leads.
    score = (domain_relevance * COMPANY_WEIGHTS.get("domain", .24)
             + business_relevance * COMPANY_WEIGHTS.get("business", .18)
             + opportunity * COMPANY_WEIGHTS.get("opportunity", .15)
             + geography * COMPANY_WEIGHTS.get("geography", .10)
             + recency * COMPANY_WEIGHTS.get("recency", .10)
             + authority * COMPANY_WEIGHTS.get("source_authority", .10)
             + max(company_relevance, competitor_relevance, government * .6) * COMPANY_WEIGHTS.get("company_competitor_government", .10))
    score += completeness * COMPANY_WEIGHTS.get("completeness", .02) + local_relevance * COMPANY_WEIGHTS.get("local_bonus", .01)
    score = max(0.0, min(1.0, score))
    item["relevance_score"] = round(score, 4)
    item["business_opportunity_score"] = round(opportunity, 4)
    item["relevance_breakdown"] = {"domain": domain_relevance, "business": business_relevance, "opportunity": opportunity, "geography": geography, "company": company_relevance, "competitor": competitor_relevance, "government": government}
    return item


def _context_terms(context: Dict[str, Any], *keys: str) -> List[str]:
    terms = []
    for key in keys:
        value = context.get(key) or []
        terms.extend([value] if isinstance(value, str) else value)
    return [str(term).lower() for term in terms if term and len(str(term).strip()) > 2]


def _term_match(haystack: str, terms: List[str]) -> float:
    if not terms:
        return 0.0
    # Best evidence phrase match rather than dividing by a long list of profile keywords.
    return 1.0 if any((bool(re.search(r"\b" + re.escape(term) + r"\b", haystack)) if len(term) <= 2 else term in haystack) for term in terms) else 0.0


def _expand_profile_terms(terms: List[str]) -> List[str]:
    expanded = list(terms)
    aliases = {"artificial intelligence": ("ai", "genai", "generative ai"), "cybersecurity": ("cyber security",), "cyber security": ("cybersecurity",), "enterprise transformation": ("digital transformation",), "digital transformation": ("enterprise transformation",), "consulting": ("consultancy", "consultant", "consultants")}
    for term in terms:
        expanded.extend(aliases.get(term, ()))
    return list(dict.fromkeys(expanded))


def _matches_company_domain(item: Dict[str, Any], query_context: Dict[str, Any]) -> bool:
    combined = " ".join([
        item.get("title") or "",
        item.get("summary") or "",
        item.get("category") or "",
        item.get("event_type") or "",
    ]).lower()
    item["_domain_match"] = _term_match(combined, _expand_profile_terms(_context_terms(query_context, "primary_industry", "sub_industries", "business_domains", "business_keywords", "products_services", "technologies")))
    item["_company_or_ecosystem_match"] = _term_match(combined, _context_terms(query_context, "company_name", "competitors"))
    is_relevant_opportunity = float(item.get("business_opportunity_score", 0.0)) >= .5 and item.get("opportunity_type") not in (None, "none")
    return bool(item["_domain_match"] or item["_company_or_ecosystem_match"] or is_relevant_opportunity)


def rank_development_items(items: Iterable[Dict[str, Any]], query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    scored = [score_development_item(item, query_context) for item in items if _matches_company_domain(item, query_context)]
    sorted_items = sorted(scored, key=lambda row: (row.get("relevance_score", 0.0), row.get("published_at") or ""), reverse=True)
    return sorted_items
