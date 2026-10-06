import pytest
from development.service import _parse_development_insights
from development.ranking import deduplicate_developments
import json

def test_parse_mapping_out_of_order():
    items = [
        {"candidate_id": "dev_001", "title": "Article A", "summary": "Summary A"},
        {"candidate_id": "dev_002", "title": "Article B", "summary": "Summary B"},
        {"candidate_id": "dev_003", "title": "Article C", "summary": "Summary C"}
    ]
    profile = {"company_name": "Test Co"}
    raw_response = json.dumps([
        {"candidate_id": "dev_003", "what_happened": "Happened C", "implication": "Imp C", "opportunity_type": "none"},
        {"candidate_id": "dev_001", "what_happened": "Happened A", "implication": "Imp A", "opportunity_type": "none"},
        {"candidate_id": "dev_002", "what_happened": "Happened B", "implication": "Imp B", "opportunity_type": "none"}
    ])
    
    results = _parse_development_insights(raw_response, items, profile)
    
    assert results[0].candidate_id == "dev_001"
    assert results[0].what_happened == "Happened A"
    assert results[1].candidate_id == "dev_002"
    assert results[1].what_happened == "Happened B"
    assert results[2].candidate_id == "dev_003"
    assert results[2].what_happened == "Happened C"

def test_parse_mapping_missing_result():
    items = [
        {"candidate_id": "dev_001", "title": "Article A", "summary": "Summary A"},
        {"candidate_id": "dev_002", "title": "Article B", "summary": "Summary B"},
        {"candidate_id": "dev_003", "title": "Article C", "summary": "Summary C"}
    ]
    profile = {"company_name": "Test Co", "business_domains": ["Tech"]}
    raw_response = json.dumps([
        {"candidate_id": "dev_001", "what_happened": "Happened A", "implication": "Imp A", "opportunity_type": "none"},
        {"candidate_id": "dev_003", "what_happened": "Happened C", "implication": "Imp C", "opportunity_type": "none"}
    ])
    
    results = _parse_development_insights(raw_response, items, profile)
    
    assert results[0].candidate_id == "dev_001"
    assert results[0].what_happened == "Happened A"
    
    assert results[1].candidate_id == "dev_002"
    assert "Article B" in results[1].what_happened or "Summary B" in results[1].what_happened
    assert "This may be relevant to Test Co" in results[1].implication
    
    assert results[2].candidate_id == "dev_003"
    assert results[2].what_happened == "Happened C"

def test_event_deduplication_across_publishers():
    items = [
        {
            "title": "RailTel AI Workshop 2026 explores infrastructure, cybersecurity and responsible AI adoption",
            "published_at": "2026-10-05T10:00:00Z",
            "source_name": "Source A",
            "source_url": "http://a.com"
        },
        {
            "title": "RailTel AI Workshop 2026 Explores Practical AI Adoption In Governance",
            "published_at": "2026-10-05T12:00:00Z",
            "source_name": "Source B",
            "source_url": "http://b.com"
        }
    ]
    deduped = deduplicate_developments(items)
    
    assert len(deduped) == 1
    sources = deduped[0].get("sources", [])
    assert len(sources) == 2
    source_names = [s["name"] for s in sources]
    assert "Source A" in source_names
    assert "Source B" in source_names
