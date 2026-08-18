"""
Example 04 — Write a STAC 1.0.0 Item describing a result.

STACItemBuilder assembles the document from supplied values. It does not read an
Earth Engine asset or introspect a file; every field below originates from an
argument.

Run:  python examples/04_stac_item.py
"""

import json

from earthbridge import build_stac_item

BBOX = [78.40, 17.30, 78.50, 17.40]


def main() -> int:
    path = build_stac_item(
        item_id="hyderabad-ndvi-2026-summer",
        bbox=BBOX,
        geometry={
            "type": "Polygon",
            "coordinates": [[
                [BBOX[0], BBOX[1]], [BBOX[2], BBOX[1]],
                [BBOX[2], BBOX[3]], [BBOX[0], BBOX[3]], [BBOX[0], BBOX[1]],
            ]],
        },
        datetime_utc="2026-08-01T05:30:00Z",
        assets={
            "ndvi": {
                "href": "https://example.org/hyderabad_ndvi.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data"],
            }
        },
        properties={
            "eo:cloud_cover": 2.1,
            "platform": "sentinel-2b",
            "processing:lineage": (
                "Median of cloud-masked Sentinel-2 L2A scenes, SCL mask applied, "
                "normalised difference of B8 and B4."
            ),
        },
        output_path="stac_item.json",
    )

    print(f"Wrote {path}\n")
    with open(path, encoding="utf-8") as f:
        print(json.dumps(json.load(f), indent=2)[:700] + "\n...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
