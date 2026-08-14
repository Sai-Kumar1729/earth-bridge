"""
Zero-Auth STAC Query & COG Metadata Reader
==========================================
Queries Microsoft Planetary Computer STAC anonymously with zero credentials or API keys.
"""

from typing import List, Dict, Any, Optional
import urllib.request
import json

class ZeroAuthSTACReader:
    """Anonymous STAC searcher & asset reader using Microsoft Planetary Computer public API."""

    STAC_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1/search"

    @classmethod
    def search_planetary_stac(
        cls,
        bbox: List[float],
        datetime_range: str = "2024-01-01/2026-12-31",
        collection: str = "sentinel-2-l2a",
        max_items: int = 5
    ) -> Dict[str, Any]:
        """
        Performs zero-authentication STAC API search against Microsoft Planetary Computer.

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]
            datetime_range: ISO range string (e.g. "2024-01-01/2026-12-31")
            collection: STAC collection ID (default: "sentinel-2-l2a")
            max_items: Maximum items to return
        """
        payload = {
            "bbox": bbox,
            "datetime": datetime_range,
            "collections": [collection],
            "limit": max_items,
            "query": {"eo:cloud_cover": {"lt": 20}}
        }

        req = urllib.request.Request(
            cls.STAC_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "earth-bridge/0.2.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                features = data.get("features", [])
                if not features:
                    return {
                        "status": "no_data",
                        "count": 0,
                        "items": [],
                        "message": f"No scenes found in {collection} for bbox {bbox} within {datetime_range} with <20% cloud cover."
                    }
                return {
                    "status": "success",
                    "count": len(features),
                    "items": [
                        {
                            "id": feat.get("id"),
                            "datetime": feat.get("properties", {}).get("datetime"),
                            "cloud_cover": feat.get("properties", {}).get("eo:cloud_cover"),
                            "assets": list(feat.get("assets", {}).keys())
                        }
                        for feat in features
                    ]
                }
        except Exception as e:
            return {
                "status": "error",
                "count": 0,
                "items": [],
                "message": f"STAC API query error: {e}"
            }

def search_stac_anonymously(
    bbox: List[float],
    datetime_range: str = "2024-01-01/2026-12-31",
    collection: str = "sentinel-2-l2a",
    max_items: int = 5
) -> Dict[str, Any]:
    return ZeroAuthSTACReader.search_planetary_stac(
        bbox=bbox,
        datetime_range=datetime_range,
        collection=collection,
        max_items=max_items
    )
