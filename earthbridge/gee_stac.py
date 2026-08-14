"""
Google Earth Engine to STAC (SpatioTemporal Asset Catalog) Converter Module
========================================================================
Dynamically converts GEE Image/ImageCollection metadata & download links into official STAC 1.0.0 JSON specification.
"""

from typing import Dict, Any, List, Optional, Union
import datetime
import json

class GEEToSTACConverter:
    """Converts Google Earth Engine metadata structures into standardized STAC Item JSON."""

    def __init__(self, item_id_prefix: str = "gee-asset"):
        self.item_id_prefix = item_id_prefix

    def image_to_stac_item(
        self,
        item_id: str,
        bbox: List[float],
        geometry: Dict[str, Any],
        datetime_utc: Union[str, datetime.datetime],
        assets: Dict[str, Dict[str, Any]],
        properties: Optional[Dict[str, Any]] = None,
        stac_extensions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Builds a compliant STAC 1.0.0 Item Dictionary from GEE Image parameters.

        Args:
            item_id: Unique identifier for the STAC item.
            bbox: [min_lon, min_lat, max_lon, max_lat]
            geometry: GeoJSON Geometry dictionary
            datetime_utc: UTC datetime string (ISO format) or datetime object
            assets: Dict of STAC assets (e.g. band download URLs or COG URLs)
            properties: Additional metadata key-values (e.g., cloud_cover, platform)
            stac_extensions: List of STAC extension URIs (e.g., EO, Raster)
        """
        if isinstance(datetime_utc, datetime.datetime):
            dt_str = datetime_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            dt_str = str(datetime_utc)

        props = properties or {}
        props["datetime"] = dt_str
        props["gee:provider"] = "Google Earth Engine"

        stac_item = {
            "type": "Feature",
            "stac_version": "1.0.0",
            "stac_extensions": stac_extensions or [
                "https://stac-extensions.github.io/eo/v1.1.0/schema.json"
            ],
            "id": f"{self.item_id_prefix}-{item_id}",
            "geometry": geometry,
            "bbox": bbox,
            "properties": props,
            "links": [
                {
                    "rel": "self",
                    "type": "application/json",
                    "href": f"./{self.item_id_prefix}-{item_id}.json"
                },
                {
                    "rel": "root",
                    "type": "application/json",
                    "href": "../catalog.json"
                }
            ],
            "assets": assets
        }
        return stac_item

    def export_stac_json(self, stac_item: Dict[str, Any], output_filepath: str) -> str:
        """Saves a STAC Item dictionary to a JSON file."""
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(stac_item, f, indent=2)
        return output_filepath

def export_gee_to_stac(
    item_id: str,
    bbox: List[float],
    geometry: Dict[str, Any],
    datetime_utc: str,
    assets: Dict[str, Dict[str, Any]],
    output_path: str,
    properties: Optional[Dict[str, Any]] = None
) -> str:
    converter = GEEToSTACConverter()
    item = converter.image_to_stac_item(
        item_id=item_id,
        bbox=bbox,
        geometry=geometry,
        datetime_utc=datetime_utc,
        assets=assets,
        properties=properties
    )
    return converter.export_stac_json(item, output_path)
