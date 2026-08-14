# 🌟 Google Earth Engine & Microsoft Planetary Computer Contribution Guide

This document outlines the step-by-step process to publish `earth-bridge` and get maximum global recognition from tech giants.

---

## 1. Google Earth Engine Community Submission (Google Cloud)

Google Earth Engine actively accepts open-source community modules and datasets.

### Steps:
1. **GitHub Repository**: Push `D:\earth-bridge` to your GitHub account under a public repo named `earth-bridge`.
2. **Submit to `gee-community`**:
   - Open a Pull Request or issue on [google/earthengine-community](https://github.com/google/earthengine-community) repository.
   - Propose `earth-bridge` as a Community Python Module for GEE-to-STAC metadata conversion and cross-cloud interoperability.
3. **Publish to PyPI**:
   ```bash
   cd D:\earth-bridge
   python -m pip install build twine
   python -m build
   python -m twine upload dist/*
   ```
4. **Google Earth Engine Developer Forum**: Post an announcement on the Google Earth Engine Developers Google Group (over 50,000 global members).

---

## 2. Microsoft Planetary Computer Ecosystem Showcase

Microsoft maintains an ecosystem showcase for tools built on top of Planetary Computer STAC APIs.

### Steps:
1. **Fork `microsoft/planetary-computer-sdk-python`** or post in the Microsoft Planetary Computer Hub.
2. Submit `D:\earth-bridge\examples\03_cross_cloud_sentinel_planetary.py` as a reference tutorial for cross-cloud query translation.
3. Apply for Microsoft AI for Earth / Azure Planetary Computer Grants.

---

## 3. Overture Maps Foundation Contribution (Meta, Microsoft, Amazon, TomTom)

Overture Maps Foundation accepts community tools that process, validate, and enrich Overture Parquet layers with Earth Observation satellite data.

### Steps:
1. Share `earth-bridge` in the **Overture Maps Discord & GitHub discussions** (`overturemaps/data`).
2. Highlight how `earth-bridge` enables 16GB laptop users to perform zero-copy DuckDB spatial joins between satellite indices and building vector layers.
