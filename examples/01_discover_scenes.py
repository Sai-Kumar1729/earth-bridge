"""
Example 01 — What imagery exists over my area?

No credentials needed. This is the question worth asking before writing any
analysis: is there usable imagery here at all, on what dates, and how cloudy?

Run:  python examples/01_discover_scenes.py
"""

import earthbridge as eb

# Hyderabad, India.
BBOX = [78.35, 17.30, 78.55, 17.50]


def main() -> int:
    print(f"Searching Sentinel-2 L2A over {BBOX}\n")

    result = eb.search_stac(BBOX, collection="sentinel-2-l2a", max_items=8)
    if result["status"] != "success":
        print(f"No scenes: {result.get('message')}")
        return 1

    print(f"{result['count']} scene(s) found:\n")
    for item in result["items"]:
        cloud = item.get("cloud_cover")
        cloud_str = f"{cloud:5.1f}%" if isinstance(cloud, (int, float)) else "    ?"
        print(f"  {item['datetime'][:10]}  cloud {cloud_str}  {item['id']}")

    print("\nSplitting the area into tiles for chunked processing:\n")
    tiles = eb.partition(BBOX, tile_size=0.05)
    first = tiles[0]["approx_km"]
    print(f"  {len(tiles)} tiles, each about {first['width']} x {first['height']} km")
    for tile in tiles[:3]:
        print(f"    {tile['tile_id']}: {tile['bbox']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
