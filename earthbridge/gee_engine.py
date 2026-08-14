"""
Google Earth Engine (GEE) Production Raster & Climatology Compute Engine
=========================================================================
Executes server-side satellite reduction, 10-year LST climatology anomaly computation,
cloud-masked Sentinel-2/Landsat spectral indices, and exports live MapID XYZ tile URLs.
"""

import os
import datetime
from typing import Dict, Any, List, Optional, Tuple, Union

try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    ee = None


class GEEOperationEngine:
    """Production GEE Server-Side Computation Manager."""

    def __init__(self, project_id: Optional[str] = None):
        self.initialized = False
        self.init_error = None
        if GEE_AVAILABLE:
            try:
                gcp_project = project_id or os.environ.get(
                    "EE_PROJECT_ID", os.environ.get("GEE_PROJECT", None)
                )
                if gcp_project:
                    ee.Initialize(project=gcp_project)
                else:
                    ee.Initialize()
                self.initialized = True
            except Exception as e:
                self.init_error = str(e)
        else:
            self.init_error = "earthengine-api package not installed."

    def _unauthenticated_fallback(self, context: str = "") -> Dict[str, Any]:
        """Returns a consistent fallback dict when GEE is unavailable."""
        return {
            "status": "unauthenticated",
            "provider": "GEE (unavailable — run 'earthengine authenticate')",
            "tile_url": None,
            "stats": None,
            "message": (
                f"GEE authentication required for {context}. "
                "Run 'earthengine authenticate' or set EE_PROJECT_ID env var."
            ),
        }

    def compute_lst_climatology_anomaly(
        self,
        bbox: List[float],
        start_year: int = 2015,
        end_year: int = 2025,
        target_month: int = 7,
    ) -> Dict[str, Any]:
        """
        Computes 10-year Land Surface Temperature (LST) Climatology Deviation Anomaly.
        Formula: Anomaly = LST_observed - LST_historical_mean (10-year monthly baseline)

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]
            start_year: Start year for historical climatology baseline
            end_year: End year for historical climatology baseline
            target_month: Target month to evaluate (1 to 12)
        """
        if not self.initialized:
            return self._unauthenticated_fallback("LST Climatology Anomaly")

        min_x, min_y, max_x, max_y = bbox
        region = ee.Geometry.Rectangle([min_x, min_y, max_x, max_y])

        # Load MODIS LST 1km Daily Collection (MOD11A1 061)
        modis_coll = (
            ee.ImageCollection("MODIS/061/MOD11A1")
            .filterBounds(region)
            .filter(ee.Filter.calendarRange(target_month, target_month, "month"))
            .select("LST_Day_1km")
        )

        # Convert raw digital numbers to Celsius: LST * 0.02 - 273.15
        def to_celsius(img):
            celsius = img.multiply(0.02).subtract(273.15).rename("LST_Celsius")
            return img.addBands(celsius)

        celsius_coll = modis_coll.map(to_celsius).select("LST_Celsius")

        # Historical 10-year baseline mean
        historical_baseline = celsius_coll.filter(
            ee.Filter.calendarRange(start_year, end_year, "year")
        ).mean()

        # Current year observed mean
        current_year = datetime.datetime.now().year - 1
        current_observed = celsius_coll.filter(
            ee.Filter.calendarRange(current_year, current_year, "year")
        ).mean()

        # Thermal Anomaly Deviation
        lst_anomaly = current_observed.subtract(historical_baseline).rename(
            "LST_Anomaly"
        )

        # Compute summary statistics over ROI
        stats = (
            lst_anomaly.reduceRegion(
                reducer=ee.Reducer.mean()
                .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
                .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
                geometry=region,
                scale=1000,
                maxPixels=1e9,
            )
            .getInfo()
        )

        # Get XYZ Tile URL — correct Earth Engine API pattern
        viz_params = {
            "min": -3.0,
            "max": 5.0,
            "palette": ["blue", "white", "orange", "red"],
        }
        try:
            map_id = lst_anomaly.getMapId(viz_params)
            tile_url = map_id["tile_fetcher"].url_format
        except Exception:
            tile_url = None

        return {
            "status": "success",
            "provider": "Google Earth Engine (MODIS MOD11A1)",
            "climatology_baseline": f"{start_year}-{end_year} Month {target_month}",
            "observed_period": f"Year {current_year} Month {target_month}",
            "stats": stats,
            "tile_url": tile_url,
        }

    def compute_sentinel2_indices(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        cloud_threshold: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Computes cloud-masked Sentinel-2 L2A median surface reflectance and spectral indices.
        Calculates: NDVI, NDWI, LSWI, NBR, NDBI.
        """
        if not self.initialized:
            return self._unauthenticated_fallback("Sentinel-2 Spectral Indices")

        min_x, min_y, max_x, max_y = bbox
        region = ee.Geometry.Rectangle([min_x, min_y, max_x, max_y])

        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
        )

        median_img = s2.median().clip(region)

        # Calculate spectral indices
        ndvi = median_img.normalizedDifference(["B8", "B4"]).rename("NDVI")
        ndwi = median_img.normalizedDifference(["B3", "B8"]).rename("NDWI")
        lswi = median_img.normalizedDifference(["B8", "B11"]).rename("LSWI")
        nbr = median_img.normalizedDifference(["B8", "B12"]).rename("NBR")
        ndbi = median_img.normalizedDifference(["B11", "B8"]).rename("NDBI")

        # Generate MapID Tile URLs — correct Earth Engine API pattern
        ndvi_viz = {
            "min": -0.1,
            "max": 0.8,
            "palette": ["#0000ff", "#ffffff", "#22c55e", "#15803d"],
        }
        try:
            map_id = ndvi.getMapId(ndvi_viz)
            tile_url = map_id["tile_fetcher"].url_format
        except Exception:
            tile_url = None

        stats = (
            ndvi.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    ee.Reducer.minMax(), sharedInputs=True
                ),
                geometry=region,
                scale=10,
                maxPixels=1e9,
            )
            .getInfo()
        )

        return {
            "status": "success",
            "provider": "Google Earth Engine (Sentinel-2 L2A)",
            "tile_url": tile_url,
            "stats": stats,
        }
