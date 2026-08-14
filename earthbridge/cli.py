"""
CLI Interface for earth-bridge package
======================================
"""

import sys
import os
import argparse
import json
import numpy as np
import subprocess

from .spectral_indexes import SpectralIndexCalculator
from .gee_stac import GEEToSTACConverter
from .tiling import partition_state_bbox
from .stac_reader import search_stac_anonymously
from .exporter import export_open_dataset

def main():
    parser = argparse.ArgumentParser(
        description="earth-bridge: Open Earth Data & Cross-Cloud STAC Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: index
    index_parser = subparsers.add_parser("index", help="Compute spectral index from band values")
    index_parser.add_argument("--type", choices=["ndvi", "ndwi", "lswi", "nbr", "ndbi"], default="ndvi")
    index_parser.add_argument("--band1", type=float, required=True, help="NIR or Primary band value")
    index_parser.add_argument("--band2", type=float, required=True, help="RED/SWIR or Secondary band value")

    # Command: gee2stac
    gee_parser = subparsers.add_parser("gee2stac", help="Generate STAC 1.0.0 JSON metadata for GEE asset")
    gee_parser.add_argument("--id", type=str, default="gee-sample-01")
    gee_parser.add_argument("--bbox", type=str, default="78.4,17.3,78.5,17.4", help="min_lon,min_lat,max_lon,max_lat")
    gee_parser.add_argument("--output", type=str, default="stac_item.json")

    # Command: partition (State-Scale BBox Grid Partitioning)
    partition_parser = subparsers.add_parser("partition", help="Partition a state-scale BBox into memory-safe grid tiles")
    partition_parser.add_argument("--bbox", type=str, default="78.0,17.0,79.0,18.0", help="min_lon,min_lat,max_lon,max_lat")
    partition_parser.add_argument("--tile-size", type=float, default=0.1, help="Tile size in degrees (~11km)")

    # Command: stac-search (Zero-Auth STAC Search)
    stac_parser = subparsers.add_parser("stac-search", help="Anonymous STAC API search against MS Planetary Computer")
    stac_parser.add_argument("--bbox", type=str, default="78.4,17.3,78.5,17.4")
    stac_parser.add_argument("--collection", type=str, default="sentinel-2-l2a")

    # Command: studio
    studio_parser = subparsers.add_parser("studio", help="Launch interactive EarthBridge Web Workbench server")
    studio_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "index":
        b1, b2 = np.array([args.band1]), np.array([args.band2])
        if args.type == "ndvi":
            val = SpectralIndexCalculator.ndvi(b1, b2)[0]
        elif args.type == "ndwi":
            val = SpectralIndexCalculator.ndwi(b1, b2)[0]
        elif args.type == "lswi":
            val = SpectralIndexCalculator.lswi(b1, b2)[0]
        elif args.type == "nbr":
            val = SpectralIndexCalculator.nbr(b1, b2)[0]
        else:
            val = SpectralIndexCalculator.ndbi(b1, b2)[0]
        print(f"[earth-bridge] Calculated {args.type.upper()}: {val:.4f}")

    elif args.command == "gee2stac":
        bbox_coords = [float(x.strip()) for x in args.bbox.split(",")]
        converter = GEEToSTACConverter()
        item = converter.image_to_stac_item(
            item_id=args.id,
            bbox=bbox_coords,
            geometry={"type": "Polygon", "coordinates": [[[bbox_coords[0], bbox_coords[1]], [bbox_coords[2], bbox_coords[1]], [bbox_coords[2], bbox_coords[3]], [bbox_coords[0], bbox_coords[3]], [bbox_coords[0], bbox_coords[1]]]]},
            datetime_utc="2026-08-01T10:30:00Z",
            assets={"B4": {"href": "https://earthengine.googleapis.com/sample_b4.tif", "type": "image/tiff"}},
            properties={"eo:cloud_cover": 3.2}
        )
        converter.export_stac_json(item, args.output)
        print(f"[earth-bridge] Successfully exported STAC item metadata to: {args.output}")

    elif args.command == "partition":
        bbox_coords = [float(x.strip()) for x in args.bbox.split(",")]
        tiles = partition_state_bbox(bbox_coords, tile_size_deg=args.tile_size)
        print(f"[earth-bridge] Partitioned state BBox {bbox_coords} into {len(tiles)} memory-safe grid tiles.")
        for t in tiles[:3]:
            print(f" -> {t['tile_id']}: BBox {t['bbox']}")

    elif args.command == "stac-search":
        bbox_coords = [float(x.strip()) for x in args.bbox.split(",")]
        res = search_stac_anonymously(bbox_coords, collection=args.collection)
        print(f"[earth-bridge Zero-Auth STAC] Search Status: {res['status']} | Found {res['count']} items.")
        for item in res["items"][:3]:
            print(f" -> Item ID: {item['id']} | Date: {item['datetime']} | Cloud Cover: {item['cloud_cover']}%")

    elif args.command == "studio":
        # Launch server using subprocess to correctly load it outside the package namespace
        server_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web_studio', 'server.py')
        print(f"[earth-bridge] Starting studio on port {args.port}...")
        subprocess.run([sys.executable, server_path])

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
