import html
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any, Dict, Optional

VALID_EVENT_TYPES = {
    "government_tender",
    "tender_corrigendum",
    "contract_award",
    "policy",
    "infrastructure_project",
    "investment",
    "company_expansion",
    "technology",
    "regulatory_change",
    "public_safety",
    "other",
}

CITY_ALIASES = {
    "bengaluru": ("Bengaluru", "Karnataka"), "bangalore": ("Bengaluru", "Karnataka"),
    "mysuru": ("Mysuru", "Karnataka"), "mysore": ("Mysuru", "Karnataka"),
    "hubballi": ("Hubballi", "Karnataka"), "mangaluru": ("Mangaluru", "Karnataka"),
    "chennai": ("Chennai", "Tamil Nadu"), "hyderabad": ("Hyderabad", "Telangana"),
    "mumbai": ("Mumbai", "Maharashtra"), "pune": ("Pune", "Maharashtra"),
    "delhi": ("Delhi", "Delhi"), "new delhi": ("New Delhi", "Delhi"),
    "kolkata": ("Kolkata", "West Bengal"), "gurugram": ("Gurugram", "Haryana"),
    "gurgaon": ("Gurugram", "Haryana"), "noida": ("Noida", "Uttar Pradesh"),
    "kochi": ("Kochi", "Kerala"), "ahmedabad": ("Ahmedabad", "Gujarat"),
    "jaipur": ("Jaipur", "Rajasthan"), "lucknow": ("Lucknow", "Uttar Pradesh"),
}
STATE_NAMES = ("Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi")


def normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = html.unescape(str(value)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or None


def strip_html(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = html.unescape(str(value))
    cleaned = re.sub(r"<.*?>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def parse_published_at(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    try:
        dt = datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %Z")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue

    return None


def infer_event_type(title: str, summary: str, category: Optional[str]) -> str:
    text = f"{title or ''} {summary or ''} {category or ''}".lower()
    if any(term in text for term in ["tender", "eprocurement", "procurement", "bid", "rfq", "request for proposal"]):
        return "government_tender"
    if any(term in text for term in ["corrigendum", "amendment", "revision"]):
        return "tender_corrigendum"
    if any(term in text for term in ["contract award", "awarded", "contract signed", "vendor selected"]):
        return "contract_award"
    if any(term in text for term in ["policy", "scheme", "initiative", "regulation", "notification"]):
        return "policy"
    if any(term in text for term in ["infrastructure", "metro", "road", "airport", "power", "rail", "project"]):
        return "infrastructure_project"
    if any(term in text for term in ["investment", "funding", "capital", "commitment", "factory", "expansion"]):
        return "investment"
    if any(term in text for term in ["expansion", "plant", "factory", "new unit", "capacity", "launch"]):
        return "company_expansion"
    if any(term in text for term in ["technology", "ai", "software", "digital", "it", "cyber"]):
        return "technology"
    if any(term in text for term in ["regulatory", "compliance", "laws", "notification", "approval"]):
        return "regulatory_change"
    if any(term in text for term in ["safety", "surveillance", "security", "cctv", "camera"]):
        return "public_safety"
    return "other"


def normalize_development_record(raw_item: Dict[str, Any], query_context: Dict[str, Any]) -> Dict[str, Any]:
    title = normalize_text(raw_item.get("title") or raw_item.get("headline") or "Untitled development")
    summary = strip_html(raw_item.get("summary") or raw_item.get("description") or raw_item.get("excerpt") or "")
    source_name = normalize_text(raw_item.get("source_name") or raw_item.get("source") or "Unknown source") or "Unknown source"
    source_url = normalize_text(raw_item.get("source_url") or raw_item.get("url") or raw_item.get("link"))
    published_at = parse_published_at(raw_item.get("published_at") or raw_item.get("published") or raw_item.get("date") or raw_item.get("seendate"))

    category = normalize_text(raw_item.get("query_type") or raw_item.get("category") or "domain") or "domain"
    raw_event_type = raw_item.get("event_type")
    event_type = raw_event_type if raw_event_type in VALID_EVENT_TYPES and raw_event_type != "other" else infer_event_type(title or "", summary or "", raw_item.get("category"))
    if event_type not in VALID_EVENT_TYPES:
        event_type = "other"

    city, state = extract_location(title or "", summary or "", raw_item.get("city"), raw_item.get("state"))
    
    source_id = raw_item.get("source_id") or "unknown"
    discovery_source_map = {
        "google_news_rss": "Google News RSS",
        "gdelt_doc": "GDELT",
        "official_india_gov": "Google News RSS (Official Govt Filter)",
        "indian_tender_portals": "Google News RSS (Tenders Filter)",
        "newsapi": "NewsAPI",
        "guardian": "The Guardian"
    }
    discovery_source = discovery_source_map.get(source_id, source_id)
    
    original_source = source_name
    original_url = source_url
    
    return {
        "title": title,
        "summary": summary,
        "source_name": source_name,
        "source_url": source_url,
        "original_source": original_source,
        "original_url": original_url,
        "discovery_source": discovery_source,
        "published_at": published_at,
        "city": city,
        "state": state,
        "category": category,
        "event_type": event_type,
        "development_type": category,
        "query_type": normalize_text(raw_item.get("query_type")),
        "discovery_query": normalize_text(raw_item.get("discovery_query")),
        "query_priority": raw_item.get("query_priority", 0.5),
        "source_result": raw_item.get("source_result"),
        "source_id": source_id,
        "source_record_id": raw_item.get("source_record_id"),
        "canonical_url": raw_item.get("canonical_url") or source_url,
        "normalized_title": title or "",
    }


def extract_location(title: str, summary: str, city: Any = None, state: Any = None):
    """Return only source-supplied or explicitly recognized article locations."""
    text = f"{title} {summary}"
    resolved_city = normalize_text(city)
    resolved_state = normalize_text(state)
    if resolved_city is None:
        for alias, (canonical_city, canonical_state) in CITY_ALIASES.items():
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.IGNORECASE):
                resolved_city = canonical_city
                if resolved_state is None:
                    resolved_state = canonical_state
                break
    if resolved_state is None:
        for state_name in STATE_NAMES:
            if re.search(rf"(?<!\w){re.escape(state_name)}(?!\w)", text, re.IGNORECASE):
                resolved_state = state_name
                break
    return resolved_city, resolved_state
