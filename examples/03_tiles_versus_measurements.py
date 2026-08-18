"""
Example 03 — Distinguishing display tiles from measured values.

A tile layer is rendered imagery: it can be displayed, but no numeric value can
be read from it. A measured statistic is derived by reducing pixel values over
the requested region, which currently requires Earth Engine.

This example requests both and reports the result of each, including the case in
which the measurement is unavailable.

Run:  python examples/03_tiles_versus_measurements.py
"""

import earthbridge as eb

BBOX = [78.40, 17.35, 78.50, 17.45]


def show(result: dict, heading: str) -> None:
    print(f"\n{heading}")
    print("-" * len(heading))

    if result["status"] != "success":
        print(f"  unavailable: {result['reason']}")
        if result.get("remedy"):
            print(f"  what to do:  {result['remedy']}")
        return

    provenance = result["provenance"]
    print(f"  kind:       {result['kind']}")
    print(f"  backend:    {provenance['attribution']}")
    print(f"  collection: {provenance['collection']}")
    print(f"  date:       {provenance['datetime']}")
    print(f"  resolution: {provenance['resolution']}")

    stats = result.get("stats")
    if stats and stats.get("mean") is not None:
        print(f"  mean:       {stats['mean']}")
        print(f"  range:      {stats.get('min')} to {stats.get('max')}")
    else:
        print("  mean:       not measured — this is imagery, not data")

    for note in provenance.get("notes", []):
        print(f"  note:       {note}")


def main() -> int:
    # Works with no credentials. Returns a URL template for a map.
    show(eb.get_tiles(BBOX, layer="ndvi"), "MODIS NDVI tile layer (no credentials)")

    # Needs Earth Engine. Returns a number, or an explanation of why it cannot.
    show(eb.compute_index(BBOX, index="ndvi"), "Sentinel-2 NDVI statistics")

    # Canopy cover has no zero-credential route at all: Planetary Computer does
    # not carry MOD44B.
    show(eb.get_modis_tcc(BBOX, year=2020), "Tree canopy cover (MOD44B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
