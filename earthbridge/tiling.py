"""
State-Scale Grid Partitioning & Tiling Module
==============================================
Splits large state-scale Bounding Boxes into sub-district grid tiles for memory-safe processing on 16GB laptops.
"""

from typing import List, Dict, Any
import numpy as np

class BoundingBoxGridSplitter:
    """Partitions state-scale bounding boxes into chunked sub-grids for low-memory spatial execution."""

    @staticmethod
    def split_bbox(
        bbox: List[float],
        tile_size_deg: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        Splits a bounding box [min_lon, min_lat, max_lon, max_lat] into grid chunks.

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]
            tile_size_deg: Size of each chunk in degrees (~11km at equator for 0.1 deg)

        Returns:
            List of tile dicts with tile_id, bbox, and polygon geometry
        """
        min_x, min_y, max_x, max_y = bbox
        
        x_coords = np.arange(min_x, max_x, tile_size_deg)
        if len(x_coords) == 0 or x_coords[-1] < max_x:
            x_coords = np.append(x_coords, max_x)
            
        y_coords = np.arange(min_y, max_y, tile_size_deg)
        if len(y_coords) == 0 or y_coords[-1] < max_y:
            y_coords = np.append(y_coords, max_y)

        tiles = []
        count = 1
        for i in range(len(x_coords) - 1):
            for j in range(len(y_coords) - 1):
                t_min_x = float(x_coords[i])
                t_max_x = float(x_coords[i+1])
                t_min_y = float(y_coords[j])
                t_max_y = float(y_coords[j+1])
                
                tile_bbox = [t_min_x, t_min_y, t_max_x, t_max_y]
                tiles.append({
                    "tile_id": f"tile_{count:04d}",
                    "bbox": tile_bbox,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[t_min_x, t_min_y], [t_max_x, t_min_y], [t_max_x, t_max_y], [t_min_x, t_max_y], [t_min_x, t_min_y]]]
                    }
                })
                count += 1

        return tiles

def partition_state_bbox(bbox: List[float], tile_size_deg: float = 0.1) -> List[Dict[str, Any]]:
    return BoundingBoxGridSplitter.split_bbox(bbox, tile_size_deg=tile_size_deg)
