# Changelog

## Unreleased

Planned work is tracked as a checklist in [ROADMAP.md](ROADMAP.md), including
the capabilities that have been ruled out and why. The next release, 0.4.0,
signs Planetary Computer assets so the COG reader works — measured values over
any region with no credentials — and adds recorded-fixture tests and CI.

## 0.3.0 — Correctness release

This release removes capabilities. Several features returned numbers that were
fabricated, unfounded, or attributed to the wrong source, and a few documented
entry points raised exceptions when called. Everything in that category has been
removed or corrected rather than patched over, so the remaining surface is
smaller and can be trusted.

Anyone who used the removed features should read the reasons below. Results
derived from them should be treated as invalid.

### Removed: fabricated data

- **Raster GeoTIFF export.** `/api/export_tif` generated
  `np.random.uniform(-0.2, 0.8, (256, 256))` and served it as the computed index
  raster, with a real CRS and affine transform attached. Downloads from this
  endpoint were georeferenced noise, not measurements. The endpoint and its UI
  button are gone; there is no raster export in this release.

- **Zonal statistics.** `compute_building_zonal_stats` described itself as
  computing "exact zonal summary statistics". It sampled a 3×3 pixel window at
  each polygon's centroid, using a linear bbox interpolation that assumed the
  array covered exactly the bounding box in EPSG:4326 — no affine transform, no
  polygon rasterisation, no area weighting, no CRS handling, no nodata masking.
  With no bbox supplied it returned `np.random.normal(mean, 0.12)`. Calling it
  now raises `NotImplementedError` pointing at `exactextract`.

- **Per-building vulnerability index and risk bands.** Derived entirely from the
  above, then labelled "High Risk" / "Optimal" against fixed 0.3 and 0.6
  cut-offs applied to any column whose name contained `_mean` — the same
  thresholds for NDVI, for degrees Celsius, and for a unitless index. Removed
  from the API, the report and the map styling.

- **Synthetic building generator.** `_generate_realistic_building_polygons`
  produced random L-shaped and rectangular polygons with random heights.
  Removed.

- **Policy recommendations.** The report emitted intervention advice for city
  planners on top of the numbers above. Removed; the report is now a descriptive
  map with quantile shading of the dataset's own values.

### Fixed: claims that did not match behaviour

- **`get_modis_tcc()` did not return tree canopy cover.** It returned MOD13Q1
  NDVI tiles, or a NASA GIBS corrected-reflectance layer frozen at 2024-05-01.
  Neither is canopy cover, and the documented
  `stats["Percent_Tree_Cover_mean"]` key did not exist, so the README's first
  example raised `KeyError`. It now uses MOD44B, which is the actual canopy
  product, and requires Earth Engine — Planetary Computer does not carry MOD44B,
  so there is no zero-credential route to this measurement. The zero-credential
  MODIS vegetation layer is now named `get_modis_ndvi()`.

- **`eb.report()` raised `TypeError` on every call.** It passed `gdf=` and
  `output_path=` to a function whose parameters were `enriched_gdf` and
  `output_filepath`. Both spellings are now accepted.

- **`eb.compute_index()` silently returned `no_data`.** The COG reader is
  genuinely broken — Planetary Computer returns HTTP 409 for anonymous reads of
  signed assets — but this was reported as an empty result rather than a
  failure. It now returns `status="unavailable"` with a reason and a remedy, and
  routes through Earth Engine when available.

- **Overture queries silently returned OpenStreetMap data.** Different schema,
  different licence, no indication to the caller. Results now carry a `source`
  column and licence terms in `gdf.attrs["provenance"]`; pass
  `allow_osm_fallback=False` to refuse the substitution.

- **OpenStreetMap heights were invented.** Buildings with no height tag were
  assigned 12 m. They are now null.

- **Three of four examples crashed on import**, referencing modules
  (`overture_join`, `planetary_sync`) deleted in an earlier release. All
  examples have been rewritten and all four run.

- **`GEEToSTACConverter` never touched Earth Engine.** It built a dictionary from
  arguments you supplied. Renamed to `STACItemBuilder`.

### Fixed: remote sensing correctness

- **Sentinel-2 composites had no per-pixel cloud masking.** Only a scene-level
  `CLOUDY_PIXEL_PERCENTAGE` filter was applied, while the docstring claimed
  cloud masking. A Scene Classification Layer mask now removes cloud shadow,
  medium and high probability cloud, and cirrus before compositing.

- **Missing baseline 04.00 reflectance offset.** Sentinel-2 digital numbers were
  divided by 10000 with no `BOA_ADD_OFFSET`, biasing every scene acquired after
  January 2022. The offset is now applied by acquisition date, and zeros are
  masked as nodata rather than treated as zero reflectance.

- **COG windows were read in the wrong coordinate system.** An EPSG:4326 bbox
  was passed against a UTM raster transform, addressing entirely wrong pixels.
  Bounds are now reprojected into the raster's CRS first.

- **LST climatology baseline included the observed year**, letting the
  observation contribute to the mean it was compared against and damping the
  anomaly. The baseline now excludes it, and an overlapping request is rejected.

- **Empty regions reported as zero.** `float(stats.get(x) or 0.0)` turned Earth
  Engine's null — meaning no unmasked pixels — into a measurement of 0.0. Empty
  reductions now return `status="unavailable"`.

- **Dead emptiness check.** `if not tcc_img:` on an `ee.Image` is always false,
  since server-side objects are truthy. Emptiness is now tested with
  `collection.size().getInfo()`.

- **Non-deterministic scene selection.** STAC searches had no date filter, no
  cloud filter, and took `features[0]`. Results are now sorted by cloud cover so
  repeated calls return the same scene.

- **NASA GIBS dates were hardcoded to 2024-05-01** in five places. The date is
  now computed, adjustable, and recorded in the provenance.

- **Tile grid drift and silent antimeridian failure.** Edges accumulated
  floating point error (`78.19999999999999`), and a bbox crossing the
  antimeridian silently produced zero tiles. Edges are now computed by
  multiplication, invalid bboxes raise, and each tile reports its ground size.

- **Geographic centroids.** CSV export computed centroids in degrees, treating
  lat/lon as a plane. They are now computed in an equal-area projection.

### Fixed: security

- **Arbitrary file write via uploaded zip.** `zipfile.extractall` follows `../`
  and absolute paths in member names, letting an uploaded archive write anywhere
  the process could reach. Entries are now validated against the extraction root.

- **Server listened on all interfaces** with `Access-Control-Allow-Origin: *`,
  no authentication, live Earth Engine credentials and a file upload endpoint.
  It now binds loopback only.

- **Unbounded upload reads.** The whole request body was read into memory with no
  size check. Capped at 100 MB.

- **Shared mutable state across threads.** `LATEST_GDF` was mutated by a threaded
  server, so concurrent requests could interleave and an export could return
  another request's data. Now guarded by a lock.

### Fixed: packaging

- **`earthbridge studio` could not work for anyone installing from PyPI.**
  `web_studio` had no `__init__.py`, so setuptools never discovered it and the
  wheel shipped no server, HTML or JavaScript. Added, with package data for the
  runtime assets.

- **The project could not be built at all** with setuptools below 77:
  `license = "MIT"` as a bare SPDX string was rejected. The build requirement is
  now declared.

- **`duckdb` was a required dependency** but is only needed for Overture reads.
  Moved to the `overture` extra, alongside new `parquet` and `all` extras.

- **DuckDB could terminate the caller's process.** On some platforms
  `INSTALL httpfs` crashes the interpreter outright, which no `try`/`except` can
  catch. The Overture query now runs in a subprocess, so the worst case is a
  fallback rather than a dead process.

- **The Overture release was pinned in source** to `2025-04-02.0`, which no
  longer exists — only the two most recent releases are retained on S3. The
  current release is now discovered at runtime, with `EARTHBRIDGE_OVERTURE_RELEASE`
  to pin one deliberately.

- **`dist/` was committed** despite being in `.gitignore`, shipping stale 0.1.0
  artefacts that referenced deleted modules. Untracked.

- **Silent format substitution.** GeoParquet export fell back to writing GeoJSON
  at a different path when pyarrow was missing. It now raises.

### Renamed

Old names remain as aliases for one release.

| Was | Now |
|---|---|
| `ProductionSTACEngine` | `STACBackend` |
| `ProductionOvertureEngine` | `OvertureBackend` |
| `GEEOperationEngine` | `EarthEngineBackend` |
| `GEEToSTACConverter` | `STACItemBuilder` |
| `generate_policy_report` | `write_map_report` |
| `partition_state_bbox` | `split_bbox` |
| `get_modis_tcc` (zero-auth NDVI) | `get_modis_ndvi` |

### Also

- Removed `GEE_COMMUNITY_SUBMISSION.md`, a checklist for obtaining recognition
  from large technology companies. It did not belong in the repository.
- Every result now carries a `provenance` record: backend, collection, scene,
  date, native resolution, attribution and licence.

---

## 0.2.0 and earlier

See git history. Note that the 0.1.0 wheel published to PyPI references modules
(`overture_join`, `planetary_sync`) that no longer exist and omits the Studio
entirely.
