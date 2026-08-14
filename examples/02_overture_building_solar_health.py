"""
Example 02: Spatial Join Overture Maps Buildings with Satellite Indices
========================================================================
Demonstrates zero-copy DuckDB + GeoPandas join running on a standard 16GB RAM laptop.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from earthbridge.spectral_indexes import compute_ndvi
from earthbridge.overture_join import spatial_join_overture_satellite

def main():
    print("=== earth-bridge Example 02: Overture Buildings + Satellite Join ===")
    
    # 1. Synthesize 2D Satellite Raster Arrays (NIR & RED bands)
    nir_band = np.random.uniform(0.3, 0.8, (100, 100))
    red_band = np.random.uniform(0.05, 0.2, (100, 100))
    
    # 2. Compute NDVI Index
    ndvi_raster = compute_ndvi(nir_band, red_band)
    print(f"Calculated 100x100 NDVI Raster. Mean NDVI: {np.mean(ndvi_raster):.4f}")
    
    # 3. Spatial Join with Overture Maps building polygons
    bbox = [78.400, 17.300, 78.500, 17.400]
    enriched_gdf = spatial_join_overture_satellite(
        parquet_path="synthetic_overture.geojson",
        bbox=bbox,
        index_array=ndvi_raster,
        index_name="vegetation_greenery_score"
    )
    
    print("\nEnriched Overture Building Footprints GeoDataFrame:")
    print(enriched_gdf[["id", "subtype", "height", "vegetation_greenery_score"]].head(5))

if __name__ == "__main__":
    main()
