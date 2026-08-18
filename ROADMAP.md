# earth-bridge roadmap

The end goal: a geospatial library whose numbers can be trusted and cited —
useful enough that people reach for it over writing the glue themselves, and
credible enough to be referenced by the Earth Engine, Planetary Computer, and
OSGeo communities.

Ordered by impact x feasibility. Check items only when verified by running them,
not when the code is written.

Status legend: `[x]` done and verified - `[ ]` not started - `[~]` in progress

---

## 0.3.0 — Honesty release (shipped, commit `654116b`)

The prerequisite for everything below. A library that returns invented numbers
cannot be built on, promoted, or cited, however good the rest of it is.

### 1. Remove fabricated data
- [x] Delete `/api/export_tif` — served `np.random.uniform(-0.2, 0.8, (256,256))` as the computed raster, georeferenced
- [x] Withdraw `compute_building_zonal_stats` — 3x3 centroid sample called "exact"; `np.random.normal()` fallback with no bbox
- [x] Remove vulnerability index, risk bands, policy recommendations (all derived from the above)
- [x] Delete `_generate_realistic_building_polygons`
- [x] Record the reason for every removal in `CHANGELOG.md`, not a silent delete

### 2. Provenance as a first-class return value
- [x] `earthbridge/provenance.py` — `Provenance`, `success()`, `unavailable()`
- [x] Licence table per provider, incl. OSM ODbL share-alike vs Overture's mixed terms
- [x] Provenance on every dict result and on `gdf.attrs["provenance"]`
- [x] Failures return `reason` + `remedy`, never a substitute value
- [x] Provenance survives export (`_source` / `_license` columns) and appears in the HTML report

### 3. Make the documented API actually run
- [x] `get_modis_tcc()` returns real MOD44B canopy cover (was NDVI tiles; documented key raised `KeyError`)
- [x] `eb.report()` no longer `TypeError`s on every call
- [x] `eb.compute_index()` reports the real HTTP 409 instead of silent `no_data`
- [x] Sentinel-2 baseline 04.00 `BOA_ADD_OFFSET` applied by acquisition date
- [x] SCL cloud masking before compositing (classes 3, 8, 9, 10)
- [x] EE nulls stay `None` — an empty region is not a measurement of zero
- [x] COG reads reproject the bbox into the scene CRS (S2 COGs are UTM, not 4326)
- [x] Composite products (MOD13Q1) read `start_datetime`/`end_datetime` when `datetime` is null
- [x] Equal-area centroids (EPSG:6933) in CSV export
- [x] All 4 examples run clean; 9/9 documented claims verified

### 4. Packaging that installs and works
- [x] `web_studio/__init__.py` — without it `find_packages` shipped no Studio at all
- [x] `setuptools>=77` for PEP 639 SPDX licence
- [x] `duckdb` out of core into `[overture]`; add `[parquet]`, `[all]`
- [x] Studio static assets in `package-data`
- [x] Studio binds loopback only; zip-slip guard; upload cap; threading lock
- [x] Overture query isolated in a subprocess (DuckDB `INSTALL httpfs` fatally crashes the interpreter)
- [x] Overture release discovered at runtime (the pinned one had been deleted from S3)
- [x] Verified from a clean venv against the built wheel, not the dev tree

---

## 0.4.0 — The release that makes the project worth using

Everything above made it honest. This makes it useful. One capability defines it:
**real numbers over any ROI on Earth with no Google account, no Azure account, no
credentials at all.** Nothing else in the ecosystem hands you that in one call.

### 5. Repair the zero-credential COG pipeline
- [ ] Sign Planetary Computer assets (`planetary_computer.sign_inplace`) — the 409 cause
- [ ] Windowed COG reads over HTTP range requests, verified against a known scene
- [ ] Nodata masking and dtype/scale handling per collection
- [ ] `compute_index()` returns measured stats with `backend="planetary-computer"`
- [ ] Cross-check: same bbox, same date, PC vs GEE — agree within tolerance, or explain why not
- [ ] Delete the "does not work in this release" caveat from README

### 6. Tests that catch regressions without the network
- [ ] Recorded HTTP fixtures (VCR-style) for STAC search, COG read, Overture, Overpass
- [ ] Unit tests for the maths: BOA offset by date, SCL masking, CRS transform, tile edges, quantile breaks
- [ ] Property test: `split_bbox` tiles cover the input exactly, no gaps or overlap
- [ ] GitHub Actions matrix — Python 3.9-3.13, Linux/macOS/Windows
- [ ] Coverage reported honestly in the README, whatever the number is
- [ ] `tests/verify_release.py` demoted to an optional live smoke check

### 7. Real zonal statistics
- [ ] `exactextract` integration, area-weighted, behind `[zonal]`
- [ ] Earth Engine `reduceRegions` path for the same call signature
- [ ] Agreement test between the two backends on a fixture
- [ ] Restores the capability 0.3.0 withdrew — this time correct

---

## 0.5.0 — Architecture that scales past one call

### 8. `Recipe` / `Result` / pluggable `Backend`
- [ ] One request object; backends declare what they can serve
- [ ] Automatic backend selection with the reason recorded in provenance
- [ ] `Result` carries data + provenance + the exact code path taken
- [ ] Third-party backends registerable without touching core

### 9. Arrays and time, not just single numbers
- [ ] xarray output with CRS and time coordinates
- [ ] Time series over a date range, not single composites
- [ ] Wire `partition()` to a real executor so a country-sized ROI actually completes
- [ ] Streaming / chunked so memory stays flat

### 10. Interoperability
- [ ] STAC ItemCollection as a native output of every search
- [ ] openEO as a third backend
- [ ] Optional GDAL/QGIS-readable outputs (COG, GeoParquet) end to end

---

## 1.0.0 — The claim that earns recognition

The differentiator is not "another STAC wrapper". It is **the same measurement
computed through independent backends, reported with its disagreement.** Nobody
publishes that. It is the thing a reviewer, a journal, or a Google/Microsoft team
would find genuinely novel.

- [ ] Cross-backend agreement benchmark: GEE vs Planetary Computer vs openEO, same ROI, same date, published numbers
- [ ] Document where they disagree and why (masking, compositing, resampling, baseline offsets)
- [ ] Reproducible benchmark notebook anyone can re-run
- [ ] API frozen and semver-honoured
- [ ] Docs site with a real quickstart
- [ ] JOSS paper submission
- [ ] Approach the gee-community / Planetary Computer / OSGeo channels — with the benchmark, not with a feature list

---

## Not doing

Recorded so they don't get re-proposed:

- Raster export — not until there is a real raster to export
- Risk / vulnerability / policy scoring — unfounded thresholds dressed as analysis
- Competing with `geemap`, `odc-stac`, `stackstac`, `spyndex` on their own ground
- Publishing to PyPI before 0.4.0 — 0.3.0's value is as a trustworthy base, not a release

---

## Rules for checking a box

1. Run it from a clean venv against the built wheel, not the dev tree.
2. If the number can't be checked against an independent source, it isn't verified.
3. A removal is finished only when the reason is written down.
