"""
Zonal statistics — withdrawn in 0.3.0.

The previous implementation described itself as computing "exact zonal summary
statistics" for polygons over a raster. It did not. It took each polygon's
centroid, mapped it into the array with a linear bounding-box interpolation that
assumed the array covered exactly the bbox in EPSG:4326, and averaged a 3x3
window of pixels around that point. There was no affine transform, no
rasterisation of the polygon, no area weighting, no CRS handling and no nodata
masking. When no bbox was supplied at all it drew values from
`np.random.normal(mean, 0.12)`.

For a building footprint against a 250 m MODIS pixel those numbers were not an
approximation of the zonal mean; they were unrelated to it. Anything derived
from them — the per-building vulnerability index, the report risk bands — was
equally unfounded.

Rather than ship a corrected version in a hurry, this release removes the
capability and points at the established implementations. A real version, built
on exactextract, is planned once the raster pipeline returns trustworthy arrays.

Use instead:

    # Area-weighted exact zonal statistics (recommended)
    pip install exactextract
    from exactextract import exact_extract
    stats = exact_extract(raster_path, buildings_gdf, ["mean", "stdev", "count"])

    # Or, for Earth Engine rasters, reduce server-side over a FeatureCollection
    image.reduceRegions(collection=features, reducer=ee.Reducer.mean(), scale=20)
"""

REMOVAL_MESSAGE = (
    "compute_building_zonal_stats was removed in earth-bridge 0.3.0 because it "
    "did not compute zonal statistics: it sampled a 3x3 window at each polygon "
    "centroid, and fell back to random values when no bbox was given. Use "
    "exactextract.exact_extract for area-weighted zonal statistics, or "
    "ee.Image.reduceRegions for Earth Engine rasters. See the module docstring "
    "and CHANGELOG.md for details."
)


class ZonalStatisticsEngine:
    """Removed. See the module docstring."""

    @staticmethod
    def compute_building_zonal_stats(*args, **kwargs):
        raise NotImplementedError(REMOVAL_MESSAGE)


def compute_building_zonal_stats(*args, **kwargs):
    raise NotImplementedError(REMOVAL_MESSAGE)
