"""
Building footprints from Overture Maps, falling back to OpenStreetMap.

Overture is queried first, over S3 with DuckDB, reading only the row groups that
intersect the requested bounding box. If that is unavailable — DuckDB missing, no
network, an S3 error, or a release that has been withdrawn — the query falls back
to the OpenStreetMap Overpass API.

That fallback changes the licence. Overture buildings are ODbL or CDLA depending
on the contributing source; OpenStreetMap is ODbL with share-alike obligations.
So the returned GeoDataFrame always carries a `source` column, and the licence
terms are attached to `gdf.attrs["provenance"]`. Callers redistributing this data
need to read them.
"""

from typing import List, Dict, Any, Optional
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from .provenance import Provenance

# Checked without importing: the Overture query runs in a subprocess, so this
# process never needs duckdb loaded in its own address space.
DUCKDB_AVAILABLE = importlib.util.find_spec("duckdb") is not None

# The buildings theme is not partitioned geographically, so even a small bbox
# scans Parquet footers across the whole global dataset. A measured city-block
# query took 322 seconds, so the default is set well above that: too short a
# timeout silently downgrades a working Overture read to an OpenStreetMap
# fallback. Bounded all the same, so a hung S3 read cannot hang the caller.
OVERTURE_TIMEOUT_SECONDS = int(os.environ.get("EARTHBRIDGE_OVERTURE_TIMEOUT", "600"))


# Overture publishes monthly and prunes old releases: at the time of writing only
# the two most recent were still on S3. Pinning a release in source therefore
# breaks within a few months, so the current one is discovered at runtime. Set
# EARTHBRIDGE_OVERTURE_RELEASE to pin a specific release for reproducibility.
FALLBACK_OVERTURE_RELEASE = "2026-07-22.0"
OVERTURE_BUCKET_LISTING = (
    "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/"
    "?list-type=2&delimiter=/&prefix=release/"
)
_S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
_release_cache: Optional[str] = None


def latest_overture_release(timeout: int = 20) -> str:
    """Return the newest Overture release id available on S3.

    Falls back to a known-good release if the bucket cannot be listed. The
    result is cached for the life of the process.
    """
    global _release_cache
    if _release_cache is not None:
        return _release_cache

    try:
        import xml.etree.ElementTree as ET
        with urllib.request.urlopen(OVERTURE_BUCKET_LISTING, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
        releases = sorted(
            prefix.find("s3:Prefix", _S3_NS).text.split("/")[1]
            for prefix in root.findall("s3:CommonPrefixes", _S3_NS)
        )
        if releases:
            _release_cache = releases[-1]
            return _release_cache
    except Exception as e:
        print(f"[earth-bridge] Could not list Overture releases ({e}); using fallback.")

    _release_cache = FALLBACK_OVERTURE_RELEASE
    return _release_cache

BUILDING_COLUMNS = ["id", "name", "subtype", "height", "num_floors", "source", "geometry"]


class OvertureBackend:
    """Streams building footprints for a bounding box."""

    def __init__(self, release: Optional[str] = None):
        self._pinned_release = release or os.environ.get("EARTHBRIDGE_OVERTURE_RELEASE")
        # Nothing is connected, listed or loaded here. Construction must be cheap
        # and must not be able to fail, so the first query does the work.
        self.duckdb_error: Optional[str] = (
            None if DUCKDB_AVAILABLE
            else "duckdb is not installed; install with pip install 'earth-bridge[overture]'"
        )

    @property
    def release(self) -> str:
        """The Overture release in use: pinned if given, otherwise the newest."""
        return self._pinned_release or latest_overture_release()

    @property
    def parquet_glob(self) -> str:
        return (
            f"s3://overturemaps-us-west-2/release/{self.release}/"
            "theme=buildings/type=building/*"
        )

    def fetch_building_footprints(
        self,
        bbox: List[float],
        limit: int = 200,
        polygon_mask: Optional[Polygon] = None,
        allow_osm_fallback: bool = True,
    ) -> gpd.GeoDataFrame:
        """Fetch building footprints intersecting `bbox`.

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
            limit: Maximum features to return.
            polygon_mask: Optional geometry to clip results to.
            allow_osm_fallback: If False, an Overture failure returns an empty
                frame rather than substituting OpenStreetMap data. Set this when
                licence provenance must be Overture specifically.

        Returns:
            GeoDataFrame with a `source` column identifying each row's origin,
            and licence terms in `gdf.attrs["provenance"]`.
        """
        min_x, min_y, max_x, max_y = self._validate_bbox(bbox)

        gdf = self._fetch_overture([min_x, min_y, max_x, max_y], limit)
        if gdf is not None and len(gdf) > 0:
            return self._finalize(gdf, polygon_mask)

        if not allow_osm_fallback:
            return self._empty(
                Provenance(
                    backend="overture",
                    collection=f"buildings/{self.release}",
                    notes=[
                        f"Overture query returned no rows. DuckDB status: "
                        f"{self.duckdb_error or 'available'}.",
                        "OpenStreetMap fallback was disabled by the caller.",
                    ],
                    requested={"bbox": bbox, "limit": limit},
                )
            )

        osm_gdf = self._fetch_osm([min_x, min_y, max_x, max_y], limit)
        if osm_gdf is not None and len(osm_gdf) > 0:
            print(
                "[earth-bridge] Overture unavailable; returning OpenStreetMap "
                "buildings instead (ODbL share-alike). See gdf.attrs['provenance']."
            )
            return self._finalize(osm_gdf, polygon_mask)

        return self._empty(
            Provenance(
                backend="overture",
                collection=f"buildings/{self.release}",
                notes=[
                    "Neither Overture nor OpenStreetMap returned buildings for "
                    "this bounding box.",
                    f"DuckDB status: {self.duckdb_error or 'available'}.",
                ],
                requested={"bbox": bbox, "limit": limit},
            )
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _validate_bbox(bbox: List[float]) -> List[float]:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError(
                f"Invalid bbox {bbox!r}: expected [min_lon, min_lat, max_lon, max_lat]."
            )
        try:
            min_x, min_y, max_x, max_y = [float(v) for v in bbox]
        except (ValueError, TypeError):
            raise ValueError(f"Invalid bbox {bbox!r}: all four values must be numeric.")
        if min_x >= max_x or min_y >= max_y:
            raise ValueError(
                f"Invalid bbox {bbox!r}: min_lon/min_lat must be less than max_lon/max_lat."
            )
        if not (-180 <= min_x <= 180 and -180 <= max_x <= 180):
            raise ValueError(f"Invalid bbox {bbox!r}: longitude outside [-180, 180].")
        if not (-90 <= min_y <= 90 and -90 <= max_y <= 90):
            raise ValueError(f"Invalid bbox {bbox!r}: latitude outside [-90, 90].")
        return [min_x, min_y, max_x, max_y]

    def _fetch_overture(self, bbox: List[float], limit: int) -> Optional[gpd.GeoDataFrame]:
        """Run the Overture query in a subprocess and read back its Parquet output."""
        if not DUCKDB_AVAILABLE:
            return None

        with tempfile.TemporaryDirectory(prefix="eb_overture_") as tmp:
            out_path = os.path.join(tmp, "buildings.parquet")
            request = json.dumps({
                "glob": self.parquet_glob,
                "bbox": bbox,
                "limit": int(limit),
                "output": out_path,
            })
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "earthbridge._overture_worker", request],
                    capture_output=True, text=True,
                    timeout=OVERTURE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                self.duckdb_error = (
                    f"Overture query exceeded {OVERTURE_TIMEOUT_SECONDS}s. Raise "
                    "EARTHBRIDGE_OVERTURE_TIMEOUT or use a smaller bounding box."
                )
                print(f"[earth-bridge] {self.duckdb_error}")
                return None

            if proc.returncode != 0:
                self.duckdb_error = self._worker_error(proc)
                print(f"[earth-bridge] Overture query failed: {self.duckdb_error}")
                return None

            if not os.path.exists(out_path):
                self.duckdb_error = "Overture worker produced no output file."
                return None

            try:
                df = pd.read_parquet(out_path)
            except Exception as e:
                self.duckdb_error = f"Could not read Overture worker output: {e}"
                return None

        if len(df) == 0:
            return None

        gdf = gpd.GeoDataFrame(
            df.drop(columns=["geometry"]),
            geometry=gpd.GeoSeries.from_wkb(df["geometry"]),
            crs="EPSG:4326",
        )
        gdf["source"] = "overture"
        gdf.attrs["provenance"] = Provenance(
            backend="overture",
            collection=f"buildings/{self.release}",
            notes=[
                "Read directly from Overture Parquet on S3; no local copy was made.",
                "Per-feature licence depends on the contributing source; see the "
                "Overture attribution guidance.",
            ],
            requested={"bbox": bbox, "limit": limit},
        ).to_dict()
        return gdf

    @staticmethod
    def _worker_error(proc: subprocess.CompletedProcess) -> str:
        """Describe why the worker failed, including a native crash."""
        try:
            return json.loads(proc.stdout.strip().splitlines()[-1])["message"]
        except (ValueError, IndexError, KeyError):
            pass
        if proc.returncode < 0 or proc.returncode == 0xC0000005:
            return (
                f"DuckDB subprocess terminated abnormally (exit {proc.returncode}), "
                "most likely while loading its httpfs extension. Overture reads are "
                "unavailable on this machine; OpenStreetMap will be used instead."
            )
        detail = (proc.stderr or "").strip().splitlines()
        return detail[-1] if detail else f"worker exited {proc.returncode}"

    def _fetch_osm(self, bbox: List[float], limit: int) -> Optional[gpd.GeoDataFrame]:
        """Query the OpenStreetMap Overpass API for building ways."""
        min_x, min_y, max_x, max_y = bbox
        query = f"""
        [out:json][timeout:25];
        (way["building"]({min_y},{min_x},{max_y},{max_x}););
        out body;
        >;
        out skel qt;
        """
        try:
            req = urllib.request.Request(
                "https://overpass-api.de/api/interpreter",
                data=query.encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "earth-bridge/0.3.0",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[earth-bridge] Overpass query failed: {e}")
            return None

        elements = data.get("elements", [])
        nodes = {
            el["id"]: (el["lon"], el["lat"])
            for el in elements
            if el.get("type") == "node"
        }
        ways = [el for el in elements if el.get("type") == "way" and "nodes" in el]

        polygons, records = [], []
        for way in sorted(ways, key=lambda w: w["id"])[:limit]:
            pts = [nodes[nid] for nid in way["nodes"] if nid in nodes]
            if len(pts) < 3:
                continue
            poly = Polygon(pts)
            if not poly.is_valid:
                continue
            tags = way.get("tags", {})
            polygons.append(poly)
            records.append({
                "id": f"osm_way_{way['id']}",
                "name": tags.get("name"),
                "subtype": tags.get("building"),
                # Height is only reported where OSM actually records it. It was
                # previously defaulted to 12 m, which invented data for the
                # large majority of buildings that carry no height tag.
                "height": _parse_osm_height(tags),
                "num_floors": _parse_int(tags.get("building:levels")),
                "source": "openstreetmap",
            })

        if not polygons:
            return None

        gdf = gpd.GeoDataFrame(records, geometry=polygons, crs="EPSG:4326")
        gdf.attrs["provenance"] = Provenance(
            backend="openstreetmap",
            collection="overpass/way[building]",
            notes=[
                "Returned because Overture was unavailable. This is NOT Overture data.",
                "ODbL share-alike: derived databases must also be released under ODbL.",
                "height and num_floors are null where OpenStreetMap has no tag; "
                "they are not estimated.",
            ],
            requested={"bbox": bbox, "limit": limit},
        ).to_dict()
        return gdf

    @staticmethod
    def _finalize(
        gdf: gpd.GeoDataFrame, polygon_mask: Optional[Polygon]
    ) -> gpd.GeoDataFrame:
        if polygon_mask is not None:
            provenance = gdf.attrs.get("provenance")
            gdf = gdf[gdf.geometry.intersects(polygon_mask)].copy()
            gdf.attrs["provenance"] = provenance
        return gdf

    @staticmethod
    def _empty(provenance: Provenance) -> gpd.GeoDataFrame:
        gdf = gpd.GeoDataFrame(columns=BUILDING_COLUMNS, crs="EPSG:4326")
        gdf.attrs["provenance"] = provenance.to_dict()
        return gdf


def _parse_osm_height(tags: Dict[str, Any]) -> Optional[float]:
    """Read a height in metres from OSM tags, or None if not recorded."""
    raw = tags.get("height")
    if raw is not None:
        try:
            return float(str(raw).replace("m", "").strip())
        except ValueError:
            return None
    levels = _parse_int(tags.get("building:levels"))
    if levels is not None:
        # Nominal 3 m per storey. Derived, not measured.
        return float(levels) * 3.0
    return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


# Previous class name, kept so existing imports keep working.
ProductionOvertureEngine = OvertureBackend
