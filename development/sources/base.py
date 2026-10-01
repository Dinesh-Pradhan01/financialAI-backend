from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseDevelopmentSource(ABC):
    source_id: str = "base"
    source_name: str = "Base source"

    @abstractmethod
    async def fetch(self, query_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError
