"""
Example 04: Hyderabad City Spatial Analysis & Executive Policy Report
====================================================================
Runs earth-bridge processing across Hyderabad and generates a visual HTML policy report for urban planners.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from earthbridge import (
    compute_ndvi,
    export_gee_to_stac,
    spatial_join_overture_satellite,
    partition_state_bbox,
    search_stac_anonymously,
    export_open_dataset,
    generate_policy_report
)

def main():
    print("==================================================================")
    print(" [earth-bridge] Hyderabad City Spatial Analysis Test")
    print("==================================================================")

    hyderabad_bbox = [78.35, 17.30, 78.55, 17.50]
    print(f"\n1. Target Region: Hyderabad, India")
    print(f"   Bounding Box: {hyderabad_bbox}")

    print("\n2. Querying Microsoft Planetary Computer STAC (Zero-Auth)...")
    stac_res = search_stac_anonymously(hyderabad_bbox, collection="sentinel-2-l2a")
    print(f"   Status: {stac_res['status']} | Found {stac_res['count']} Sentinel-2 scenes.")

    print("\n3. Partitioning Hyderabad region into sub-grid tiles...")
    tiles = partition_state_bbox(hyderabad_bbox, tile_size_deg=0.05)
    print(f"   Generated {len(tiles)} sub-grid tiles (~5.5km x 5.5km each).")

    building_limit = 500
    print(f"\n4. Running Overture Building Footprint Spatial Join (Limit: {building_limit} footprints)...")
    nir_band = np.random.uniform(0.3, 0.75, (100, 100))
    red_band = np.random.uniform(0.05, 0.22, (100, 100))
    ndvi_raster = compute_ndvi(nir_band, red_band)

    enriched_gdf = spatial_join_overture_satellite(
        parquet_path="overture_hyderabad.geojson",
        bbox=hyderabad_bbox,
        index_array=ndvi_raster,
        index_name="hyderabad_building_greenery_index"
    )
    print(f"   Successfully processed {len(enriched_gdf)} Overture building footprints in Hyderabad!")

    print("\n5. Generating Executive Policy Map Dashboard (.html)...")
    report_file = generate_policy_report(
        enriched_gdf,
        city_name="Hyderabad",
        output_filepath="hyderabad_executive_report.html"
    )
    print(f"   -> Executive Visual Map Report: {report_file}")

    print("\n6. Exporting Open Spatial Datasets...")
    stac_path = export_gee_to_stac(
        item_id="hyderabad_sentinel2_ndvi_2026",
        bbox=hyderabad_bbox,
        geometry={"type": "Polygon", "coordinates": [[[78.35, 17.30], [78.55, 17.30], [78.55, 17.50], [78.35, 17.50], [78.35, 17.30]]]},
        datetime_utc="2026-08-01T05:30:00Z",
        assets={"ndvi": {"href": "https://earthengine.googleapis.com/v1/projects/hyderabad/ndvi.tif", "type": "image/tiff"}},
        output_path="hyderabad_stac_item.json"
    )
    print(f"   -> STAC Item JSON: {os.path.abspath(stac_path)}")

    exports = export_open_dataset(enriched_gdf, base_filename="hyderabad_enriched_buildings")
    print(f"   -> Enriched GeoJSON: {exports['geojson']}")
    
    print("\n==================================================================")
    print(" SUCCESS: Hyderabad City Test Completed Successfully!")
    print("==================================================================")

if __name__ == "__main__":
    main()
