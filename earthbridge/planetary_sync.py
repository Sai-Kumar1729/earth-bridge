"""
Cross-Cloud Query Synchronization Module
=========================================
Translates spatial queries between Google Earth Engine (GEE) and 
Microsoft Planetary Computer (MPC) STAC API.
"""

from typing import Dict, Any, List, Optional
import json


# Cross-Cloud Collection Mapping
COLLECTION_MAP = {
    "sentinel-2-l2a": {
        "mpc": "sentinel-2-l2a",
        "gee": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": {
            "red": "B04", "green": "B03", "blue": "B02",
            "nir": "B08", "swir": "B11", "swir2": "B12",
        },
        "gee_bands": {
            "red": "B4", "green": "B3", "blue": "B2",
            "nir": "B8", "swir": "B11", "swir2": "B12",
        }
    },
    "landsat-c2-l2": {
        "mpc": "landsat-c2-l2",
        "gee": "LANDSAT/LC08/C02/T1_L2",
        "bands": {
            "red": "SR_B4", "green": "SR_B3", "blue": "SR_B2",
            "nir": "SR_B5", "swir": "SR_B6", "swir2": "SR_B7",
        },
        "gee_bands": {
            "red": "SR_B4", "green": "SR_B3", "blue": "SR_B2",
            "nir": "SR_B5", "swir": "SR_B6", "swir2": "SR_B7",
        }
    },
    "modis-11A1-061": {
        "mpc": "modis-11A1-061",
        "gee": "MODIS/061/MOD11A1",
        "bands": {"lst_day": "LST_Day_1km", "lst_night": "LST_Night_1km"},
        "gee_bands": {"lst_day": "LST_Day_1km", "lst_night": "LST_Night_1km"},
    },
}


def query_planetary_and_gee(
    collection: str = "sentinel-2-l2a",
    bbox: List[float] = None,
    start_date: str = "2026-01-01",
    end_date: str = "2026-08-01",
    max_cloud_cover: float = 20.0,
    max_items: int = 5
) -> Dict[str, Any]:
    """
    Generate synchronized query code snippets for both GEE and Planetary Computer.
    
    Args:
        collection: Collection identifier (e.g., "sentinel-2-l2a")
        bbox: [min_lon, min_lat, max_lon, max_lat]
        start_date: Start date for temporal filter
        end_date: End date for temporal filter
        max_cloud_cover: Maximum cloud cover percentage
        max_items: Maximum number of items to return
    
    Returns:
        Dictionary with 'planetary_code' (Python) and 'gee_code' (JavaScript) snippets
    """
    if bbox is None:
        bbox = [78.35, 17.30, 78.55, 17.50]
    
    coll_info = COLLECTION_MAP.get(collection, COLLECTION_MAP["sentinel-2-l2a"])
    
    # Microsoft Planetary Computer Python snippet
    planetary_code = f'''# Microsoft Planetary Computer STAC Query
import pystac_client
import planetary_computer

bbox = {bbox}
start_date = "{start_date}"
end_date = "{end_date}"
collection = "{coll_info['mpc']}"

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace
)

search = catalog.search(
    collections=[collection],
    bbox=bbox,
    datetime=f"{{start_date}}/{{end_date}}",
    query={{"eo:cloud_cover": {{"lt": {max_cloud_cover}}}}},
    limit={max_items}
)

items = list(search.items())
for item in items:
    print(f"{{item.id}} | Cloud: {{item.properties.get('eo:cloud_cover')}}% | Date: {{item.datetime}}")
    # Access COG assets:
    # item.assets["B04"].href  # Red band
    # item.assets["B08"].href  # NIR band
'''

    # Google Earth Engine JavaScript snippet
    gee_bands = coll_info.get('gee_bands', coll_info.get('bands', {}))
    gee_code = f'''// Google Earth Engine JavaScript Query
var bbox = ee.Geometry.Rectangle({bbox});
var startDate = "{start_date}";
var endDate = "{end_date}";
var collection = "{coll_info['gee']}";

var dataset = ee.ImageCollection(collection)
  .filterBounds(bbox)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", {max_cloud_cover}))
  .sort("CLOUDY_PIXEL_PERCENTAGE")
  .limit({max_items});

// Example: Compute NDVI
var ndvi = dataset.map(function(image) {{
  return image.normalizedDifference(["{gee_bands.get('nir', 'B8')}", "{gee_bands.get('red', 'B4')}"])
    .rename("NDVI")
    .copyProperties(image, image.propertyNames());
}});

var medianNdvi = ndvi.median().clip(bbox);

// Visualize
Map.centerObject(bbox, 12);
Map.addLayer(medianNdvi, {{min: -0.1, max: 0.8, palette: ['blue', 'white', 'green']}}, 'NDVI');

// Export
Export.image.toDrive({{
  image: medianNdvi,
  description: 'ndvi_export',
  scale: 10,
  region: bbox,
  fileFormat: 'GeoTIFF'
}});
'''

    return {
        "planetary_code": planetary_code,
        "gee_code": gee_code,
        "collection_mapping": {
            "mpc_collection": coll_info["mpc"],
            "gee_collection": coll_info["gee"],
            "bands": coll_info["bands"]
        }
    }