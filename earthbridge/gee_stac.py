"""
Build STAC 1.0.0 Item JSON from supplied values.

This is a document builder, not a reader. It does not connect to Earth Engine
or introspect an asset; every field in the output originates from a supplied
argument. It was previously named `GEEToSTACConverter`, which implied that it
could convert an Earth Engine asset into STAC independently. It cannot, and that
capability is not present in this release.
"""

from typing import Dict, Any, List, Optional, Union
import datetime
import json


class STACItemBuilder:
    """Assembles STAC 1.0.0 Item dictionaries."""

    def __init__(self, item_id_prefix: str = "earthbridge"):
        self.item_id_prefix = item_id_prefix

    def build(
        self,
        item_id: str,
        bbox: List[float],
        geometry: Dict[str, Any],
        datetime_utc: Union[str, datetime.datetime],
        assets: Dict[str, Dict[str, Any]],
        properties: Optional[Dict[str, Any]] = None,
        stac_extensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build a STAC Item.

        Args:
            item_id: Identifier, prefixed with this builder's prefix.
            bbox: [min_lon, min_lat, max_lon, max_lat].
            geometry: GeoJSON geometry.
            datetime_utc: ISO 8601 string or datetime.
            assets: STAC asset dictionaries keyed by asset name.
            properties: Extra item properties.
            stac_extensions: Extension schema URIs.
        """
        if isinstance(datetime_utc, datetime.datetime):
            dt_str = datetime_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            dt_str = str(datetime_utc)

        props = dict(properties or {})
        props["datetime"] = dt_str
        props.setdefault("processing:software", {"earth-bridge": "0.3.0"})

        return {
            "type": "Feature",
            "stac_version": "1.0.0",
            "stac_extensions": stac_extensions or [
                "https://stac-extensions.github.io/processing/v1.1.0/schema.json"
            ],
            "id": f"{self.item_id_prefix}-{item_id}",
            "geometry": geometry,
            "bbox": bbox,
            "properties": props,
            "links": [
                {"rel": "self", "type": "application/json",
                 "href": f"./{self.item_id_prefix}-{item_id}.json"},
                {"rel": "root", "type": "application/json", "href": "../catalog.json"},
            ],
            "assets": assets,
        }

    # Previous method name.
    def image_to_stac_item(self, *args, **kwargs) -> Dict[str, Any]:
        return self.build(*args, **kwargs)

    @staticmethod
    def write(stac_item: Dict[str, Any], output_filepath: str) -> str:
        """Write a STAC Item to a JSON file."""
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(stac_item, f, indent=2)
        return output_filepath

    def export_stac_json(self, stac_item: Dict[str, Any], output_filepath: str) -> str:
        return self.write(stac_item, output_filepath)


def build_stac_item(
    item_id: str,
    bbox: List[float],
    geometry: Dict[str, Any],
    datetime_utc: str,
    assets: Dict[str, Dict[str, Any]],
    output_path: str,
    properties: Optional[Dict[str, Any]] = None,
    item_id_prefix: str = "earthbridge",
) -> str:
    """Build a STAC Item and write it to `output_path`."""
    builder = STACItemBuilder(item_id_prefix=item_id_prefix)
    item = builder.build(
        item_id=item_id, bbox=bbox, geometry=geometry,
        datetime_utc=datetime_utc, assets=assets, properties=properties,
    )
    return builder.write(item, output_path)


# Previous names, kept so existing imports keep working.
GEEToSTACConverter = STACItemBuilder
export_gee_to_stac = build_stac_item
