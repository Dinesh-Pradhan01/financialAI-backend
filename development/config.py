import json
from pathlib import Path
from typing import Any, Dict, List

CONFIG_PATH = Path(__file__).resolve().parent / "india_developments_data_sources.json"


def load_development_config() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_config_name(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().lower()
    return "".join(ch for ch in cleaned if ch.isalnum())


def get_source_by_id(source_id: str) -> Dict[str, Any]:
    config = load_development_config()
    for source in config.get("global_sources", []):
        if source.get("source_id") == source_id:
            return source
    return {}


def get_procurement_sources_for_state(state_name: str) -> List[Dict[str, Any]]:
    config = load_development_config()
    if not state_name:
        return []
    target = normalize_config_name(state_name)
    for entry in config.get("states_and_union_territories", []):
        if normalize_config_name(entry.get("name", "")) == target:
            return entry.get("procurement_sources", [])
    return []
