"""
STAC search and tile layers from Microsoft Planetary Computer and NASA GIBS.

This module returns two categories of result, which should not be confused:

  * **Tile layers** (`kind="tile_layer"`) are rendered PNG or JPEG imagery for
    display on a map. They carry no retrievable pixel values and are intended
    for inspection rather than measurement.
  * **Raster arrays** (`kind="raster"`) are numeric pixel data read from Cloud
    Optimized GeoTIFFs, suitable for computation.

At present only the first works without credentials. The COG reader is gated
off: Planetary Computer asset signing currently returns HTTP 409 for anonymous
callers, so the reader would produce no data. It reports that explicitly rather
than returning a plausible-looking substitute.
"""

from typing import Dict, Any, List, Optional
import datetime as _dt
import urllib.request
import json
import numpy as np

from .provenance import Provenance, success, unavailable

try:
    import pystac_client
    import planetary_computer
    PYSTAC_AVAILABLE = True
except ImportError:
    PYSTAC_AVAILABLE = False

try:
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False


# Cross-provider collection identifiers for the same underlying sensor product.
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

# Sentinel-2 processing baseline 04.00 (from 2022-01-25) shifts surface
# reflectance by a constant offset that must be removed before scaling.
# See https://sentinels.copernicus.eu/web/sentinel/-/copernicus-sentinel-2-major-products-upgrade-upcoming
S2_BOA_QUANTIFICATION = 10000.0
S2_BOA_OFFSET = -1000.0
S2_BASELINE_0400_DATE = _dt.date(2022, 1, 25)

# GIBS publishes with a lag; asking for today usually returns empty tiles.
GIBS_LAG_DAYS = 3


def _gibs_default_date() -> str:
    return (_dt.date.today() - _dt.timedelta(days=GIBS_LAG_DAYS)).isoformat()


def _item_datetime(properties: Dict[str, Any]) -> Optional[str]:
    """Read an item's acquisition time, handling ranged items.

    Composite products such as MOD13Q1 cover an interval, so STAC sets
    `datetime` to null and carries `start_datetime`/`end_datetime` instead.
    Reading only `datetime` reported those items as having no date at all.
    """
    if properties.get("datetime"):
        return properties["datetime"]
    start, end = properties.get("start_datetime"), properties.get("end_datetime")
    if start and end:
        return f"{start}/{end}"
    return start or end


class STACBackend:
    """Client for STAC 1.0.0 catalogs and tile services."""

    STAC_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"
    TILER_ENDPOINT = "https://planetarycomputer.microsoft.com/api/data/v1"

    def __init__(self):
        self.client = None
        self._last_cog_error: Optional[str] = None
        if PYSTAC_AVAILABLE:
            try:
                self.client = pystac_client.Client.open(
                    self.STAC_ENDPOINT,
                    modifier=planetary_computer.sign_inplace,
                )
            except Exception as e:
                print(f"[earth-bridge] STAC client unavailable: {e}")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        bbox: List[float],
        collection: str = "sentinel-2-l2a",
        start_date: str = "2024-01-01",
        end_date: Optional[str] = None,
        max_items: int = 5,
        max_cloud_cover: float = 40.0,
    ) -> List[Dict[str, Any]]:
        """Search a STAC collection and return matching scenes, least cloudy first.

        Results are sorted so repeated calls with the same arguments return the
        same scene in position 0. Callers that pick `results[0]` therefore get a
        deterministic, low-cloud choice rather than whatever the API happened to
        list first.
        """
        end_date = end_date or _dt.date.today().isoformat()
        datetime_str = f"{start_date}/{end_date}"

        results: List[Dict[str, Any]] = []
        if self.client:
            try:
                search = self.client.search(
                    collections=[collection],
                    bbox=bbox,
                    datetime=datetime_str,
                    query={"eo:cloud_cover": {"lt": max_cloud_cover}},
                    limit=max_items,
                )
                for item in search.items():
                    assets_signed = {}
                    for key in ["B04", "B08", "B11", "B03", "B12", "visual"]:
                        if key in item.assets:
                            assets_signed[key] = {
                                "href": item.assets[key].href,
                                "type": item.assets[key].media_type,
                            }
                    results.append({
                        "id": item.id,
                        "collection": collection,
                        "datetime": (
                            item.datetime.isoformat() if item.datetime
                            else _item_datetime(item.properties)
                        ),
                        "cloud_cover": item.properties.get("eo:cloud_cover"),
                        "bbox": item.bbox,
                        "assets": assets_signed,
                    })
            except Exception as e:
                print(f"[earth-bridge] STAC client search failed, using REST: {e}")

        if not results:
            results = self._rest_search(
                collection, bbox, datetime_str, max_items, max_cloud_cover
            )

        results.sort(key=lambda s: (
            s.get("cloud_cover") if s.get("cloud_cover") is not None else 999,
            s.get("id") or "",
        ))
        return results

    # Retained under the previous name so existing callers keep working.
    def query_sentinel2_stac(
        self,
        bbox: List[float],
        start_date: str = "2024-01-01",
        end_date: Optional[str] = None,
        max_items: int = 5,
        max_cloud_cover: float = 40.0,
        collection: str = "sentinel-2-l2a",
    ) -> List[Dict[str, Any]]:
        return self.search(
            bbox=bbox,
            collection=collection,
            start_date=start_date,
            end_date=end_date,
            max_items=max_items,
            max_cloud_cover=max_cloud_cover,
        )

    def _rest_search(
        self,
        collection: str,
        bbox: List[float],
        datetime_str: str,
        max_items: int,
        max_cloud_cover: float,
    ) -> List[Dict[str, Any]]:
        """Anonymous REST search, used when pystac-client is not installed."""
        payload: Dict[str, Any] = {
            "bbox": bbox,
            "collections": [collection],
            "datetime": datetime_str,
            "limit": max_items,
        }
        # Not every collection carries eo:cloud_cover; only filter where it applies.
        if collection.startswith(("sentinel-2", "landsat")):
            payload["query"] = {"eo:cloud_cover": {"lt": max_cloud_cover}}

        req = urllib.request.Request(
            f"{self.STAC_ENDPOINT}/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "earth-bridge/0.3.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[earth-bridge] STAC REST search failed: {e}")
            return []

        return [
            {
                "id": feat.get("id"),
                "collection": collection,
                "datetime": _item_datetime(feat.get("properties", {})),
                "cloud_cover": feat.get("properties", {}).get("eo:cloud_cover"),
                "bbox": feat.get("bbox"),
                "assets": feat.get("assets", {}),
            }
            for feat in data.get("features", [])
        ]

    # ------------------------------------------------------------------
    # Tile layers (imagery for display, not measurable values)
    # ------------------------------------------------------------------

    def modis_ndvi_tiles(self, bbox: List[float]) -> Dict[str, Any]:
        """250 m MODIS NDVI tiles from MOD13Q1, a 16-day vegetation composite.

        This is a vegetation *index*, not tree canopy cover. Percent tree cover
        is a different product (MOD44B) that Planetary Computer does not carry;
        see `EarthEngineBackend.compute_modis_tcc` for that.
        """
        scenes = self.search(bbox, collection="modis-13Q1-061", max_items=3)
        if not scenes:
            return unavailable(
                reason=f"No MOD13Q1 NDVI scenes cover bbox {bbox}.",
                remedy="Widen the date range or check that the bbox is over land.",
            )

        scene = scenes[0]
        item_id = scene["id"]
        tile_url = (
            f"{self.TILER_ENDPOINT}/item/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@1x"
            f"?collection=modis-13Q1-061&item={item_id}"
            f"&assets=250m_16_days_NDVI&rescale=1000,8000&colormap_name=greens"
        )
        return success(
            Provenance(
                backend="planetary-computer",
                collection="modis-13Q1-061",
                scene_id=item_id,
                datetime=scene.get("datetime"),
                resolution="250m",
                notes=[
                    "MOD13Q1 NDVI, 16-day composite. Vegetation index, not canopy cover.",
                    "Tile colours are a rescaled display stretch (1000-8000); "
                    "read values from the array API, not from pixel colour.",
                ],
                requested={"bbox": bbox},
            ),
            kind="tile_layer",
            tile_url=tile_url,
            layer_name=f"MODIS NDVI 250m ({item_id[:16]})",
        )

    def sentinel2_visual_tiles(self, bbox: List[float]) -> Dict[str, Any]:
        """10 m Sentinel-2 L2A true-colour tiles."""
        scenes = self.search(bbox, collection="sentinel-2-l2a", max_items=5)
        if not scenes:
            return unavailable(
                reason=f"No Sentinel-2 L2A scenes under 40% cloud cover bbox {bbox}.",
                remedy="Widen the date range or raise max_cloud_cover.",
            )

        scene = scenes[0]
        item_id = scene["id"]
        tile_url = (
            f"{self.TILER_ENDPOINT}/item/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@1x"
            f"?collection=sentinel-2-l2a&item={item_id}&assets=visual"
        )
        return success(
            Provenance(
                backend="planetary-computer",
                collection="sentinel-2-l2a",
                scene_id=item_id,
                datetime=scene.get("datetime"),
                resolution="10m",
                notes=[f"Scene cloud cover: {scene.get('cloud_cover')}%."],
                requested={"bbox": bbox},
            ),
            kind="tile_layer",
            tile_url=tile_url,
            layer_name=f"Sentinel-2 10m visual ({item_id[:16]})",
            cloud_cover=scene.get("cloud_cover"),
        )

    def gibs_tiles(self, layer: str = "MODIS_Terra_CorrectedReflectance_TrueColor",
                   date: Optional[str] = None) -> Dict[str, Any]:
        """Global NASA GIBS WMTS tiles for a given layer and day.

        `date` defaults to a few days back because GIBS publishes with a lag.
        The date actually used is recorded in the provenance rather than being
        silently frozen in the URL.
        """
        date = date or _gibs_default_date()
        ext = "png" if "Land_Surface_Temp" in layer else "jpg"
        tile_url = (
            f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}"
            f"/default/{date}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.{ext}"
        )
        resolution = "1km" if "Land_Surface_Temp" in layer else "250m"
        return success(
            Provenance(
                backend="nasa-gibs",
                collection=layer,
                datetime=date,
                resolution=resolution,
                notes=[f"Single-day global composite for {date}."],
                requested={"layer": layer, "date": date},
            ),
            kind="tile_layer",
            tile_url=tile_url,
            layer_name=f"{layer.replace('_', ' ')} ({date})",
        )

    def tiles_for(self, bbox: List[float], layer: str = "ndvi") -> Dict[str, Any]:
        """Return a display tile layer for a named product.

        Recognised layers: `ndvi` (MODIS 250 m), `sentinel2` (10 m true colour),
        `true_color` (MODIS global), `lst` (MODIS thermal, 1 km).
        """
        key = layer.lower()
        if key in ("ndvi", "modis_ndvi", "vegetation"):
            return self.modis_ndvi_tiles(bbox)
        if key in ("sentinel2", "s2_visual", "optical"):
            return self.sentinel2_visual_tiles(bbox)
        if key in ("true_color", "modis_true_color", "modis_rgb"):
            return self.gibs_tiles("MODIS_Terra_CorrectedReflectance_TrueColor")
        if key in ("lst", "thermal", "lst_anomaly"):
            return self.gibs_tiles("MODIS_Terra_Land_Surface_Temp_Day")
        return unavailable(
            reason=f"No zero-credential tile layer is available for '{layer}'.",
            remedy=(
                "Computing this index requires pixel values. Connect Google Earth "
                "Engine, or use a layer from: ndvi, sentinel2, true_color, lst."
            ),
        )

    # ------------------------------------------------------------------
    # Raster arrays (numeric pixel data)
    # ------------------------------------------------------------------

    def read_cog_window(
        self, cog_url: str, bbox: List[float], report_errors: bool = True
    ) -> Optional[np.ndarray]:
        """Read a windowed sub-array from a remote COG over HTTP range requests.

        `bbox` is given in EPSG:4326 and reprojected into the raster's own CRS
        before the window is computed. Sentinel-2 COGs are in UTM, so reading
        with unprojected degrees would address the wrong pixels entirely.
        """
        if not RASTERIO_AVAILABLE:
            return None
        try:
            with rasterio.open(cog_url) as src:
                if src.crs and src.crs.to_epsg() != 4326:
                    left, bottom, right, top = transform_bounds(
                        "EPSG:4326", src.crs, *bbox, densify_pts=21
                    )
                else:
                    left, bottom, right, top = bbox
                window = from_bounds(left, bottom, right, top, transform=src.transform)
                return src.read(1, window=window, boundless=True, fill_value=0)
        except Exception as e:
            if report_errors:
                print(f"[earth-bridge] COG read failed: {e}")
            self._last_cog_error = str(e)
            return None

    @staticmethod
    def _scale_s2_reflectance(arr: np.ndarray, scene_datetime: Optional[str]) -> np.ndarray:
        """Convert Sentinel-2 digital numbers to surface reflectance.

        Applies the baseline 04.00 offset for scenes acquired on or after
        2022-01-25, and masks zeros, which are nodata rather than a reflectance
        of zero.
        """
        out = arr.astype(np.float32)
        out[out == 0] = np.nan

        apply_offset = True
        if scene_datetime:
            try:
                acquired = _dt.date.fromisoformat(scene_datetime[:10])
                apply_offset = acquired >= S2_BASELINE_0400_DATE
            except ValueError:
                pass

        if apply_offset:
            out = out + S2_BOA_OFFSET
        return out / S2_BOA_QUANTIFICATION

    def fetch_raster_for_bbox(
        self,
        bbox: List[float],
        index_type: str = "ndvi",
        collection: str = "sentinel-2-l2a",
    ) -> Dict[str, Any]:
        """Read Sentinel-2 bands as numeric arrays for a bounding box.

        Currently unavailable: Planetary Computer returns HTTP 409 for anonymous
        reads of signed assets, so no pixels can be retrieved. Rather than return
        substitute values, this reports the failure and points at the working
        alternative.
        """
        if not RASTERIO_AVAILABLE:
            return unavailable(
                reason="rasterio is not installed, so COGs cannot be read.",
                remedy="pip install 'earth-bridge[stac]'",
            )

        scenes = self.search(bbox, collection=collection, max_items=1)
        if not scenes:
            return unavailable(
                reason=f"No {collection} scenes cover bbox {bbox}.",
                remedy="Widen the date range or raise max_cloud_cover.",
            )

        scene = scenes[0]
        assets = scene.get("assets", {})
        band_keys = {
            "nir": "B08", "red": "B04", "green": "B03",
            "swir": "B11", "swir2": "B12",
        }
        self._last_cog_error = None
        arrays: Dict[str, Optional[np.ndarray]] = {}
        # Only the first failure is reported. All five bands live in the same
        # container, so when one is unreachable the rest fail identically and
        # printing each one buries the actual cause.
        for position, (name, key) in enumerate(band_keys.items()):
            href = assets.get(key, {}).get("href")
            raw = (
                self.read_cog_window(href, bbox, report_errors=(position == 0))
                if href else None
            )
            arrays[f"{name}_array"] = (
                self._scale_s2_reflectance(raw, scene.get("datetime"))
                if raw is not None else None
            )

        if arrays["nir_array"] is None or arrays["red_array"] is None:
            detail = self._last_cog_error or "no reason reported"
            return unavailable(
                reason=(
                    f"Could not read Sentinel-2 COG pixels from Planetary Computer: "
                    f"{detail}. Anonymous reads of signed assets currently return "
                    "HTTP 409."
                ),
                remedy=(
                    "Connect Google Earth Engine to compute this index server-side "
                    "(eb.compute_index works once Earth Engine is initialised). "
                    "The zero-credential array path is targeted for 0.4.0."
                ),
                scene_id=scene.get("id"),
            )

        return success(
            Provenance(
                backend="planetary-computer",
                collection=collection,
                scene_id=scene.get("id"),
                datetime=scene.get("datetime"),
                resolution="10m",
                notes=[
                    "Surface reflectance scaled by 1/10000 with baseline 04.00 "
                    "offset applied where the acquisition date requires it.",
                    "Zeros masked as nodata. No cloud or shadow mask has been "
                    "applied: values over cloud are not valid surface reflectance.",
                ],
                requested={"bbox": bbox, "index_type": index_type},
            ),
            kind="raster",
            **arrays,
        )


# Previous class name, kept so existing imports keep working.
ProductionSTACEngine = STACBackend
