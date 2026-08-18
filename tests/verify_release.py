"""
Release verification: execute every code claim in the README and report pass/fail.

Run with:  python tests/verify_release.py

This is a smoke check, not a unit test suite. It makes real network calls to
Planetary Computer, Overture and OpenStreetMap, so it is slow and it can fail for
reasons that have nothing to do with this code. A proper suite with recorded
fixtures is the next step; until then this at least guarantees the documented
entry points execute.
"""
import warnings; warnings.filterwarnings("ignore")
import earthbridge as eb

BBOX = [78.40, 17.35, 78.50, 17.45]
results = []
def check(name, fn):
    try:
        fn(); results.append((True, name, ""))
    except Exception as e:
        results.append((False, name, f"{type(e).__name__}: {e}"))

def t_tiles():
    r = eb.get_tiles(BBOX, layer="ndvi")
    assert r["status"] == "success", r
    assert r["tile_url"].startswith("http")
    assert r["provenance"]["collection"] == "modis-13Q1-061"
    assert r["kind"] == "tile_layer"

def t_compute_unavailable():
    r = eb.compute_index(BBOX, index="ndvi")
    assert r["status"] == "unavailable"
    assert r["reason"] and r["remedy"]

def t_search():
    s = eb.search_stac(BBOX, collection="sentinel-2-l2a", max_items=8)
    assert s["status"] == "success" and s["count"] > 0
    assert s["items"][0]["datetime"]

def t_buildings():
    import os; os.environ["EARTHBRIDGE_OVERTURE_TIMEOUT"] = "20"
    b = eb.fetch_buildings(BBOX, limit=50)
    assert "source" in b.columns, b.columns.tolist()
    assert b.attrs["provenance"]["license"]

def t_partition():
    ts = eb.partition([76.0, 12.0, 85.0, 20.0], tile_size=0.1)
    assert len(ts) == 7200, len(ts)
    assert ts[0]["approx_km"]["width"] > 0

def t_export_report():
    # Built locally: Overpass is flaky and this check is about the writers.
    import geopandas as gpd
    from shapely.geometry import box
    b = gpd.GeoDataFrame(
        {"id": ["a", "b", "c"], "height": [10.0, 22.5, 7.0]},
        geometry=[box(78.40, 17.35, 78.42, 17.37),
                  box(78.42, 17.37, 78.44, 17.39),
                  box(78.44, 17.39, 78.46, 17.41)],
        crs="EPSG:4326")
    b.attrs["provenance"] = {"backend": "test", "license": "n/a"}
    assert eb.export(b, format="geojson", output="rc.geojson").endswith(".geojson")
    assert eb.export(b, format="parquet", output="rc.parquet").endswith(".parquet")
    assert eb.export(b, format="csv", output="rc.csv").endswith(".csv")
    assert eb.report(b, city_name="Hyderabad", output="rc.html").endswith(".html")

def t_tcc_needs_gee():
    r = eb.get_modis_tcc(BBOX, year=2020)
    assert r["status"] == "unavailable"
    assert "Earth Engine" in r["reason"]

def t_zonal_removed():
    from earthbridge.zonal_stats import compute_building_zonal_stats
    try:
        compute_building_zonal_stats(); raise AssertionError("should have raised")
    except NotImplementedError as e:
        assert "exactextract" in str(e)

def t_aliases():
    assert eb.ProductionSTACEngine is eb.STACBackend
    assert eb.ProductionOvertureEngine is eb.OvertureBackend
    assert eb.GEEOperationEngine is eb.EarthEngineBackend

for name, fn in [
    ("get_tiles returns a tile layer", t_tiles),
    ("compute_index reports an unavailable status", t_compute_unavailable),
    ("search_stac finds scenes", t_search),
    ("fetch_buildings records source and licence", t_buildings),
    ("partition splits a large bbox", t_partition),
    ("export to geojson, parquet, csv, and report", t_export_report),
    ("get_modis_tcc requires Earth Engine", t_tcc_needs_gee),
    ("zonal statistics raise with guidance", t_zonal_removed),
    ("deprecated aliases still resolve", t_aliases),
]:
    check(name, fn)

print()
for ok, name, err in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if err: print(f"        {err}")
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{len(results)-failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
