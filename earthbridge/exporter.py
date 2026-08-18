"""
Write GeoDataFrames to GeoJSON, GeoParquet, CSV, or a STAC ItemCollection.

Where a dataset carries provenance in `gdf.attrs["provenance"]`, the source and
licence travel with the export rather than being dropped at the file boundary.
"""

from typing import Dict, Any, List, Optional
import os
import json
import geopandas as gpd

class OpenDatasetExporter:
    """Writes GeoDataFrames to open, widely-readable formats."""

    @staticmethod
    def export_geojson(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """Exports GeoPandas DataFrame to standard GeoJSON format."""
        gdf.to_file(output_path, driver="GeoJSON")
        return os.path.abspath(output_path)

    @staticmethod
    def export_parquet(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """Exports a GeoDataFrame to GeoParquet.

        Raises if pyarrow is unavailable rather than silently writing GeoJSON to
        a different path, which left callers holding a file that was not the
        format or the location they asked for.
        """
        try:
            gdf.to_parquet(output_path)
        except ImportError as e:
            raise ImportError(
                "Writing GeoParquet requires pyarrow. Install it with "
                "'pip install pyarrow', or export as geojson instead."
            ) from e
        return os.path.abspath(output_path)

    @staticmethod
    def export_csv(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """Exports a GeoDataFrame to CSV with centroid coordinates.

        Centroids are computed in an equal-area projection and converted back to
        EPSG:4326. Taking a centroid directly in degrees treats latitude and
        longitude as a flat plane, which displaces the result away from the
        equator.
        """
        df = gdf.copy()

        if len(df) and df.geometry.notna().any():
            source_crs = df.crs or "EPSG:4326"
            # World Equal Area Cylindrical; adequate for centroid placement at
            # any latitude and defined globally.
            centroids = df.geometry.to_crs("EPSG:6933").centroid.to_crs(source_crs)
            df["centroid_lon"] = centroids.x
            df["centroid_lat"] = centroids.y

        provenance = gdf.attrs.get("provenance")
        if provenance:
            df["_source"] = provenance.get("backend")
            df["_license"] = provenance.get("license")

        df = df.drop(columns=[gdf.geometry.name])
        df.to_csv(output_path, index=False)
        return os.path.abspath(output_path)

    @staticmethod
    def export_stac_collection(stac_items: List[Dict[str, Any]], output_path: str) -> str:
        """Exports a list of STAC Item dictionaries into a unified STAC ItemCollection JSON."""
        collection = {
            "type": "FeatureCollection",
            "stac_version": "1.0.0",
            "stac_extensions": [],
            "features": stac_items
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2)
        return os.path.abspath(output_path)

def export_open_dataset(
    gdf: gpd.GeoDataFrame,
    output_format: str = "geojson",
    output_path: str = "output.geojson"
) -> str:
    """Exports to a single requested format/path, matching the eb.export() keyword API."""
    exporter = OpenDatasetExporter()
    fmt = output_format.lower()
    if fmt == "geojson":
        return exporter.export_geojson(gdf, output_path)
    elif fmt == "parquet":
        return exporter.export_parquet(gdf, output_path)
    elif fmt == "csv":
        return exporter.export_csv(gdf, output_path)
    else:
        raise ValueError(f"Unsupported export format: {output_format}. Choose 'geojson', 'parquet', or 'csv'.")

def export_all_formats(gdf: gpd.GeoDataFrame, base_filename: str = "earthbridge_dataset") -> Dict[str, str]:
    """Exports dataset to all 3 standard formats (GeoJSON, Parquet, CSV)."""
    exporter = OpenDatasetExporter()
    return {
        "geojson": exporter.export_geojson(gdf, f"{base_filename}.geojson"),
        "parquet": exporter.export_parquet(gdf, f"{base_filename}.parquet"),
        "csv": exporter.export_csv(gdf, f"{base_filename}.csv")
    }
