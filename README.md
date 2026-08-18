# earth-bridge

Define a region of interest and find out what Earth observation data exists over
it — across Microsoft Planetary Computer, NASA GIBS, Google Earth Engine and
Overture Maps, from one Python API and a local browser workbench.

[![PyPI](https://img.shields.io/pypi/v/earth-bridge?color=blue)](https://pypi.org/project/earth-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)

> **Alpha.** This is a reconnaissance tool: it answers *what data is here and what
> does it look like*, not *what is the value*. Measured statistics currently
> require Google Earth Engine. Read [Scope and limits](#scope-and-limits) before
> depending on it for anything, and [ROADMAP.md](ROADMAP.md) for what is being
> built next and what has been ruled out.

---

## Install

```bash
pip install earth-bridge                 # core: search, tiles, buildings, export
pip install 'earth-bridge[gee]'          # + Earth Engine, for measured statistics
pip install 'earth-bridge[overture]'     # + DuckDB, for Overture building reads
pip install 'earth-bridge[all]'          # everything
```

## Launch the workbench

```bash
earthbridge studio
```

Draw a box or upload a boundary, pick a product, and see it on the map. The
server binds to loopback only.

---

## Two kinds of result

This distinction runs through the whole library, and getting it wrong is the
easiest way to misread output.

| | Tile layer | Measured statistics |
|---|---|---|
| What it is | Rendered PNG/JPEG imagery | Numbers reduced from pixel values |
| Credentials | None | Google Earth Engine |
| Can you read a value? | **No** — colours are a display stretch | Yes |
| `result["kind"]` | `tile_layer` | `tile_layer_with_stats` |

```python
import earthbridge as eb

BBOX = [78.40, 17.35, 78.50, 17.45]

# No credentials. Imagery you can look at.
tiles = eb.get_tiles(BBOX, layer="ndvi")
print(tiles["tile_url"])                      # XYZ template for a map
print(tiles["provenance"]["collection"])      # modis-13Q1-061

# Earth Engine. A number you can use.
result = eb.compute_index(BBOX, index="ndvi")
if result["status"] == "success":
    print(result["stats"]["mean"])
else:
    print(result["reason"], "→", result["remedy"])
```

## What works without credentials

```python
# Which scenes cover this area, when, and how cloudy?
scenes = eb.search_stac(BBOX, collection="sentinel-2-l2a", max_items=8)
for item in scenes["items"]:
    print(item["datetime"][:10], item["cloud_cover"], item["id"])

# Building footprints, with their origin recorded
buildings = eb.fetch_buildings(BBOX, limit=500)
print(buildings["source"].unique())                    # ['overture'] or ['openstreetmap']
print(buildings.attrs["provenance"]["license"])

# Split a large area into tiles
tiles = eb.partition([76.0, 12.0, 85.0, 20.0], tile_size=0.1)
print(len(tiles), tiles[0]["approx_km"])               # degree tiles are not equal area

# Export, and write a standalone HTML map
eb.export(buildings, format="geojson", output="buildings.geojson")
eb.report(buildings, city_name="Hyderabad", output="map.html")
```

## What needs Earth Engine

Run `earthengine authenticate` once, then set a Cloud project id — either
`EE_PROJECT_ID` in the environment, or in the Studio header.

```python
eb.compute_index(BBOX, index="ndvi")     # also ndwi, lswi, nbr, ndbi
eb.get_modis_tcc(BBOX, year=2020)        # percent tree canopy cover (MOD44B)
```

Earth Engine does the cloud masking, compositing and reduction server-side, so
local memory use stays flat regardless of area.

---

## Every result carries its provenance

```python
>>> eb.get_tiles(BBOX, layer="ndvi")["provenance"]
{'backend': 'planetary-computer',
 'collection': 'modis-13Q1-061',
 'scene_id': 'MOD13Q1.A2026...',
 'datetime': '2026-07-12T00:00:00Z',
 'resolution': '250m',
 'attribution': 'Microsoft Planetary Computer',
 'license': 'Varies by collection; most are open (CC-BY-4.0 or public domain)',
 'notes': ['MOD13Q1 NDVI, 16-day composite. Vegetation index, not canopy cover.',
           'Tile colours are a rescaled display stretch...']}
```

This matters most where earth-bridge falls back between providers. A building
query can be answered by Overture or by OpenStreetMap, and those carry different
licences — OpenStreetMap is ODbL with share-alike obligations. The fallback is
allowed; hiding it is not. Pass `allow_osm_fallback=False` to require Overture.

Failures carry a reason and a remedy instead of a substitute value:

```python
>>> eb.compute_index(BBOX, index="ndvi")
{'status': 'unavailable',
 'reason': "Could not read Sentinel-2 COG pixels from Planetary Computer. ...",
 'remedy': 'Connect Google Earth Engine to compute this index server-side...'}
```

---

## Scope and limits

Read this before relying on the output.

- **Reading numeric arrays without Earth Engine does not work in this release.**
  Planetary Computer returns HTTP 409 for anonymous reads of signed assets, so
  the COG reader returns `status="unavailable"`. Targeted for 0.4.0.
- **No zonal statistics.** Removed in 0.3.0 — the previous implementation
  sampled a 3×3 window at each polygon centroid and called it exact. Use
  [`exactextract`](https://github.com/isciences/exactextract), or Earth Engine's
  `reduceRegions`. Returning correctly is targeted for 0.4.0.
- **No raster export.** The GeoTIFF export was removed: it wrote random noise.
  It will not return until there is a real raster to export.
- **No time series.** Single composites only. Targeted for 0.5.0.
- **Tiles are imagery.** Colours are a display stretch. Do not sample them.
- **Degree tiles are not equal area.** 0.1° is ~11 km at the equator, ~7 km at
  50°N. Each tile reports its own `approx_km`.
- **Overture reads are slow.** The buildings theme is not partitioned
  geographically, so even a small bounding box scans Parquet metadata across the
  whole global dataset — a city-block query measured 322 seconds. It runs in an
  isolated subprocess (DuckDB's httpfs extension can terminate the interpreter
  on some platforms) with a 600 s timeout, then falls back to OpenStreetMap.
  Set `EARTHBRIDGE_OVERTURE_TIMEOUT` to change it.

## CLI

```bash
earthbridge studio                                        # launch the workbench
earthbridge search    --bbox 78.4,17.3,78.5,17.4          # what scenes are here
earthbridge index     --bbox 78.4,17.3,78.5,17.4 --type ndvi
earthbridge partition --bbox 78.0,17.0,79.0,18.0 --tile-size 0.1
earthbridge stac-item --bbox 78.4,17.3,78.5,17.4 --output item.json
```

## Examples

```bash
python examples/01_discover_scenes.py           # what imagery exists here
python examples/02_buildings_with_provenance.py # buildings and their licence
python examples/03_tiles_versus_measurements.py # imagery vs measured values
python examples/04_stac_item.py                 # write a STAC 1.0.0 Item
```

## Related tools

earth-bridge is a thin convenience layer. For serious work these are more
capable, and often the right answer:

- [`geemap`](https://github.com/gee-community/geemap) — Earth Engine in Jupyter
- [`odc-stac`](https://github.com/opendatacube/odc-stac) / [`stackstac`](https://github.com/gjoseph92/stackstac) — STAC to xarray, done properly
- [`spyndex`](https://github.com/awesome-spectral-indices/spyndex) — 200+ cited spectral indices
- [`exactextract`](https://github.com/isciences/exactextract) — exact zonal statistics
- [`overturemaps`](https://github.com/OvertureMaps/overturemaps-py) — official Overture CLI

## Roadmap

[ROADMAP.md](ROADMAP.md) tracks the whole plan as a checklist, including the
things deliberately ruled out.

- **0.3.0 — honesty** *(done)*. Removed everything that returned invented
  numbers, gave every result a provenance record, and made the documented API
  run.
- **0.4.0 — usefulness** *(next)*. Sign Planetary Computer assets so the COG
  reader works, and you get measured NDVI over any region on Earth with no
  credentials at all. Plus recorded-fixture tests, CI, and real zonal statistics
  via `exactextract`.
- **0.5.0 — scale.** Pluggable backends, xarray output, time series, and the
  tile partitioner wired to an executor.
- **1.0.0 — the actual claim.** The same measurement computed through
  independent backends and reported *with its disagreement* — where Earth
  Engine, Planetary Computer and openEO differ over one region, and why.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). 0.3.0 removed several features that produced
fabricated or unfounded numbers; the rationale for each is recorded there.

## License

MIT.
