from __future__ import annotations
import logging
from typing import Any, Dict, List
from development.sources.google_news import GoogleNewsSource

logger = logging.getLogger(__name__)


class OfficialIndiaGovSource(GoogleNewsSource):
    source_id = "official_india_gov"
    source_name = "Official India Government (PIB/RBI/SEBI/MCA)"

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        original_query = query_context.get("search_query", "")
        # Create a copy so we don't modify the context for other sources
        context = dict(query_context)
        site_filters = "site:pib.gov.in OR site:rbi.org.in OR site:sebi.gov.in OR site:mca.gov.in"
        context["search_query"] = f"({site_filters}) {original_query}"
        
        items = await super().fetch(context)
        for item in items:
            item["source_id"] = self.source_id
            item["source_name"] = "Indian Government Official Portal"
            item["category"] = "regulatory"
            item["event_type"] = "government_update"
        return items


class IndianTenderPortalSource(GoogleNewsSource):
    source_id = "indian_tender_portals"
    source_name = "Indian Government Procurement Portals"

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        original_query = query_context.get("search_query", "")
        context = dict(query_context)
        site_filters = "site:eprocure.gov.in OR site:gem.gov.in OR site:tenders.gov.in"
        context["search_query"] = f"({site_filters}) {original_query}"
        
        items = await super().fetch(context)
        for item in items:
            item["source_id"] = self.source_id
            item["source_name"] = "Indian Tender Portal"
            item["category"] = "tender"
            item["event_type"] = "government_tender"
        return items
