# Roadmap

## Objective

A geospatial library whose outputs are accurate, attributable, and reproducible:
suitable as a dependency in research and production workflows, and credible
enough to be referenced by the Earth Engine, Planetary Computer, and OSGeo
communities.

Items are ordered by impact and feasibility. An item is marked complete only
when it has been executed and verified, not when the code has been written.

Status: `[x]` complete and verified, `[~]` in progress, `[ ]` not started.

---

## 0.3.0 — Correctness (released, commit `654116b`)

Prerequisite for all subsequent work. A library that returns fabricated values
cannot be depended upon, regardless of the quality of the remaining surface.

### 1. Removal of fabricated output

- [x] Remove `/api/export_tif`, which returned `np.random.uniform(-0.2, 0.8, (256, 256))` as the computed index raster with a valid CRS and affine transform attached
- [x] Withdraw `compute_building_zonal_stats`, which sampled a 3x3 window at each polygon centroid and returned `np.random.normal()` when no bounding box was supplied
- [x] Remove the vulnerability index, risk bands, and policy recommendations derived from the above
- [x] Remove `_generate_realistic_building_polygons`
- [x] Document the rationale for each removal in `CHANGELOG.md`

### 2. Provenance as a first-class return value

- [x] Add `earthbridge/provenance.py` with `Provenance`, `success()`, and `unavailable()`
- [x] Maintain a per-provider licence table, including OpenStreetMap ODbL share-alike obligations and Overture mixed terms
- [x] Attach provenance to every dictionary result and to `gdf.attrs["provenance"]`
- [x] Return a reason and a remedy on failure rather than a substitute value
- [x] Propagate provenance through export (`_source`, `_license`) and into the HTML report

### 3. Alignment of documented behaviour with implementation

- [x] `get_modis_tcc()` returns MOD44B percent tree canopy cover; it previously returned NDVI tiles and lacked the documented statistics key
- [x] `eb.report()` no longer raises `TypeError` on every call
- [x] `eb.compute_index()` reports the underlying HTTP 409 rather than an unexplained `no_data` status
- [x] Apply the Sentinel-2 processing baseline 04.00 `BOA_ADD_OFFSET` by acquisition date
- [x] Apply SCL cloud masking (classes 3, 8, 9, 10) before compositing
- [x] Preserve Earth Engine nulls as `None`; an empty region is not a measurement of zero
- [x] Reproject the request bounding box into the scene CRS before windowed COG reads
- [x] Read `start_datetime` and `end_datetime` for composite products where `datetime` is null
- [x] Compute CSV centroids in an equal-area projection (EPSG:6933)
- [x] Confirm that all four examples and all nine documented API claims execute successfully

### 4. Packaging and distribution

- [x] Add `web_studio/__init__.py`; without it the wheel contained no Studio package
- [x] Require `setuptools>=77` for the PEP 639 SPDX licence expression
- [x] Move `duckdb` from core dependencies into the `overture` extra; add `parquet` and `all` extras
- [x] Include Studio static assets in `package-data`
- [x] Bind the Studio to loopback; add a zip-slip guard, an upload size limit, and a state lock
- [x] Isolate the Overture query in a subprocess; the DuckDB `httpfs` installation can terminate the interpreter
- [x] Discover the current Overture release at runtime; the previously pinned release has been withdrawn from S3
- [x] Verify the built wheel from a clean virtual environment rather than the development tree

---

## 0.4.0 — Measurement without credentials

Delivers the capability that distinguishes the library: numeric results over an
arbitrary region of interest without a Google or Azure account.

### 5. Zero-credential COG pipeline

- [ ] Sign Planetary Computer assets with `planetary_computer.sign_inplace`, resolving the HTTP 409 response
- [ ] Perform windowed COG reads over HTTP range requests, verified against a known scene
- [ ] Apply nodata masking and per-collection scale and dtype handling
- [ ] Return measured statistics from `compute_index()` with `backend="planetary-computer"`
- [ ] Compare Planetary Computer and Earth Engine results for the same region and date, and document any divergence
- [ ] Remove the corresponding limitation from `README.md`

### 6. Regression testing

- [ ] Record HTTP fixtures for STAC search, COG reads, Overture, and Overpass
- [ ] Add unit tests for the BOA offset, SCL masking, CRS transformation, tile boundaries, and quantile classification
- [ ] Add a property test asserting that `split_bbox` tiles cover the input without gaps or overlap
- [ ] Configure a GitHub Actions matrix across Python 3.9-3.13 on Linux, macOS, and Windows
- [ ] Report test coverage in `README.md`
- [ ] Reclassify `tests/verify_release.py` as an optional live smoke check

### 7. Zonal statistics

- [ ] Integrate `exactextract` for area-weighted statistics behind a `zonal` extra
- [ ] Provide an Earth Engine `reduceRegions` path under the same call signature
- [ ] Add an agreement test between the two implementations
- [ ] Restore the capability withdrawn in 0.3.0 with a correct implementation

---

## 0.5.0 — Architecture and scale

### 8. Backend abstraction

- [ ] Introduce `Recipe` and `Result` types with a pluggable `Backend` interface
- [ ] Select backends automatically and record the selection rationale in provenance
- [ ] Carry data, provenance, and the executed code path in `Result`
- [ ] Support registration of third-party backends without modification of core modules

### 9. Arrays and time series

- [ ] Return xarray objects with CRS and time coordinates
- [ ] Support requests across a date range rather than a single composite
- [ ] Connect `partition()` to an executor so that large regions complete within practical limits
- [ ] Process in chunks so that memory use is independent of region size

### 10. Interoperability

- [ ] Emit a STAC ItemCollection as a native output of every search
- [ ] Add openEO as a third backend
- [ ] Provide GDAL- and QGIS-readable outputs (COG, GeoParquet) end to end

---

## 1.0.0 — Cross-backend verification

The intended contribution is not an additional STAC client, but a single
measurement computed through independent backends and reported together with the
divergence between them.

- [ ] Publish a cross-backend agreement benchmark covering Earth Engine, Planetary Computer, and openEO for identical regions and dates
- [ ] Document the sources of divergence: masking, compositing, resampling, and baseline offsets
- [ ] Provide a reproducible benchmark notebook
- [ ] Freeze the public API and adopt semantic versioning guarantees
- [ ] Publish a documentation site with a verified quickstart
- [ ] Submit to the Journal of Open Source Software
- [ ] Present the benchmark to the gee-community, Planetary Computer, and OSGeo communities

---

## Out of scope

Recorded to prevent reintroduction:

- Raster export, until there is a genuine raster to export
- Risk, vulnerability, and policy scoring based on unvalidated thresholds
- Duplication of the primary functionality of `geemap`, `odc-stac`, `stackstac`, or `spyndex`
- Publication to PyPI before 0.4.0; 0.3.0 is a corrected baseline rather than a distributable release

---

## Completion criteria

1. Verification is performed against the built wheel in a clean virtual environment.
2. A numeric result is considered verified only when it has been checked against an independent source.
3. A removal is complete only when its rationale has been documented.
