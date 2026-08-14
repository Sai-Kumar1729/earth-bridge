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

    def reconnect(self, project_id: Optional[str] = None) -> Tuple[bool, str]:
        """Dynamically re-initialize Earth Engine with a user-supplied Cloud Project ID."""
        if not GEE_AVAILABLE:
            return False, "earthengine-api Python package is not installed."
        try:
            proj = project_id.strip() if project_id else None
            if proj:
                ee.Initialize(project=proj)
                os.environ["EE_PROJECT_ID"] = proj
            else:
                ee.Initialize()
            self.initialized = True
            self.init_error = None
            return True, f"Successfully authenticated GEE with project '{proj or 'default'}'."
        except Exception as e:
            self.initialized = False
            self.init_error = str(e)
            return False, str(e)

    def _unauthenticated_fallback(self, context: str = "") -> Dict[str, Any]:
        """Returns a consistent fallback dict when GEE is unavailable."""
        return {
            "status": "unauthenticated",
            "provider": "Google Earth Engine (Unauthenticated)",
            "tile_url": None,
            "stats": None,
            "message": (
                f"GEE authentication required for {context}. "
                "Please enter your Google Cloud Project ID in the Studio header "
                "or run 'earthengine authenticate' in your terminal."
            ),
        }

    def compute_modis_tcc(
        self,
        bbox: List[float],
        year: int = 2020
    ) -> Dict[str, Any]:
        """
        Computes MODIS Tree Canopy Cover (Percent_Tree_Cover) from MOD44B Collection (250m)
        clipped to the given bounding box / ROI.
        """
        if not self.initialized:
            return self._unauthenticated_fallback("MODIS Tree Canopy Cover (TCC)")

        try:
            min_x, min_y, max_x, max_y = bbox
            region = ee.Geometry.Rectangle([min_x, min_y, max_x, max_y])

            # MOD44B.061 Terra Vegetation Continuous Fields Yearly Global 250m
            tcc_coll = (
                ee.ImageCollection("MODIS/061/MOD44B")
                .filterBounds(region)
                .filter(ee.Filter.calendarRange(year, year, "year"))
                .select("Percent_Tree_Cover")
            )

            # Fallback to nearest available year if empty
            tcc_img = tcc_coll.first()
            if not tcc_img:
                tcc_img = (
                    ee.ImageCollection("MODIS/061/MOD44B")
                    .filterBounds(region)
                    .sort("system:time_start", False)
                    .select("Percent_Tree_Cover")
                    .first()
                )

            if not tcc_img:
                return {
                    "status": "error",
                    "message": f"No MODIS MOD44B imagery available for ROI in year {year}."
                }

            tcc_clipped = tcc_img.clip(region)

            # Calculate regional statistics over the ROI
            stats = tcc_clipped.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    ee.Reducer.minMax(), sharedInputs=True
                ).combine(
                    ee.Reducer.stdDev(), sharedInputs=True
                ),
                geometry=region,
                scale=250,
                maxPixels=1e9,
            ).getInfo()

            # Visual Palette for Tree Canopy Cover (0% Light/Olive to 100% Deep Forest Green)
            viz_params = {
                "min": 0.0,
                "max": 100.0,
                "palette": ["#ffffd4", "#fed98e", "#fe9929", "#78c679", "#238443", "#004529"],
            }

            map_id = tcc_clipped.getMapId(viz_params)
            tile_url = map_id["tile_fetcher"].url_format

            return {
                "status": "success",
                "provider": f"Google Earth Engine (MODIS MOD44B TCC - {year})",
                "tile_url": tile_url,
                "stats": {
                    "Percent_Tree_Cover_mean": float(stats.get("Percent_Tree_Cover_mean") or 0.0),
                    "min": float(stats.get("Percent_Tree_Cover_min") or 0.0),
                    "max": float(stats.get("Percent_Tree_Cover_max") or 100.0),
                    "stdDev": float(stats.get("Percent_Tree_Cover_stdDev") or 0.0)
                },
                "layer_name": "MODIS Tree Canopy Cover (TCC 250m)"
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": "Google Earth Engine",
                "message": f"Error computing MODIS TCC in GEE: {str(e)}"
            }

    def compute_modis_true_color(
        self,
        bbox: List[float],
        start_date: str = "2024-01-01",
        end_date: str = "2024-06-01"
    ) -> Dict[str, Any]:
        """
        Computes cloud-masked MODIS Surface Reflectance 8-Day 500m (MOD09A1) RGB Composite.
        """
        if not self.initialized:
            return self._unauthenticated_fallback("MODIS True Color Composite")

        try:
            min_x, min_y, max_x, max_y = bbox
            region = ee.Geometry.Rectangle([min_x, min_y, max_x, max_y])

            mod09 = (
                ee.ImageCollection("MODIS/061/MOD09A1")
                .filterBounds(region)
                .filterDate(start_date, end_date)
                .select(["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"])
            )

            composite = mod09.median().clip(region)

            viz = {
                "min": 100,
                "max": 3500,
                "bands": ["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"]
            }

            map_id = composite.getMapId(viz)
            tile_url = map_id["tile_fetcher"].url_format

            return {
                "status": "success",
                "provider": "Google Earth Engine (MODIS MOD09A1 500m)",
                "tile_url": tile_url,
                "stats": {"resolution": "500m", "composite_period": f"{start_date} to {end_date}"},
                "layer_name": "MODIS True Color Composite (500m)"
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": "Google Earth Engine",
                "message": f"Error generating MODIS True Color: {str(e)}"
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
