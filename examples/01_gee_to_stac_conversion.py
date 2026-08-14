"""
Example 01: Convert Google Earth Engine Asset Metadata to STAC 1.0.0 Standard
=============================================================================
"""

import sys
import os

# Add parent dir to path for direct package execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from earthbridge.gee_stac import export_gee_to_stac

def main():
    print("=== earth-bridge Example 01: GEE asset to STAC Item ===")
    output_path = "gee_sample_stac.json"
    
    file_path = export_gee_to_stac(
        item_id="sentinel2_hyderabad_2026",
        bbox=[78.400, 17.300, 78.500, 17.400],
        geometry={
            "type": "Polygon",
            "coordinates": [[[78.4, 17.3], [78.5, 17.3], [78.5, 17.4], [78.4, 17.4], [78.4, 17.3]]]
        },
        datetime_utc="2026-08-01T05:30:00Z",
        assets={
            "B4_red": {"href": "https://earthengine.googleapis.com/v1/projects/b4.tif", "type": "image/tiff"},
            "B8_nir": {"href": "https://earthengine.googleapis.com/v1/projects/b8.tif", "type": "image/tiff"}
        },
        output_path=output_path,
        properties={
            "eo:cloud_cover": 2.1,
            "platform": "Sentinel-2B",
            "earthbridge:index": "NDVI"
        }
    )
    
    print(f"-> Successfully generated STAC 1.0.0 file at: {os.path.abspath(file_path)}")

if __name__ == "__main__":
    main()
