"""
earth-bridge — define a region of interest and see what Earth observation data
exists over it.

Two kinds of result come out of this library, and the distinction matters:

  * **Tile layers** are rendered imagery for display. They work without any
    credentials, and they carry no retrievable pixel values.
  * **Statistics** are measured numbers over your region. These currently
    require Google Earth Engine, which computes them server-side.

Reading a numeric array directly from Planetary Computer COGs is not available
in this release; anonymous asset signing returns HTTP 409. Where that path is
requested, the library reports it rather than substituting a value.

Every result carries a `provenance` record naming the backend, collection,
scene, date and licence it came from.

    import earthbridge as eb

    # Which Sentinel-2 scenes cover this area?          (no credentials)
    scenes = eb.search_stac(bbox=[78.4, 17.3, 78.5, 17.4])

    # A MODIS NDVI tile layer for a map                 (no credentials)
    layer = eb.get_modis_ndvi(bbox=[78.0, 15.0, 80.0, 17.0])

    # Building footprints, with their source recorded   (no credentials)
    buildings = eb.fetch_buildings(bbox=[78.4, 17.3, 78.5, 17.4], limit=500)
    print(buildings["source"].unique())

    # A measured NDVI value over the region             (needs Earth Engine)
    ndvi = eb.compute_index(bbox=[78.4, 17.3, 78.5, 17.4], index="ndvi")

    # Launch the interactive Studio in a browser
    eb.studio()
"""

__version__ = "0.3.0"

from typing import List, Optional, Dict, Any

from .provenance import Provenance, PROVIDER_LICENSES
from .gee_engine import EarthEngineBackend, GEEOperationEngine
from .stac_engine import STACBackend, ProductionSTACEngine, COLLECTION_MAP
from .overture_engine import OvertureBackend, ProductionOvertureEngine
from .spectral_indexes import (
    SpectralIndexCalculator, compute_ndvi, compute_ndwi,
    compute_lswi, compute_nbr, compute_ndbi,
)
from .report_engine import write_map_report, generate_policy_report
from .tiling import split_bbox, partition_state_bbox
from .stac_reader import ZeroAuthSTACReader, search_stac_anonymously
from .exporter import export_open_dataset, OpenDatasetExporter
from .gee_stac import STACItemBuilder, build_stac_item, GEEToSTACConverter, export_gee_to_stac

_stac_backend: Optional[STACBackend] = None
_overture_backend: Optional[OvertureBackend] = None
_earth_engine: Optional[EarthEngineBackend] = None


def get_stac_engine() -> STACBackend:
    global _stac_backend
    if _stac_backend is None:
        _stac_backend = STACBackend()
    return _stac_backend


def get_overture_engine() -> OvertureBackend:
    global _overture_backend
    if _overture_backend is None:
        _overture_backend = OvertureBackend()
    return _overture_backend


def get_gee_engine() -> EarthEngineBackend:
    global _earth_engine
    if _earth_engine is None:
        _earth_engine = EarthEngineBackend()
    return _earth_engine


def studio(port: int = 8000, open_browser: bool = True):
    """Launch the interactive Studio in a browser."""
    from .cli import launch_studio
    launch_studio(port=port, open_browser=open_browser)


launch = studio


def search_stac(
    bbox: List[float],
    collection: str = "sentinel-2-l2a",
    max_items: int = 5,
) -> Dict[str, Any]:
    """List scenes covering `bbox`. No credentials required."""
    return search_stac_anonymously(bbox=bbox, collection=collection, max_items=max_items)


def get_modis_ndvi(bbox: List[float]) -> Dict[str, Any]:
    """A 250 m MODIS NDVI tile layer (MOD13Q1). No credentials required.

    This is a vegetation index for display. For percent tree canopy cover, which
    is a different product, see `get_modis_tcc`.
    """
    return get_stac_engine().modis_ndvi_tiles(bbox=bbox)


def get_modis_tcc(bbox: List[float], year: int = 2020) -> Dict[str, Any]:
    """Percent tree canopy cover from MOD44B. Requires Google Earth Engine.

    Planetary Computer does not carry MOD44B, so there is no zero-credential
    route to canopy cover. Earlier releases answered this call with MOD13Q1 NDVI
    or a NASA GIBS reflectance layer, neither of which is canopy cover.

    On success, `result["stats"]["Percent_Tree_Cover_mean"]` is the regional mean
    percentage.
    """
    return get_gee_engine().compute_modis_tcc(bbox=bbox, year=year)


def get_tiles(bbox: List[float], layer: str = "ndvi") -> Dict[str, Any]:
    """A display tile layer for `bbox`: ndvi, sentinel2, true_color, or lst."""
    return get_stac_engine().tiles_for(bbox=bbox, layer=layer)


def fetch_buildings(bbox: List[float], limit: int = 1000, allow_osm_fallback: bool = True):
    """Building footprints for `bbox`, from Overture or OpenStreetMap.

    The returned GeoDataFrame has a `source` column identifying each row's
    origin, and licence terms in `gdf.attrs["provenance"]`. Pass
    `allow_osm_fallback=False` to require Overture specifically.
    """
    return get_overture_engine().fetch_building_footprints(
        bbox=bbox, limit=limit, allow_osm_fallback=allow_osm_fallback
    )


def partition(bbox: List[float], tile_size: float = 0.1) -> List[Dict[str, Any]]:
    """Split a large bounding box into a grid of smaller tiles."""
    return split_bbox(bbox=bbox, tile_size_deg=tile_size)


def compute_index(
    bbox: List[float],
    index: str = "ndvi",
    start_date: str = "2024-01-01",
    end_date: str = "2024-06-01",
    cloud_threshold: float = 20.0,
) -> Dict[str, Any]:
    """Compute a spectral index over `bbox` and return measured statistics.

    Supported: ndvi, ndwi, lswi, nbr, ndbi.

    Requires Google Earth Engine, which performs the cloud masking, compositing
    and reduction server-side. Without it this returns a result with
    `status="unavailable"` and a `remedy` explaining what to do, because the
    Planetary Computer array path cannot currently retrieve pixels.
    """
    engine = get_gee_engine()
    if engine.initialized:
        return engine.compute_spectral_index(
            bbox=bbox, index_type=index,
            start_date=start_date, end_date=end_date,
            cloud_threshold=cloud_threshold,
        )

    raster = get_stac_engine().fetch_raster_for_bbox(bbox=bbox, index_type=index)
    if raster.get("status") != "success":
        return raster

    band_map = {
        "ndvi": ("nir_array", "red_array"),
        "ndwi": ("green_array", "nir_array"),
        "lswi": ("nir_array", "swir_array"),
        "nbr": ("nir_array", "swir2_array"),
        "ndbi": ("swir_array", "nir_array"),
    }
    fn_map = {
        "ndvi": SpectralIndexCalculator.ndvi,
        "ndwi": SpectralIndexCalculator.ndwi,
        "lswi": SpectralIndexCalculator.lswi,
        "nbr": SpectralIndexCalculator.nbr,
        "ndbi": SpectralIndexCalculator.ndbi,
    }
    key = index.lower()
    if key not in band_map:
        from .provenance import unavailable
        return unavailable(
            reason=f"Unknown index '{index}'.",
            remedy=f"Choose one of: {', '.join(sorted(band_map))}.",
        )

    import numpy as np
    a_key, b_key = band_map[key]
    a, b = raster.get(a_key), raster.get(b_key)
    if a is None or b is None:
        from .provenance import unavailable
        return unavailable(
            reason=f"Bands {a_key} and {b_key} needed for {key.upper()} were not returned.",
            remedy="This scene does not carry the required bands; try another date.",
        )

    array = fn_map[key](a, b)
    valid = array[~np.isnan(array)]
    if valid.size == 0:
        from .provenance import unavailable
        return unavailable(
            reason=f"All pixels were nodata after masking, so {key.upper()} has no value.",
            remedy="Try a different date or a larger bounding box.",
        )

    return {
        "status": "success",
        "provenance": raster.get("provenance"),
        "kind": "raster",
        "index": key.upper(),
        "index_array": array,
        "index_mean": float(np.nanmean(valid)),
        "index_min": float(np.nanmin(valid)),
        "index_max": float(np.nanmax(valid)),
        "index_std": float(np.nanstd(valid)),
        "pixels_valid": int(valid.size),
    }


def export(data, format: str = "geojson", output: str = "output.geojson") -> str:
    """Write a GeoDataFrame to geojson, parquet, or csv. Returns the path."""
    return export_open_dataset(gdf=data, output_format=format, output_path=output)


def report(data, city_name: str = "Analysis Region", output: str = "map_report.html") -> str:
    """Write a standalone HTML map of a GeoDataFrame. Returns the path."""
    return write_map_report(data, title=city_name, output_path=output)


__all__ = [
    "studio", "launch",
    "search_stac", "get_tiles", "get_modis_ndvi", "get_modis_tcc",
    "fetch_buildings", "partition", "compute_index", "export", "report",
    "Provenance", "PROVIDER_LICENSES",
    "EarthEngineBackend", "STACBackend", "OvertureBackend",
    "COLLECTION_MAP",
    "SpectralIndexCalculator",
    "compute_ndvi", "compute_ndwi", "compute_lswi", "compute_nbr", "compute_ndbi",
    "write_map_report", "split_bbox",
    "ZeroAuthSTACReader", "search_stac_anonymously",
    "export_open_dataset", "OpenDatasetExporter",
    "STACItemBuilder", "build_stac_item",
    # Deprecated aliases, retained for one release.
    "GEEOperationEngine", "ProductionSTACEngine", "ProductionOvertureEngine",
    "generate_policy_report", "partition_state_bbox",
    "GEEToSTACConverter", "export_gee_to_stac",
]
