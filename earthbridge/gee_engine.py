"""
Google Earth Engine backend: server-side compute, no local pixel processing.

Earth Engine does the cloud masking, compositing, index arithmetic and region
reduction on Google's infrastructure. What comes back is a summary statistic and
an XYZ tile URL, so memory use here stays flat regardless of how large the
region is.

This backend requires credentials. Run `earthengine authenticate` once, then
supply a Google Cloud project id. Nothing in this module invents a value when
Earth Engine is unreachable; it reports that it is unreachable.
"""

import os
import datetime
from typing import Dict, Any, List, Optional, Tuple

from .provenance import Provenance, success, unavailable

try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    ee = None


# Sentinel-2 Scene Classification Layer values that are not usable surface.
SCL_CLOUD_SHADOW = 3
SCL_CLOUD_MEDIUM_PROB = 8
SCL_CLOUD_HIGH_PROB = 9
SCL_CIRRUS = 10
SCL_MASKED_CLASSES = [
    SCL_CLOUD_SHADOW,
    SCL_CLOUD_MEDIUM_PROB,
    SCL_CLOUD_HIGH_PROB,
    SCL_CIRRUS,
]

INDEX_CONFIGS = {
    "ndvi": {
        "bands": ["B8", "B4"],
        "name": "NDVI (vegetation)",
        "viz": {"min": -0.1, "max": 0.85, "palette": [
            "#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b", "#ffffbf",
            "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"]},
    },
    "ndwi": {
        "bands": ["B3", "B8"],
        "name": "NDWI (water)",
        "viz": {"min": -0.5, "max": 0.5, "palette": [
            "#ffffd4", "#fed98e", "#fe9929", "#d95f0e", "#993404", "#045a8d", "#023858"]},
    },
    "lswi": {
        "bands": ["B8", "B11"],
        "name": "LSWI (land surface water)",
        "viz": {"min": -0.2, "max": 0.6, "palette": [
            "#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]},
    },
    "nbr": {
        "bands": ["B8", "B12"],
        "name": "NBR (burn ratio)",
        "viz": {"min": -0.3, "max": 0.7, "palette": [
            "#7f3b08", "#b35806", "#e08214", "#fdb863", "#fee0b6", "#d8daeb",
            "#b2abd2", "#8073ac", "#542788", "#2d004b"]},
    },
    "ndbi": {
        "bands": ["B11", "B8"],
        "name": "NDBI (built-up)",
        "viz": {"min": -0.3, "max": 0.5, "palette": [
            "#2b83ba", "#abdda4", "#ffffbf", "#fdae61", "#d7191c"]},
    },
}


class EarthEngineBackend:
    """Server-side computation on Google Earth Engine."""

    def __init__(self, project_id: Optional[str] = None):
        self.initialized = False
        self.init_error: Optional[str] = None
        self.project_id: Optional[str] = None
        if not GEE_AVAILABLE:
            self.init_error = (
                "earthengine-api is not installed. Install with "
                "pip install 'earth-bridge[gee]'."
            )
            return
        project = project_id or os.environ.get("EE_PROJECT_ID") or os.environ.get("GEE_PROJECT")
        try:
            if project:
                ee.Initialize(project=project)
                self.project_id = project
            else:
                ee.Initialize()
            self.initialized = True
        except Exception as e:
            self.init_error = str(e)

    def reconnect(self, project_id: Optional[str] = None) -> Tuple[bool, str]:
        """Re-initialise Earth Engine with a Cloud project id."""
        if not GEE_AVAILABLE:
            return False, "earthengine-api is not installed."
        project = (project_id or "").strip() or None
        try:
            if project:
                ee.Initialize(project=project)
                os.environ["EE_PROJECT_ID"] = project
            else:
                ee.Initialize()
            self.initialized = True
            self.init_error = None
            self.project_id = project
            return True, f"Earth Engine initialised with project '{project or 'default'}'."
        except Exception as e:
            self.initialized = False
            self.init_error = str(e)
            return False, str(e)

    def _not_initialized(self, what: str) -> Dict[str, Any]:
        return unavailable(
            reason=f"{what} requires Google Earth Engine, which is not initialised.",
            remedy=(
                f"{self.init_error or 'Not initialised.'} "
                "Run 'earthengine authenticate' once, then supply a Cloud project id "
                "in the Studio header or via the EE_PROJECT_ID environment variable."
            ),
        )

    @staticmethod
    def _region(bbox: List[float], geometry_geojson: Optional[Dict[str, Any]] = None):
        if geometry_geojson:
            try:
                return ee.Geometry(geometry_geojson)
            except Exception:
                pass
        return ee.Geometry.Rectangle(list(bbox))

    @staticmethod
    def _stats_or_none(raw: Dict[str, Any], band: str) -> Optional[Dict[str, float]]:
        """Convert a reduceRegion result into floats, or None if it is empty.

        Earth Engine returns null for every reducer when no unmasked pixels fall
        in the region. Coercing that to 0.0 would report an empty region as a
        real measurement of zero, so it returns None instead.
        """
        mean = raw.get(f"{band}_mean")
        if mean is None:
            return None
        return {
            "mean": float(mean),
            "min": float(raw[f"{band}_min"]) if raw.get(f"{band}_min") is not None else None,
            "max": float(raw[f"{band}_max"]) if raw.get(f"{band}_max") is not None else None,
            "stdDev": float(raw[f"{band}_stdDev"]) if raw.get(f"{band}_stdDev") is not None else None,
        }

    @staticmethod
    def _reducer():
        return (
            ee.Reducer.mean()
            .combine(ee.Reducer.minMax(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
        )

    @staticmethod
    def _mask_s2_clouds(img):
        """Mask cloud, shadow and cirrus pixels using the Scene Classification Layer."""
        scl = img.select("SCL")
        mask = ee.Image.constant(1)
        for cls in SCL_MASKED_CLASSES:
            mask = mask.And(scl.neq(cls))
        return img.updateMask(mask)

    # ------------------------------------------------------------------

    def compute_modis_tcc(self, bbox: List[float], year: int = 2020) -> Dict[str, Any]:
        """Percent tree canopy cover from MOD44B, 250 m, yearly.

        MOD44B Vegetation Continuous Fields is the actual canopy-cover product.
        It is not carried by Planetary Computer, so this path has no
        zero-credential equivalent.
        """
        if not self.initialized:
            return self._not_initialized("Tree canopy cover (MOD44B)")

        try:
            region = self._region(bbox)
            collection = (
                ee.ImageCollection("MODIS/061/MOD44B")
                .filterBounds(region)
                .filter(ee.Filter.calendarRange(year, year, "year"))
                .select("Percent_Tree_Cover")
            )

            # ee.Image objects are always truthy, so emptiness has to be tested
            # on the server and fetched back explicitly.
            if collection.size().getInfo() == 0:
                available = (
                    ee.ImageCollection("MODIS/061/MOD44B")
                    .filterBounds(region)
                    .aggregate_array("system:index")
                    .getInfo()
                )
                return unavailable(
                    reason=f"MOD44B has no imagery for {year} over this region.",
                    remedy=f"Available MOD44B indices here: {available[:8] or 'none'}.",
                )

            image = collection.first().clip(region)
            raw = image.reduceRegion(
                reducer=self._reducer(), geometry=region, scale=250, maxPixels=1e9
            ).getInfo()
            stats = self._stats_or_none(raw, "Percent_Tree_Cover")
            if stats is None:
                return unavailable(
                    reason="MOD44B returned no unmasked pixels for this region.",
                    remedy="The bounding box may be over water or too small for 250 m pixels.",
                )

            tile_url = image.getMapId({
                "min": 0.0, "max": 100.0,
                "palette": ["#ffffd4", "#fed98e", "#fe9929", "#78c679", "#238443", "#004529"],
            })["tile_fetcher"].url_format

            return success(
                Provenance(
                    backend="earth-engine",
                    collection="MODIS/061/MOD44B",
                    datetime=str(year),
                    resolution="250m",
                    notes=["Percent_Tree_Cover band, yearly Vegetation Continuous Fields."],
                    requested={"bbox": bbox, "year": year},
                ),
                kind="tile_layer_with_stats",
                tile_url=tile_url,
                stats={"Percent_Tree_Cover_mean": stats["mean"], **stats},
                layer_name=f"MODIS tree canopy cover 250m ({year})",
            )
        except Exception as e:
            return unavailable(
                reason=f"Earth Engine error computing MOD44B: {e}",
                remedy="Check that your Cloud project has the Earth Engine API enabled.",
            )

    def compute_modis_true_color(
        self, bbox: List[float],
        start_date: str = "2024-01-01",
        end_date: str = "2024-06-01",
    ) -> Dict[str, Any]:
        """MOD09A1 500 m surface reflectance RGB composite."""
        if not self.initialized:
            return self._not_initialized("MODIS true colour composite")
        try:
            region = self._region(bbox)
            bands = ["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"]
            collection = (
                ee.ImageCollection("MODIS/061/MOD09A1")
                .filterBounds(region)
                .filterDate(start_date, end_date)
                .select(bands)
            )
            count = collection.size().getInfo()
            if count == 0:
                return unavailable(
                    reason=f"No MOD09A1 imagery between {start_date} and {end_date}.",
                    remedy="Widen the date range.",
                )
            composite = collection.median().clip(region)
            tile_url = composite.getMapId(
                {"min": 100, "max": 3500, "bands": bands}
            )["tile_fetcher"].url_format
            return success(
                Provenance(
                    backend="earth-engine",
                    collection="MODIS/061/MOD09A1",
                    datetime=f"{start_date}/{end_date}",
                    resolution="500m",
                    notes=[f"Median of {count} 8-day composites."],
                    requested={"bbox": bbox, "start_date": start_date, "end_date": end_date},
                ),
                kind="tile_layer",
                tile_url=tile_url,
                layer_name="MODIS true colour 500m",
            )
        except Exception as e:
            return unavailable(reason=f"Earth Engine error computing MOD09A1: {e}")

    def compute_lst_climatology_anomaly(
        self,
        bbox: List[float],
        baseline_start_year: int = 2013,
        baseline_end_year: int = 2022,
        observed_year: Optional[int] = None,
        target_month: int = 7,
    ) -> Dict[str, Any]:
        """Land surface temperature anomaly against a monthly climatology.

        anomaly = observed monthly mean LST - baseline monthly mean LST

        The observed year is excluded from the baseline. Including it, as this
        function previously did, lets the observation contribute to the mean it
        is being compared against, which damps the anomaly toward zero.
        """
        if not self.initialized:
            return self._not_initialized("LST climatology anomaly")

        observed_year = observed_year or (datetime.datetime.now().year - 1)
        if baseline_start_year <= observed_year <= baseline_end_year:
            return unavailable(
                reason=(
                    f"Observed year {observed_year} falls inside the baseline "
                    f"{baseline_start_year}-{baseline_end_year}, which would bias "
                    "the anomaly toward zero."
                ),
                remedy=f"Use a baseline that ends before {observed_year}.",
            )

        try:
            region = self._region(bbox)
            monthly = (
                ee.ImageCollection("MODIS/061/MOD11A1")
                .filterBounds(region)
                .filter(ee.Filter.calendarRange(target_month, target_month, "month"))
                .select("LST_Day_1km")
                # Scale factor 0.02 K per DN, then Kelvin to Celsius.
                .map(lambda img: img.multiply(0.02).subtract(273.15).rename("LST_Celsius"))
            )

            baseline = monthly.filter(
                ee.Filter.calendarRange(baseline_start_year, baseline_end_year, "year")
            )
            observed = monthly.filter(
                ee.Filter.calendarRange(observed_year, observed_year, "year")
            )
            baseline_n = baseline.size().getInfo()
            observed_n = observed.size().getInfo()
            if baseline_n == 0 or observed_n == 0:
                return unavailable(
                    reason=(
                        f"Insufficient MOD11A1 imagery: {baseline_n} baseline and "
                        f"{observed_n} observed scenes for month {target_month}."
                    ),
                    remedy="Choose a different month or widen the baseline.",
                )

            anomaly = observed.mean().subtract(baseline.mean()).rename("LST_Anomaly")
            raw = anomaly.reduceRegion(
                reducer=self._reducer(), geometry=region, scale=1000, maxPixels=1e9
            ).getInfo()
            stats = self._stats_or_none(raw, "LST_Anomaly")
            if stats is None:
                return unavailable(
                    reason="MOD11A1 returned no unmasked pixels for this region.",
                    remedy="The bounding box may be over water or persistently cloudy.",
                )

            tile_url = anomaly.getMapId({
                "min": -3.0, "max": 5.0,
                "palette": ["blue", "white", "orange", "red"],
            })["tile_fetcher"].url_format

            return success(
                Provenance(
                    backend="earth-engine",
                    collection="MODIS/061/MOD11A1",
                    datetime=f"month {target_month}, {observed_year} vs {baseline_start_year}-{baseline_end_year}",
                    resolution="1km",
                    notes=[
                        f"Baseline mean over {baseline_n} scenes; observed mean over "
                        f"{observed_n} scenes.",
                        "Daytime LST only. Values are degrees Celsius difference.",
                        "MOD11A1 is already cloud-screened by the upstream QA process.",
                    ],
                    requested={
                        "bbox": bbox, "target_month": target_month,
                        "observed_year": observed_year,
                        "baseline": [baseline_start_year, baseline_end_year],
                    },
                ),
                kind="tile_layer_with_stats",
                tile_url=tile_url,
                stats=stats,
                layer_name=f"LST anomaly °C ({observed_year} vs {baseline_start_year}-{baseline_end_year})",
            )
        except Exception as e:
            return unavailable(reason=f"Earth Engine error computing LST anomaly: {e}")

    def compute_spectral_index(
        self,
        bbox: List[float],
        index_type: str = "ndvi",
        start_date: str = "2024-01-01",
        end_date: str = "2024-06-01",
        cloud_threshold: float = 20.0,
        geometry_geojson: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute a Sentinel-2 spectral index over a region, server-side.

        Scenes above `cloud_threshold` are dropped, then remaining scenes are
        masked per-pixel with the Scene Classification Layer before compositing.
        Scene-level filtering alone leaves cloud in the median, which biases
        NDVI down and NDBI up.
        """
        if not self.initialized:
            return self._not_initialized(f"Index '{index_type.upper()}'")

        key = index_type.lower()
        if key in ("modis_tcc", "tcc"):
            return self.compute_modis_tcc(bbox=bbox)
        if key in ("modis_true_color", "modis_rgb"):
            return self.compute_modis_true_color(bbox, start_date, end_date)
        if key in ("lst_anomaly", "lst"):
            return self.compute_lst_climatology_anomaly(bbox)

        cfg = INDEX_CONFIGS.get(key)
        if cfg is None:
            return unavailable(
                reason=f"Unknown index '{index_type}'.",
                remedy=f"Choose one of: {', '.join(sorted(INDEX_CONFIGS))}.",
            )

        try:
            region = self._region(bbox, geometry_geojson)
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(region)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
            )
            scene_count = collection.size().getInfo()
            if scene_count == 0:
                return unavailable(
                    reason=(
                        f"No Sentinel-2 scenes below {cloud_threshold}% cloud between "
                        f"{start_date} and {end_date} over this region."
                    ),
                    remedy="Widen the date range or raise cloud_threshold.",
                )

            composite = collection.map(self._mask_s2_clouds).median().clip(region)
            index_img = composite.normalizedDifference(cfg["bands"]).rename("index_value")

            raw = index_img.reduceRegion(
                reducer=self._reducer(), geometry=region, scale=20, maxPixels=1e9
            ).getInfo()
            stats = self._stats_or_none(raw, "index_value")
            if stats is None:
                return unavailable(
                    reason=(
                        "Every pixel in this region was masked as cloud, shadow or "
                        "cirrus, so no index value could be computed."
                    ),
                    remedy="Widen the date range so more clear observations are available.",
                )

            tile_url = index_img.getMapId(cfg["viz"])["tile_fetcher"].url_format

            return success(
                Provenance(
                    backend="earth-engine",
                    collection="COPERNICUS/S2_SR_HARMONIZED",
                    datetime=f"{start_date}/{end_date}",
                    resolution="20m (reduction scale)",
                    notes=[
                        f"Median of {scene_count} scenes below {cloud_threshold}% cloud.",
                        "Per-pixel SCL mask applied for cloud shadow, medium and high "
                        "probability cloud, and cirrus.",
                        f"Bands {cfg['bands'][0]} and {cfg['bands'][1]} as normalised difference.",
                    ],
                    requested={
                        "bbox": bbox, "index_type": key,
                        "start_date": start_date, "end_date": end_date,
                        "cloud_threshold": cloud_threshold,
                    },
                ),
                kind="tile_layer_with_stats",
                tile_url=tile_url,
                stats={
                    f"{key.upper()}_mean": round(stats["mean"], 4),
                    "mean": round(stats["mean"], 4),
                    "min": round(stats["min"], 4) if stats["min"] is not None else None,
                    "max": round(stats["max"], 4) if stats["max"] is not None else None,
                    "stdDev": round(stats["stdDev"], 4) if stats["stdDev"] is not None else None,
                    "scenes_used": scene_count,
                },
                layer_name=f"Sentinel-2 {key.upper()} ({cfg['name']})",
            )
        except Exception as e:
            return unavailable(reason=f"Earth Engine error computing {key.upper()}: {e}")

    def compute_sentinel2_indices(
        self,
        bbox: List[float],
        start_date: str = "2024-01-01",
        end_date: str = "2024-06-01",
        cloud_threshold: float = 15.0,
    ) -> Dict[str, Any]:
        """Convenience wrapper for Sentinel-2 NDVI."""
        return self.compute_spectral_index(
            bbox=bbox, index_type="ndvi",
            start_date=start_date, end_date=end_date,
            cloud_threshold=cloud_threshold,
        )


# Previous class name, kept so existing imports keep working.
GEEOperationEngine = EarthEngineBackend
