import re
from typing import Any, Dict, Iterable, List, Optional

DOMAIN_KEYWORDS = {
    "technology": ["technology", "software", "it", "digital", "cloud", "ai", "cyber", "data", "saas", "platform"],
    "manufacturing": ["manufacturing", "factory", "production", "industrial", "machinery", "plant", "supply chain"],
    "logistics": ["logistics", "transport", "supply chain", "warehousing", "fleet", "shipping", "distribution"],
    "finance": ["finance", "banking", "lending", "payments", "insurance", "investment", "capital"],
    "healthcare": ["healthcare", "hospital", "medical", "pharma", "biotech", "clinical"],
    "real estate": ["real estate", "property", "construction", "housing", "infrastructure", "commercial space"],
    "retail": ["retail", "consumer", "ecommerce", "store", "shopping", "brand"],
    "energy": ["energy", "power", "renewables", "solar", "wind", "oil", "gas"],
    "agriculture": ["agriculture", "farm", "food", "fertilizer", "agri", "crop"],
}


def _sanitize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _tokenize(value: Optional[str]) -> List[str]:
    if not value:
        return []
    tokens = re.split(r"[^\w]+", value.lower())
    return [token.strip() for token in tokens if token.strip()]


def _coalesce(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return None


def build_company_query_context(company: Dict[str, Any]) -> Dict[str, Any]:
    city = _sanitize_text(company.get("city"))
    state = _sanitize_text(company.get("state"))
    category = _sanitize_text(company.get("business_category"))
    company_name = _sanitize_text(company.get("company_name"))

    geographic_terms = []
    if city:
        geographic_terms.append(city)
    geographic_terms.append(state)

    topic_terms = []
    if company_name:
        topic_terms.extend(_tokenize(company_name))
    if category:
        topic_terms.extend(_tokenize(category))

    category_key = (category or "").lower()
    matching_domain_keywords = []
    for key, keywords in DOMAIN_KEYWORDS.items():
        if key in category_key or any(token in category_key for token in _tokenize(category or "")):
            matching_domain_keywords.extend(keywords)
    if matching_domain_keywords:
        topic_terms.extend(matching_domain_keywords)

    return {
        "company_name": company_name,
        "city": city,
        "state": state,
        "business_category": category,
        "geographic_terms": geographic_terms,
        "topic_terms": topic_terms,
        "location_terms": [term for term in geographic_terms if term],
        "domain_terms": list(dict.fromkeys(term.lower() for term in topic_terms if term and len(term) > 2)),
    }


def build_topic_terms(query_context: Dict[str, Any]) -> List[str]:
    category = query_context.get("business_category")
    terms = []
    if category:
        terms.extend([part.strip() for part in re.split(r"[\s/&,-]+", category) if part.strip()])
    if query_context.get("company_name"):
        terms.extend([part.strip() for part in re.split(r"[\s/&,-]+", query_context["company_name"]) if part.strip()])
    terms.extend(query_context.get("topic_terms", []))
    terms = [term for term in terms if term and len(term) > 2]
    return list(dict.fromkeys(terms))


def _quote_term(value: Optional[str]) -> str:
    if not value:
        return '""'
    return f'"{value.strip()}"'


def build_gdelt_query(query_context: Dict[str, Any]) -> str:
    city = query_context.get("city")
    state = query_context.get("state")
    company_name = query_context.get("company_name")
    category = query_context.get("business_category")

    location_terms = [term for term in [city, state] if term]
    geolocation = " OR ".join(_quote_term(term) for term in location_terms if term)
    if not geolocation:
        raise ValueError("At least one location term is required for GDELT queries.")

    company_terms = [term for term in build_topic_terms(query_context) if term and term.lower() not in {"and", "or", "the", "for"}]
    company_clause = " OR ".join(_quote_term(term) for term in company_terms[:8] if term)
    if company_name:
        company_clause = f"{company_clause} OR {_quote_term(company_name)}" if company_clause else _quote_term(company_name)
    if category:
        company_clause = f"{company_clause} OR {_quote_term(category)}" if company_clause else _quote_term(category)

    development_terms = ["expansion", "development", "investment", "facility", "project", "factory", "launch", "tender", "policy", "acquisition", "growth"]
    event_clause = " OR ".join(_quote_term(term) for term in development_terms)

    return f"({geolocation}) AND ({company_clause}) AND ({event_clause})"


def build_google_news_query(query_context: Dict[str, Any]) -> str:
    city = query_context.get("city")
    state = query_context.get("state")
    company_name = query_context.get("company_name")
    category = query_context.get("business_category")

    primary_location = city or state
    location_clause = _quote_term(primary_location)

    topic_terms = build_topic_terms(query_context)
    domain_terms = [term for term in topic_terms if term.lower() not in {"and", "or", "the", "for", "government", "project", "investment", "tender"}]
    topic_clause = " OR ".join(term for term in domain_terms[:6] if term)
    if not topic_clause:
        topic_clause = "technology OR software OR investment"

    company_clause = _quote_term(company_name) if company_name else ""
    category_clause = _quote_term(category) if category else ""
    exact_query = " OR ".join(part for part in [company_clause, category_clause, topic_clause] if part)

    return f"{location_clause} ({exact_query}) AND (expansion OR investment OR project OR launch OR facility OR acquisition OR development)"


def build_company_queries(profile: Dict[str, Any], max_queries: int = 12) -> List[str]:
    """Build a bounded, evidence-led query set across company and business dimensions."""
    name = (profile.get("company_name") or "").strip()
    industry = (profile.get("primary_industry") or profile.get("business_category") or "").strip()
    city, state = profile.get("city"), profile.get("state")
    groups = [
        [f'"{name}"', f'"{name}" {industry}'] if name else [],
        [f'"{term}" India' for term in (profile.get("sub_industries") or [])[:2]] + ([f'"{industry}" India'] if industry else []),
        [f'"{city}" {industry}', f'"{state}" {industry}', f'"{city}" "{name}"'] if city or state else [],
        [f'"{term}" {industry} India' for term in (profile.get("competitors") or [])[:2]],
        [f'"{term}" {industry}' for term in (profile.get("technologies") or [])[:2]],
        [f'"{industry}" regulation India', f'"{industry}" policy India'] if industry else [],
        [f'"{industry}" tender India', f'"{industry}" procurement India'] if industry else [],
        [f'"{industry}" investment India', f'"{industry}" funding OR expansion'] if industry else [],
        [f'"{city}" infrastructure {industry}', f'"{state}" infrastructure {industry}'] if industry else [],
        [f'"{industry}" global', f'"{industry}" national India'] if industry else [],
    ]
    result = []
    seen = set()
    # Reserve initial coverage across dimensions before filling categories with extras.
    for offset in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if offset >= len(group):
                continue
            query = group[offset]
            query = " ".join(query.split())
            if query and query.casefold() not in seen:
                seen.add(query.casefold())
                result.append(query)
            if len(result) >= max(1, max_queries):
                return result
    return result
