"""Configuration-backed procurement adapter; disabled until a portal is verified as automatable."""
from typing import Any, Dict, List

from development.config import get_procurement_sources_for_state
from development.sources.base import BaseDevelopmentSource


class ProcurementSource(BaseDevelopmentSource):
    source_id = "procurement"
    source_name = "Government procurement portals"

    def configured_sources(self, state: str) -> List[Dict[str, Any]]:
        return get_procurement_sources_for_state(state)

    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # The supplied directory is mostly portal landing pages, not supported search APIs.
        # Returning no records is safer than making undocumented or fabricated API calls.
        return []
