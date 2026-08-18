"""
Split a large bounding box into a grid of smaller tiles.

Tiles are sized in degrees, which is convenient for addressing but is not equal
area: 0.1 degrees of longitude spans about 11 km at the equator and about 7 km at
50 degrees latitude. Each tile therefore reports its approximate ground width and
height so a caller can see the variation rather than assume uniform tiles.
"""

from typing import List, Dict, Any
import math

# Mean Earth radius, WGS84 authalic sphere.
_EARTH_RADIUS_KM = 6371.0088
_KM_PER_DEG_LAT = math.pi * _EARTH_RADIUS_KM / 180.0


def _edges(low: float, high: float, step: float) -> List[float]:
    """Tile edges from `low` to `high`, with a final partial tile if needed.

    Built by multiplying the step rather than accumulating it, so the values do
    not drift (repeated addition produced edges like 78.19999999999999).
    """
    if step <= 0:
        raise ValueError(f"tile_size_deg must be positive, got {step}.")
    count = max(1, math.ceil(round((high - low) / step, 9)))
    edges = [round(low + i * step, 9) for i in range(count)]
    edges.append(round(high, 9))
    return edges


def split_bbox(bbox: List[float], tile_size_deg: float = 0.1) -> List[Dict[str, Any]]:
    """Split `bbox` into grid tiles.

    Args:
        bbox: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
        tile_size_deg: Tile edge length in degrees.

    Returns:
        Tiles in row-major order, each with `tile_id`, `bbox`, `geometry` and
        `approx_km` giving the tile's ground dimensions at its own latitude.

    Raises:
        ValueError: If the bbox is malformed, out of range, or crosses the
            antimeridian. The previous implementation returned an empty list for
            an antimeridian bbox, which looked like "no tiles here" rather than
            an unsupported input.
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError(
            f"Invalid bbox {bbox!r}: expected [min_lon, min_lat, max_lon, max_lat]."
        )
    min_x, min_y, max_x, max_y = [float(v) for v in bbox]

    if not (-180 <= min_x <= 180 and -180 <= max_x <= 180):
        raise ValueError(f"Invalid bbox {bbox!r}: longitude outside [-180, 180].")
    if not (-90 <= min_y <= 90 and -90 <= max_y <= 90):
        raise ValueError(f"Invalid bbox {bbox!r}: latitude outside [-90, 90].")
    if min_x >= max_x:
        raise ValueError(
            f"Invalid bbox {bbox!r}: min_lon must be less than max_lon. "
            "Bounding boxes crossing the antimeridian are not supported; split "
            "the request into one box east of 180 and one west of -180."
        )
    if min_y >= max_y:
        raise ValueError(f"Invalid bbox {bbox!r}: min_lat must be less than max_lat.")

    xs = _edges(min_x, max_x, tile_size_deg)
    ys = _edges(min_y, max_y, tile_size_deg)

    tiles: List[Dict[str, Any]] = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            mid_lat_rad = math.radians((y0 + y1) / 2.0)
            tiles.append({
                "tile_id": f"tile_{len(tiles) + 1:04d}",
                "bbox": [x0, y0, x1, y1],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
                    ]],
                },
                "approx_km": {
                    "width": round((x1 - x0) * _KM_PER_DEG_LAT * math.cos(mid_lat_rad), 2),
                    "height": round((y1 - y0) * _KM_PER_DEG_LAT, 2),
                },
            })
    return tiles


class BoundingBoxGridSplitter:
    """Deprecated wrapper. Use `split_bbox`."""

    @staticmethod
    def split_bbox(bbox: List[float], tile_size_deg: float = 0.1) -> List[Dict[str, Any]]:
        return split_bbox(bbox, tile_size_deg=tile_size_deg)


def partition_state_bbox(bbox: List[float], tile_size_deg: float = 0.1) -> List[Dict[str, Any]]:
    return split_bbox(bbox, tile_size_deg=tile_size_deg)
