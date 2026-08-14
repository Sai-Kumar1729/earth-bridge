"""
Overture Maps + Satellite Spatial Join Module
==============================================
Zero-copy DuckDB spatial overlay linking Overture Maps building footprints 
with satellite indices (NDVI, NDWI, LSWI, NBR, LST Thermal Anomaly).
"""

from typing import Dict, Any, List, Optional
import numpy as np
import geopandas as gpd
from shapely.geometry import box

from .overture_engine import ProductionOvertureEngine
from .zonal_stats import compute_building_zonal_stats
from .spectral_indexes import SpectralIndexCalculator


class OvertureGEEJoin:
    """Spatial join engine for Overture building footprints with satellite indices."""
    
    def __init__(self):
        self.overture_engine = ProductionOvertureEngine()
    
    def query_overture_bbox(
        self,
        parquet_path: str,
        bbox: List[float],
        limit: int = 1000
    ) -> gpd.GeoDataFrame:
        """Query Overture Maps building footprints within a bounding box."""
        return self.overture_engine.fetch_building_footprints(bbox=bbox, limit=limit)
    
    def enrich_buildings_with_satellite_index(
        self,
        buildings_gdf: gpd.GeoDataFrame,
        index_array: np.ndarray,
        index_name: str = "satellite_index",
        bbox: Optional[List[float]] = None
    ) -> gpd.GeoDataFrame:
        """Enrich building footprints with satellite index zonal statistics."""
        return compute_building_zonal_stats(
            buildings_gdf, 
            index_array, 
            index_name=index_name,
            bbox=bbox
        )


def spatial_join_overture_satellite(
    parquet_path: str,
    bbox: List[float],
    index_array: np.ndarray,
    index_name: str = "satellite_index",
    limit: int = 1000
) -> gpd.GeoDataFrame:
    """
    Convenience function to perform full spatial join pipeline.
    
    Args:
        parquet_path: Path to Overture Parquet file (or S3 URL)
        bbox: [min_lon, min_lat, max_lon, max_lat]
        index_array: 2D numpy array of computed satellite index
        index_name: Name for the index column in output
        limit: Maximum number of building footprints to process
    
    Returns:
        Enriched GeoDataFrame with building footprints and zonal statistics
    """
    joiner = OvertureGEEJoin()
    
    # Fetch buildings
    buildings = joiner.query_overture_bbox(parquet_path, bbox, limit=limit)
    
    # Enrich with satellite index
    enriched = joiner.enrich_buildings_with_satellite_index(
        buildings, 
        index_array, 
        index_name=index_name,
        bbox=bbox
    )
    
    return enriched