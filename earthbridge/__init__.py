"""
earth-bridge
============
Universal Spatial Intelligence SDK & Cross-Cloud STAC Engine.
Bridging Google Earth Engine, Microsoft Planetary Computer, and Overture Maps Foundation.

Usage on any OS (macOS, Linux, Windows):
    import earthbridge as eb

    # 1. Launch Interactive Studio UI
    eb.studio() # or eb.launch()

    # 2. Query 250m Tree Canopy Cover & Vegetation (Zero Auth)
    canopy = eb.get_modis_tcc(bbox=[78.0, 15.0, 80.0, 17.0])

    # 3. Compute Spectral Index (NDVI, NDWI, LSWI, NBR, NDBI)
    ndvi = eb.compute_index(bbox=[78.4, 17.3, 78.5, 17.4], index="ndvi")

    # 4. Zero-Auth STAC Search (Planetary Computer)
    scenes = eb.search_stac(bbox=[78.4, 17.3, 78.5, 17.4], collection="sentinel-2-l2a")

    # 5. Fetch Building Footprints (Overture Maps)
    buildings = eb.fetch_buildings(bbox=[78.4, 17.3, 78.5, 17.4], limit=1000)

    # 6. Memory-Safe State Partitioning
    tiles = eb.partition(bbox=[76.0, 12.0, 85.0, 20.0], tile_size=0.1)

    # 7. Export Datasets & Executive Policy Reports
    eb.export(buildings, format="geojson", output="results.geojson")
    eb.report(buildings, city_name="Analysis Region", output="report.html")
"""

__version__ = "0.2.0"

import os
import sys
from typing import List, Optional, Dict, Any

from .gee_engine import GEEOperationEngine
from .stac_engine import ProductionSTACEngine
from .overture_engine import ProductionOvertureEngine
from .zonal_stats import compute_building_zonal_stats
from .spectral_indexes import SpectralIndexCalculator, compute_ndvi, compute_ndwi
from .report_engine import ExecutiveReportEngine, PolicyReportGenerator, generate_policy_report
from .tiling import partition_state_bbox
from .stac_reader import ZeroAuthSTACReader, search_stac_anonymously
from .exporter import export_open_dataset, OpenDatasetExporter
from .gee_stac import GEEToSTACConverter, export_gee_to_stac

# Global singleton instances for instant keyword access
_stac_engine = None
_overture_engine = None
_gee_engine = None

def get_stac_engine() -> ProductionSTACEngine:
    global _stac_engine
    if _stac_engine is None:
        _stac_engine = ProductionSTACEngine()
    return _stac_engine

def get_overture_engine() -> ProductionOvertureEngine:
    global _overture_engine
    if _overture_engine is None:
        _overture_engine = ProductionOvertureEngine()
    return _overture_engine

def get_gee_engine() -> GEEOperationEngine:
    global _gee_engine
    if _gee_engine is None:
        _gee_engine = GEEOperationEngine()
    return _gee_engine

# High-Level Intuitive Keyword APIs
def studio(port: int = 8000, open_browser: bool = True):
    """Launch the interactive earth-bridge Web Studio on any OS."""
    from .cli import launch_studio
    launch_studio(port=port, open_browser=open_browser)

launch = studio  # Alias

def get_modis_tcc(bbox: List[float]) -> Dict[str, Any]:
    """Fetch MODIS 250m Tree Canopy Cover / Vegetation Index for any ROI (Zero Auth)."""
    return get_stac_engine().fetch_modis_tcc_from_mpc(bbox=bbox)

def search_stac(bbox: List[float], collection: str = "sentinel-2-l2a", max_items: int = 5) -> Dict[str, Any]:
    """Zero-auth STAC search against Microsoft Planetary Computer."""
    return search_stac_anonymously(bbox=bbox, collection=collection, max_items=max_items)

def fetch_buildings(bbox: List[float], limit: int = 1000):
    """Fetch Overture Maps building polygons using zero-copy cloud DuckDB."""
    return get_overture_engine().fetch_building_footprints(bbox=bbox, limit=limit)

def partition(bbox: List[float], tile_size: float = 0.1) -> List[Dict[str, Any]]:
    """Partition a large state/district bounding box into memory-safe sub-grid tiles."""
    return partition_state_bbox(bbox=bbox, tile_size_deg=tile_size)

def compute_index(bbox: List[float], index: str = "ndvi") -> Dict[str, Any]:
    """Compute spectral indices (NDVI, NDWI, LSWI, NBR, NDBI) on satellite rasters."""
    import numpy as np
    raster = get_stac_engine().fetch_raster_for_bbox(bbox=bbox, index_type=index)
    
    if raster.get("status") != "success":
        return {
            **raster,
            "index": index.upper(),
            "index_array": None,
            "index_mean": None,
            "index_min": None,
            "index_max": None,
            "index_std": None
        }

    band_map = {
        "ndvi": ("nir_array", "red_array"),
        "ndwi": ("green_array", "nir_array"),
        "lswi": ("nir_array", "swir_array"),
        "nbr": ("nir_array", "swir2_array"),
        "ndbi": ("swir_array", "nir_array"),
    }
    
    itype = index.lower()
    a_key, b_key = band_map.get(itype, ("nir_array", "red_array"))
    a, b = raster.get(a_key), raster.get(b_key)
    
    if a is None or b is None:
        return {
            **raster,
            "index_array": None,
            "index": index.upper(),
            "error": f"Required bands ({a_key}, {b_key}) for {index.upper()} unavailable from this scene."
        }

    fn_map = {
        "ndvi": SpectralIndexCalculator.ndvi,
        "ndwi": SpectralIndexCalculator.ndwi,
        "lswi": SpectralIndexCalculator.lswi,
        "nbr": SpectralIndexCalculator.nbr,
        "ndbi": SpectralIndexCalculator.ndbi,
    }
    calc_fn = fn_map.get(itype, SpectralIndexCalculator.ndvi)
    index_array = calc_fn(a, b)
    
    valid = index_array[~np.isnan(index_array)] if index_array is not None else np.array([])
    
    return {
        "status": "success",
        "provider": raster.get("provider"),
        "index": index.upper(),
        "index_array": index_array,
        "index_mean": float(np.nanmean(valid)) if len(valid) > 0 else None,
        "index_min": float(np.nanmin(valid)) if len(valid) > 0 else None,
        "index_max": float(np.nanmax(valid)) if len(valid) > 0 else None,
        "index_std": float(np.nanstd(valid)) if len(valid) > 0 else None,
        "pixels_processed": len(valid)
    }

def export(data, format: str = "geojson", output: str = "output.geojson"):
    """Export spatial dataset to GeoJSON, Parquet, or CSV."""
    return export_open_dataset(gdf=data, output_format=format, output_path=output)

def report(data, city_name: str = "Analysis Region", output: str = "report.html"):
    """Generate executive HTML sustainability and policy report."""
    return generate_policy_report(gdf=data, city_name=city_name, output_path=output)

__all__ = [
    "studio",
    "launch",
    "get_modis_tcc",
    "search_stac",
    "fetch_buildings",
    "partition",
    "compute_index",
    "export",
    "report",
    "GEEOperationEngine",
    "ProductionSTACEngine",
    "ProductionOvertureEngine",
    "compute_building_zonal_stats",
    "SpectralIndexCalculator",
    "compute_ndvi",
    "compute_ndwi",
    "ExecutiveReportEngine",
    "PolicyReportGenerator",
    "generate_policy_report",
    "partition_state_bbox",
    "ZeroAuthSTACReader",
    "search_stac_anonymously",
    "export_open_dataset",
    "OpenDatasetExporter",
    "GEEToSTACConverter",
    "export_gee_to_stac",
]
