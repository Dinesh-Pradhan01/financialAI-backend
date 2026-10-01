"""Resolve nearby Indian towns from OpenStreetMap; lookup failures never block news discovery."""
import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class NearbyLocationResolver:
    async def resolve(self, city: str | None, state: str | None, limit: int = 6) -> List[str]:
        if not city or not state:
            return []
        headers = {"User-Agent": "SpotliteDevelopments/1.0 (company development discovery)"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(1.3), headers=headers) as client:
                response = await client.get("https://nominatim.openstreetmap.org/search", params={"city": city, "state": state, "country": "India", "format": "jsonv2", "limit": 1})
                response.raise_for_status()
                matches = response.json()
                if not matches:
                    return []
                lat, lon = float(matches[0]["lat"]), float(matches[0]["lon"])
                # Search OSM place nodes around the city's center; avoid broad arbitrary radius crawls.
                query = f"[out:json][timeout:1];(node(around:35000,{lat},{lon})[place~\"^(city|town)$\"];);out tags 20;"
                nearby_response = await client.post("https://overpass-api.de/api/interpreter", data={"data": query})
                nearby_response.raise_for_status()
                places = nearby_response.json().get("elements", [])
                names = []
                for place in places:
                    name = (place.get("tags") or {}).get("name:en") or (place.get("tags") or {}).get("name")
                    if name and name.casefold() != city.casefold() and name.casefold() not in {item.casefold() for item in names}:
                        names.append(name)
                    if len(names) >= max(1, min(limit, 10)):
                        break
                return names
        except Exception as exc:
            logger.info("Nearby location discovery unavailable (%s)", type(exc).__name__)
            return []
