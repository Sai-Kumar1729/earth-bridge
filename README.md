# earth-bridge

A Python interface for discovering and retrieving Earth observation data over a
region of interest across Microsoft Planetary Computer, NASA GIBS, Google Earth
Engine, and Overture Maps, with a local browser workbench.

[![PyPI](https://img.shields.io/pypi/v/earth-bridge?color=blue)](https://pypi.org/project/earth-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)

> **Alpha release.** This library performs data discovery: it reports which
> observations exist over a region and renders them for display. It does not
> currently derive measured values without Google Earth Engine. Review
> [Scope and limitations](#scope-and-limitations) before use, and
> [ROADMAP.md](ROADMAP.md) for planned work and excluded functionality.

---

## Installation

```bash
pip install earth-bridge                 # core: search, tiles, buildings, export
pip install 'earth-bridge[gee]'          # adds Earth Engine, for measured statistics
pip install 'earth-bridge[overture]'     # adds DuckDB, for Overture building reads
pip install 'earth-bridge[all]'          # all optional dependencies
```

## Workbench

```bash
earthbridge studio
```

The workbench accepts a drawn bounding box or an uploaded boundary, retrieves the
selected product, and displays it on a map. The server binds to loopback only.

---

## Result types

The library returns two distinct categories of result. Confusing them is the most
common source of misinterpretation.

| | Tile layer | Measured statistics |
|---|---|---|
| Content | Rendered PNG or JPEG imagery | Values reduced from pixel data |
| Credentials required | None | Google Earth Engine |
| Pixel values retrievable | No; colours are a display stretch | Yes |
| `result["kind"]` | `tile_layer` | `tile_layer_with_stats` |

```python
import earthbridge as eb

BBOX = [78.40, 17.35, 78.50, 17.45]

# Rendered imagery, no credentials required.
tiles = eb.get_tiles(BBOX, layer="ndvi")
print(tiles["tile_url"])                      # XYZ template for a map client
print(tiles["provenance"]["collection"])      # modis-13Q1-061

# Measured value, requires Earth Engine.
result = eb.compute_index(BBOX, index="ndvi")
if result["status"] == "success":
    print(result["stats"]["mean"])
else:
    print(result["reason"], "->", result["remedy"])
```

## Functionality available without credentials

```python
# Scene discovery: coverage, acquisition date, and cloud cover
scenes = eb.search_stac(BBOX, collection="sentinel-2-l2a", max_items=8)
for item in scenes["items"]:
    print(item["datetime"][:10], item["cloud_cover"], item["id"])

# Building footprints, with the source recorded
buildings = eb.fetch_buildings(BBOX, limit=500)
print(buildings["source"].unique())                    # ['overture'] or ['openstreetmap']
print(buildings.attrs["provenance"]["license"])

# Partition a large region into tiles
tiles = eb.partition([76.0, 12.0, 85.0, 20.0], tile_size=0.1)
print(len(tiles), tiles[0]["approx_km"])               # degree tiles are not equal area

# Export, and write a standalone HTML map
eb.export(buildings, format="geojson", output="buildings.geojson")
eb.report(buildings, city_name="Hyderabad", output="map.html")
```

## Functionality requiring Earth Engine

Run `earthengine authenticate` once, then supply a Cloud project identifier
through the `EE_PROJECT_ID` environment variable or the Studio header.

```python
eb.compute_index(BBOX, index="ndvi")     # also ndwi, lswi, nbr, ndbi
eb.get_modis_tcc(BBOX, year=2020)        # percent tree canopy cover (MOD44B)
```

Earth Engine performs cloud masking, compositing, and reduction server-side, so
local memory consumption remains constant regardless of region size.

---

## Provenance

Every result carries a record of its origin:

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

This is significant where the library falls back between providers. A building
query may be satisfied by Overture or by OpenStreetMap, and the two carry
different licences: OpenStreetMap is ODbL, which imposes share-alike obligations
on derived databases. The fallback is permitted, but it is always reported. Pass
`allow_osm_fallback=False` to require Overture.

Failures return a reason and a remedy rather than a substitute value:

```python
>>> eb.compute_index(BBOX, index="ndvi")
{'status': 'unavailable',
 'reason': "Could not read Sentinel-2 COG pixels from Planetary Computer. ...",
 'remedy': 'Connect Google Earth Engine to compute this index server-side...'}
```

---

## Scope and limitations

- **Numeric array reads without Earth Engine are not functional in this
  release.** Planetary Computer returns HTTP 409 for anonymous reads of signed
  assets, so the COG reader returns `status="unavailable"`. Scheduled for 0.4.0.
- **Zonal statistics are unavailable.** The previous implementation was removed
  in 0.3.0: it sampled a 3x3 window at each polygon centroid and described the
  result as exact. Use
  [`exactextract`](https://github.com/isciences/exactextract) or the Earth Engine
  `reduceRegions` method. A correct implementation is scheduled for 0.4.0.
- **Raster export is unavailable.** The GeoTIFF export was removed because it
  wrote randomly generated values. It will not be reinstated until the library
  produces a genuine raster.
- **Time series are unsupported.** Single composites only. Scheduled for 0.5.0.
- **Tiles are rendered imagery.** Colours are a display stretch and must not be
  sampled as data.
- **Degree-based tiles are not equal area.** A 0.1 degree tile is approximately
  11 km at the equator and approximately 7 km at 50 degrees north. Each tile
  reports its own `approx_km` value.
- **Overture reads are slow.** The buildings theme is not partitioned
  geographically, so even a small bounding box requires scanning Parquet metadata
  across the global dataset; a city-block query has been measured at 322 seconds.
  The query runs in an isolated subprocess, because the DuckDB `httpfs` extension
  can terminate the interpreter on some platforms, with a 600 second timeout
  followed by fallback to OpenStreetMap. The timeout is configurable through
  `EARTHBRIDGE_OVERTURE_TIMEOUT`.

## Command line interface

```bash
earthbridge studio                                        # launch the workbench
earthbridge search    --bbox 78.4,17.3,78.5,17.4          # list available scenes
earthbridge index     --bbox 78.4,17.3,78.5,17.4 --type ndvi
earthbridge partition --bbox 78.0,17.0,79.0,18.0 --tile-size 0.1
earthbridge stac-item --bbox 78.4,17.3,78.5,17.4 --output item.json
```

## Examples

```bash
python examples/01_discover_scenes.py           # scene discovery
python examples/02_buildings_with_provenance.py # buildings and licence terms
python examples/03_tiles_versus_measurements.py # imagery compared with measurements
python examples/04_stac_item.py                 # write a STAC 1.0.0 Item
```

## Related projects

earth-bridge is a convenience layer over established libraries. For specialised
work, the following are more capable and are frequently the appropriate choice:

- [`geemap`](https://github.com/gee-community/geemap) — Earth Engine in Jupyter
- [`odc-stac`](https://github.com/opendatacube/odc-stac) and [`stackstac`](https://github.com/gjoseph92/stackstac) — STAC to xarray
- [`spyndex`](https://github.com/awesome-spectral-indices/spyndex) — over 200 documented spectral indices
- [`exactextract`](https://github.com/isciences/exactextract) — exact zonal statistics
- [`overturemaps`](https://github.com/OvertureMaps/overturemaps-py) — official Overture command line tool

## Roadmap

[ROADMAP.md](ROADMAP.md) tracks planned work as a checklist, including
functionality that has been explicitly excluded.

- **0.3.0 — Correctness** (released). Removed all output that was fabricated or
  unfounded, attached a provenance record to every result, and aligned the
  documented API with its implementation.
- **0.4.0 — Measurement without credentials** (next). Signs Planetary Computer
  assets so that the COG reader returns measured NDVI over any region without
  credentials, and adds recorded-fixture tests, continuous integration, and
  zonal statistics through `exactextract`.
- **0.5.0 — Architecture and scale.** Pluggable backends, xarray output, time
  series support, and the tile partitioner connected to an executor.
- **1.0.0 — Cross-backend verification.** A single measurement computed through
  independent backends and reported together with the divergence between them,
  covering Earth Engine, Planetary Computer, and openEO.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Release 0.3.0 removed several features that
produced fabricated or unfounded values; the rationale for each removal is
recorded there.

## License

MIT.
