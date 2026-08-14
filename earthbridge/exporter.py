"""
Open Dataset Exporter Module
============================
Exports enriched spatial datasets to GeoJSON, Parquet (HuggingFace compatible), CSV, and STAC Item Collections.
"""

from typing import Dict, Any, List, Optional
import os
import json
import geopandas as gpd

class OpenDatasetExporter:
    """Exports processed spatial datasets into community-standard open dataset formats."""

    @staticmethod
    def export_geojson(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """Exports GeoPandas DataFrame to standard GeoJSON format."""
        gdf.to_file(output_path, driver="GeoJSON")
        return os.path.abspath(output_path)

    @staticmethod
    def export_parquet(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """Exports GeoPandas DataFrame to Cloud-Native GeoParquet (HuggingFace compatible)."""
        try:
            gdf.to_parquet(output_path)
        except Exception:
            # Fallback if pyarrow is not present
            gdf.to_file(output_path.replace(".parquet", ".geojson"), driver="GeoJSON")
            return os.path.abspath(output_path.replace(".parquet", ".geojson"))
        return os.path.abspath(output_path)

    @staticmethod
    def export_csv(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """Exports GeoPandas DataFrame to CSV with centroid coordinates."""
        # Create a copy to avoid mutating the original
        df = gdf.copy()
        
        # Add centroid coordinates if geometry column exists
        if df.geometry.notnull().any():
            centroids = df.geometry.centroid
            df['centroid_lon'] = centroids.x
            df['centroid_lat'] = centroids.y
            
        # Drop the complex geometry column for CSV export
        df = df.drop(columns=['geometry'])
        
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
