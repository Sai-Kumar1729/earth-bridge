"""
Microsoft Planetary Computer STAC Engine & COG Streaming Reader
===============================================================
Production-grade STAC search, automatic SAS token URL signing, HTTP windowed COG raster
streaming, and real satellite raster data pipeline with graceful synthetic fallback.
"""

from typing import Dict, Any, List, Optional, Tuple
import urllib.request
import json
import numpy as np

try:
    import pystac_client
    import planetary_computer
    PYSTAC_AVAILABLE = True
except ImportError:
    PYSTAC_AVAILABLE = False

try:
    import rasterio
    from rasterio.windows import from_bounds
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False


# Cross-Cloud Collection Mapping (absorbed from planetary_sync.py)
COLLECTION_MAP = {
    "sentinel-2-l2a": {
        "mpc": "sentinel-2-l2a",
        "gee": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": {
            "red": "B04", "green": "B03", "blue": "B02",
            "nir": "B08", "swir": "B11", "swir2": "B12",
        },
    },
    "landsat-c2-l2": {
        "mpc": "landsat-c2-l2",
        "gee": "LANDSAT/LC08/C02/T1_L2",
        "bands": {
            "red": "SR_B4", "green": "SR_B3", "blue": "SR_B2",
            "nir": "SR_B5", "swir": "SR_B6", "swir2": "SR_B7",
        },
    },
    "modis-11A1-061": {
        "mpc": "modis-11A1-061",
        "gee": "MODIS/061/MOD11A1",
        "bands": {"lst_day": "LST_Day_1km", "lst_night": "LST_Night_1km"},
    },
}


class ProductionSTACEngine:
    """Production Client for STAC 1.0.0 Catalogs & COG Streaming."""

    STAC_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"

    def __init__(self):
        self.client = None
        if PYSTAC_AVAILABLE:
            try:
                self.client = pystac_client.Client.open(
                    self.STAC_ENDPOINT,
                    modifier=planetary_computer.sign_inplace,
                )
            except Exception as e:
                print(f"[ProductionSTACEngine] Client initialization note: {e}")

    def query_sentinel2_stac(
        self,
        bbox: List[float],
        start_date: str = "2026-01-01",
        end_date: str = "2026-08-01",
        max_items: int = 5,
        max_cloud_cover: float = 15.0,
        collection: str = "sentinel-2-l2a",
    ) -> List[Dict[str, Any]]:
        """
        Executes production STAC query against a satellite collection.
        Returns signed asset URLs for relevant bands.
        """
        if self.client:
            try:
                datetime_str = f"{start_date}/{end_date}"
                search = self.client.search(
                    collections=[collection],
                    bbox=bbox,
                    datetime=datetime_str,
                    query={"eo:cloud_cover": {"lt": max_cloud_cover}},
                    limit=max_items,
                )
                items = list(search.items())
                results = []
                for item in items:
                    assets_signed = {}
                    for key in ["B04", "B08", "B11", "B03", "B12", "visual"]:
                        if key in item.assets:
                            assets_signed[key] = {
                                "href": item.assets[key].href,
                                "type": item.assets[key].media_type,
                            }
                    results.append(
                        {
                            "id": item.id,
                            "datetime": (
                                item.datetime.isoformat() if item.datetime else None
                            ),
                            "cloud_cover": item.properties.get("eo:cloud_cover"),
                            "bbox": item.bbox,
                            "assets": assets_signed,
                        }
                    )
                return results
            except Exception as e:
                print(f"[ProductionSTACEngine] STAC query fallback: {e}")

        # Anonymous REST fallback if pystac client is unavailable
        return self._rest_anonymous_fallback(bbox, max_items)

    def read_cog_window(
        self, cog_url: str, bbox: List[float]
    ) -> Optional[np.ndarray]:
        """
        Reads a windowed sub-array directly from a remote Cloud Optimized GeoTIFF (COG)
        via HTTP. Does NOT download the entire tile — uses HTTP range requests via rasterio.
        """
        if not RASTERIO_AVAILABLE:
            return None
        try:
            with rasterio.open(cog_url) as src:
                window = from_bounds(*bbox, transform=src.transform)
                data = src.read(1, window=window)
                return data
        except Exception as e:
            print(f"[ProductionSTACEngine] COG window read note: {e}")
            return None

    def fetch_raster_for_bbox(
        self,
        bbox: List[float],
        index_type: str = "ndvi",
        collection: str = "sentinel-2-l2a",
    ) -> Dict[str, Any]:
        """
        Full pipeline: STAC search → find best scene → read COG bands → return numpy arrays.

        Returns dict with keys:
            status: 'success' | 'fallback'
            nir_array, red_array, green_array, swir_array: np.ndarray or None
            provider: str describing data source
        """
        # Attempt real STAC COG pipeline
        try:
            scenes = self.query_sentinel2_stac(
                bbox, max_items=1, collection=collection
            )
            if scenes and RASTERIO_AVAILABLE:
                scene = scenes[0]
                assets = scene.get("assets", {})
                nir_url = assets.get("B08", {}).get("href")
                red_url = assets.get("B04", {}).get("href")
                green_url = assets.get("B03", {}).get("href")
                swir_url = assets.get("B11", {}).get("href")

                nir_arr = self.read_cog_window(nir_url, bbox) if nir_url else None
                red_arr = self.read_cog_window(red_url, bbox) if red_url else None
                green_arr = (
                    self.read_cog_window(green_url, bbox) if green_url else None
                )
                swir_arr = (
                    self.read_cog_window(swir_url, bbox) if swir_url else None
                )

                if nir_arr is not None and red_arr is not None:
                    # Normalize to [0, 1] reflectance if needed (Sentinel-2 L2A: divide by 10000)
                    nir_f = nir_arr.astype(np.float32) / 10000.0
                    red_f = red_arr.astype(np.float32) / 10000.0
                    green_f = (
                        green_arr.astype(np.float32) / 10000.0
                        if green_arr is not None
                        else None
                    )
                    swir_f = (
                        swir_arr.astype(np.float32) / 10000.0
                        if swir_arr is not None
                        else None
                    )

                    return {
                        "status": "success",
                        "provider": f"Planetary Computer STAC ({scene['id']})",
                        "nir_array": nir_f,
                        "red_array": red_f,
                        "green_array": green_f,
                        "swir_array": swir_f,
                    }
        except Exception as e:
            print(f"[ProductionSTACEngine] Real raster pipeline note: {e}")

        # Graceful synthetic fallback — deterministic per bbox location
        seed = hash(tuple(bbox)) % (2**32)
        rng = np.random.RandomState(seed)

        return {
            "status": "fallback",
            "provider": "Synthetic Raster Engine (STAC offline)",
            "nir_array": rng.uniform(0.30, 0.80, (100, 100)).astype(np.float32),
            "red_array": rng.uniform(0.04, 0.22, (100, 100)).astype(np.float32),
            "green_array": rng.uniform(0.03, 0.18, (100, 100)).astype(np.float32),
            "swir_array": rng.uniform(0.08, 0.45, (100, 100)).astype(np.float32),
        }

    def _rest_anonymous_fallback(
        self, bbox: List[float], max_items: int
    ) -> List[Dict[str, Any]]:
        """REST API fallback for zero-auth public STAC search."""
        endpoint = f"{self.STAC_ENDPOINT}/search"
        payload = {
            "bbox": bbox,
            "collections": ["sentinel-2-l2a"],
            "limit": max_items,
            "query": {"eo:cloud_cover": {"lt": 20.0}},
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "earth-bridge/0.2.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [
                    {
                        "id": feat.get("id"),
                        "datetime": feat.get("properties", {}).get("datetime"),
                        "cloud_cover": feat.get("properties", {}).get(
                            "eo:cloud_cover"
                        ),
                        "assets": feat.get("assets", {}),
                    }
                    for feat in data.get("features", [])
                ]
        except Exception:
            return []
