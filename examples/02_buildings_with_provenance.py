"""
Example 02 — Building footprints, and knowing where they came from.

earth-bridge tries Overture Maps first and falls back to OpenStreetMap. Those
two carry different licences, so the source is always recorded rather than
assumed. This example shows how to read it, and how to refuse the fallback when
the licence matters.

Run:  python examples/02_buildings_with_provenance.py
"""

import earthbridge as eb

BBOX = [78.44, 17.38, 78.46, 17.40]


def main() -> int:
    print(f"Fetching building footprints over {BBOX}\n")

    buildings = eb.fetch_buildings(BBOX, limit=200)
    if len(buildings) == 0:
        print("No buildings found here.")
        print(f"  {buildings.attrs['provenance']['notes']}")
        return 1

    provenance = buildings.attrs["provenance"]
    print(f"  {len(buildings)} features")
    print(f"  source:      {provenance['attribution']}")
    print(f"  licence:     {provenance['license']}")
    print(f"  licence url: {provenance['license_url']}")
    for note in provenance.get("notes", []):
        print(f"  note:        {note}")

    print(f"\n  source column: {buildings['source'].unique().tolist()}")
    with_height = buildings["height"].notna().sum()
    print(f"  height recorded for {with_height} of {len(buildings)} features")
    print("  (heights are null where the source has no value; they are not estimated)")

    out = eb.export(buildings, format="geojson", output="buildings.geojson")
    print(f"\n  wrote {out}")

    report = eb.report(buildings, city_name="Hyderabad buildings", output="buildings_map.html")
    print(f"  wrote {report}")

    # Where redistribution under a specific licence is required, do not accept a
    # substitute source silently.
    print("\nRequiring Overture specifically (no OpenStreetMap fallback):")
    strict = eb.fetch_buildings(BBOX, limit=200, allow_osm_fallback=False)
    if len(strict) == 0:
        print("  Overture returned nothing, and no substitute was used.")
    else:
        print(f"  {len(strict)} Overture features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
