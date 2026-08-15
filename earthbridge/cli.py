"""Command line interface for earth-bridge."""

import argparse
import json
import os
import subprocess
import sys
import threading

from .tiling import split_bbox
from .stac_reader import search_stac_anonymously
from .gee_stac import build_stac_item


def _parse_bbox(text: str):
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"bbox must be 'min_lon,min_lat,max_lon,max_lat', got {text!r}."
        )
    try:
        return [float(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError(f"bbox values must be numeric, got {text!r}.")


def find_web_studio_server() -> str:
    """Locate the Studio server across editable, wheel and virtualenv installs."""
    try:
        from web_studio import SERVER_PATH
        if os.path.exists(SERVER_PATH):
            return SERVER_PATH
    except ImportError:
        pass

    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "web_studio", "server.py"),
        os.path.join(os.path.dirname(__file__), "web_studio", "server.py"),
        os.path.join(sys.prefix, "web_studio", "server.py"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)

    raise FileNotFoundError(
        "Could not find the Studio server. This usually means earth-bridge was "
        "installed from a wheel built before 0.3.0, which omitted web_studio. "
        "Reinstall with: pip install --upgrade --force-reinstall earth-bridge"
    )


def launch_studio(port: int = 8000, open_browser: bool = True) -> int:
    """Start the Studio server and open it in a browser.

    The browser is opened only once the server reports the port it actually
    bound. It walks past busy ports, so opening the requested port immediately
    used to land on a blank page.
    """
    import webbrowser

    server_path = find_web_studio_server()
    print(f"[earth-bridge] Starting Studio from {server_path}")

    process = subprocess.Popen(
        [sys.executable, server_path, str(port)],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
    )

    def _relay():
        opened = False
        for line in process.stdout:
            if line.startswith("EARTHBRIDGE_STUDIO_URL="):
                url = line.split("=", 1)[1].strip()
                if open_browser and not opened:
                    opened = True
                    webbrowser.open_new_tab(url)
                continue
            sys.stdout.write(line)

    reader = threading.Thread(target=_relay, daemon=True)
    reader.start()

    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="earthbridge",
        description="Explore Earth observation data over a region of interest.",
    )
    sub = parser.add_subparsers(dest="command")

    p_studio = sub.add_parser("studio", help="Launch the interactive Studio in a browser")
    p_studio.add_argument("--port", type=int, default=8000)
    p_studio.add_argument("--no-browser", action="store_true")

    p_search = sub.add_parser("search", help="List scenes covering a bounding box")
    p_search.add_argument("--bbox", type=_parse_bbox, required=True)
    p_search.add_argument("--collection", default="sentinel-2-l2a")
    p_search.add_argument("--max-items", type=int, default=5)

    p_index = sub.add_parser("index", help="Compute a spectral index over a bounding box")
    p_index.add_argument("--bbox", type=_parse_bbox, required=True)
    p_index.add_argument("--type", choices=["ndvi", "ndwi", "lswi", "nbr", "ndbi"], default="ndvi")
    p_index.add_argument("--start-date", default="2024-01-01")
    p_index.add_argument("--end-date", default="2024-06-01")

    p_part = sub.add_parser("partition", help="Split a bounding box into grid tiles")
    p_part.add_argument("--bbox", type=_parse_bbox, required=True)
    p_part.add_argument("--tile-size", type=float, default=0.1)

    p_stac = sub.add_parser("stac-item", help="Write a STAC 1.0.0 Item JSON file")
    p_stac.add_argument("--id", default="item-01")
    p_stac.add_argument("--bbox", type=_parse_bbox, required=True)
    p_stac.add_argument("--datetime", default="2026-01-01T00:00:00Z")
    p_stac.add_argument("--output", default="stac_item.json")

    args = parser.parse_args()

    if args.command == "studio":
        return launch_studio(port=args.port, open_browser=not args.no_browser)

    if args.command == "search":
        res = search_stac_anonymously(
            args.bbox, collection=args.collection, max_items=args.max_items
        )
        if res["status"] != "success":
            print(f"[earth-bridge] {res.get('message')}")
            return 1
        print(f"[earth-bridge] {res['count']} scene(s) in {args.collection}:")
        for item in res["items"]:
            cloud = item.get("cloud_cover")
            cloud_str = f"{cloud:.1f}% cloud" if isinstance(cloud, (int, float)) else "cloud n/a"
            print(f"  {item['id']}  {item['datetime']}  {cloud_str}")
        return 0

    if args.command == "index":
        # Imported here so the other subcommands do not pay for geopandas.
        from . import compute_index
        res = compute_index(
            bbox=args.bbox, index=args.type,
            start_date=args.start_date, end_date=args.end_date,
        )
        if res.get("status") != "success":
            print(f"[earth-bridge] {args.type.upper()} unavailable: {res.get('reason')}")
            if res.get("remedy"):
                print(f"               {res['remedy']}")
            return 1
        stats = res.get("stats") or {}
        mean = stats.get("mean", res.get("index_mean"))
        print(f"[earth-bridge] {args.type.upper()} mean {mean}")
        prov = res.get("provenance") or {}
        print(f"               source: {prov.get('backend')} / {prov.get('collection')}")
        for note in prov.get("notes", []):
            print(f"               note: {note}")
        return 0

    if args.command == "partition":
        tiles = split_bbox(args.bbox, tile_size_deg=args.tile_size)
        first = tiles[0]["approx_km"]
        print(
            f"[earth-bridge] {len(tiles)} tiles of about "
            f"{first['width']} x {first['height']} km."
        )
        for tile in tiles[:3]:
            print(f"  {tile['tile_id']}: {tile['bbox']}")
        if len(tiles) > 3:
            print(f"  ... and {len(tiles) - 3} more")
        return 0

    if args.command == "stac-item":
        lon0, lat0, lon1, lat1 = args.bbox
        path = build_stac_item(
            item_id=args.id,
            bbox=args.bbox,
            geometry={
                "type": "Polygon",
                "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1],
                                 [lon0, lat1], [lon0, lat0]]],
            },
            datetime_utc=args.datetime,
            assets={},
            output_path=args.output,
        )
        print(f"[earth-bridge] Wrote STAC Item to {os.path.abspath(path)}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
