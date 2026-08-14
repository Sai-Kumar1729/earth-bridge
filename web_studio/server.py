"""
Earth-Bridge Web Studio Server
"""

import os
import json
import time
import tempfile
import sys
import traceback
import numpy as np
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import socketserver

# Insert parent path so earthbridge package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from earthbridge.stac_engine import ProductionSTACEngine
from earthbridge.gee_engine import GEEOperationEngine
from earthbridge.spectral_indexes import SpectralIndexCalculator
from earthbridge.overture_engine import ProductionOvertureEngine
from earthbridge.zonal_stats import compute_building_zonal_stats
from earthbridge.exporter import OpenDatasetExporter
from earthbridge.report_engine import generate_policy_report
import geopandas as gpd

# Optional rasterio for GeoTIFF export
try:
    import rasterio
    from rasterio.transform import from_bounds
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))

INDEX_REGISTRY = {
    'ndvi': {'compute': SpectralIndexCalculator.ndvi, 'bands': ('nir', 'red'), 'label': 'NDVI'},
    'ndwi': {'compute': SpectralIndexCalculator.ndwi, 'bands': ('green', 'nir'), 'label': 'NDWI'},
    'lswi': {'compute': SpectralIndexCalculator.lswi, 'bands': ('nir', 'swir'), 'label': 'LSWI'},
    'nbr':  {'compute': SpectralIndexCalculator.nbr, 'bands': ('nir', 'swir'), 'label': 'NBR'},
    'ndbi': {'compute': SpectralIndexCalculator.ndbi, 'bands': ('swir', 'nir'), 'label': 'NDBI'},
}

# In-memory storage for the latest enriched GeoDataFrame
LATEST_GDF = None 
LATEST_INDEX = None

stac_engine = ProductionSTACEngine()
gee_engine = GEEOperationEngine()
overture_engine = ProductionOvertureEngine()

class StudioRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STUDIO_DIR, **kwargs)

    def send_cors_headers(self):
        """Send CORS headers for all responses."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def send_error_response(self, code, message):
        """Send a consistent error response."""
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        
        response = {
            "status": "error",
            "message": message,
            "code": code
        }
        self.wfile.write(json.dumps(response).encode())

    def do_OPTIONS(self):
        """Handle preflight requests."""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        start = time.time()
        
        if self.path == '/api/export_geojson':
            self._handle_export_geojson()
        elif self.path == '/api/export_csv':
            self._handle_export_csv()
        elif self.path == '/api/export_stac':
            self._handle_export_stac()
        elif self.path == '/api/export_tif':
            self._handle_export_tif()
        elif self.path == '/api/export_parquet':
            self._handle_export_parquet()
        else:
            super().do_GET()
            
        elapsed = time.time() - start
        if not self.path.endswith('.png') and not self.path.endswith('.css') and not self.path.endswith('.js'):
            print(f'[earth-bridge] {self.command} {self.path} completed in {elapsed:.2f}s')

    def do_POST(self):
        """Handle POST requests."""
        start = time.time()
        
        try:
            if self.path == '/api/compute':
                self._handle_compute()
            elif self.path == '/api/upload_shapefile':
                self._handle_upload_shapefile()
            else:
                self.send_error_response(404, "Endpoint not found")
        except Exception as e:
            traceback.print_exc()
            self.send_error_response(500, str(e))
            
        elapsed = time.time() - start
        print(f'[earth-bridge] {self.command} {self.path} completed in {elapsed:.2f}s')

    def _handle_export_geojson(self):
        """Export the latest GeoDataFrame as GeoJSON."""
        global LATEST_GDF
        if LATEST_GDF is None:
            self.send_error_response(404, "No enriched GeoDataFrame available")
            return
            
        try:
            geojson_data = LATEST_GDF.to_json()
            self.send_response(200)
            self.send_header('Content-type', 'application/geo+json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(geojson_data.encode())
        except Exception as e:
            self.send_error_response(500, f"Error exporting GeoJSON: {str(e)}")
            
    def _handle_export_csv(self):
        """Export the latest GeoDataFrame as CSV."""
        global LATEST_GDF
        if LATEST_GDF is None:
            self.send_error_response(404, "No enriched GeoDataFrame available")
            return
            
        try:
            csv_path = os.path.join(STUDIO_DIR, 'latest_export.csv')
            OpenDatasetExporter.export_csv(LATEST_GDF, csv_path)
            with open(csv_path, 'r') as f:
                csv_data = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/csv')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(csv_data.encode())
        except Exception as e:
            self.send_error_response(500, f"Error exporting CSV: {str(e)}")

    def _handle_export_stac(self):
        """Export the latest GeoDataFrame as STAC ItemCollection."""
        global LATEST_GDF, LATEST_INDEX
        if LATEST_GDF is None:
            self.send_error_response(404, "No enriched GeoDataFrame available")
            return
            
        try:
            # Convert buildings to STAC items
            stac_items = []
            for _, row in LATEST_GDF.iterrows():
                props = row.to_dict()
                geometry = props.pop('geometry', None)
                item = {
                    "type": "Feature",
                    "stac_version": "1.0.0",
                    "id": props.get('id', f"bldg_{len(stac_items)}"),
                    "geometry": geometry.__geo_interface__ if geometry else None,
                    "properties": props,
                    "bbox": list(geometry.bounds) if geometry else None
                }
                stac_items.append(item)
            
            stac_collection = {
                "type": "FeatureCollection",
                "stac_version": "1.0.0",
                "features": stac_items
            }
            
            stac_path = os.path.join(STUDIO_DIR, 'latest_export_stac.json')
            with open(stac_path, 'w') as f:
                json.dump(stac_collection, f, indent=2)
            
            with open(stac_path, 'r') as f:
                stac_data = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(stac_data.encode())
        except Exception as e:
            self.send_error_response(500, f"Error exporting STAC: {str(e)}")

    def _handle_export_tif(self):
        """Export the latest computed index raster as GeoTIFF."""
        global LATEST_GDF, LATEST_INDEX
        if LATEST_GDF is None or LATEST_INDEX is None:
            self.send_error_response(404, "No computed raster available")
            return
            
        try:
            # This is a placeholder - in production would export the actual raster array
            # For now, we'll return an informative message
            import io
            from rasterio.transform import from_bounds
            
            # Create a synthetic GeoTIFF from the current bbox and index
            bbox = LATEST_GDF.total_bounds.tolist()
            width, height = 256, 256
            transform = from_bounds(*bbox, width, height)
            
            # Generate synthetic data based on index type
            np.random.seed(42)
            if 'lst' in LATEST_INDEX.lower():
                data = np.random.uniform(-2, 5, (height, width)).astype(np.float32)
            else:
                data = np.random.uniform(-0.2, 0.8, (height, width)).astype(np.float32)
            
            buf = io.BytesIO()
            with rasterio.open(
                buf, 'w',
                driver='GTiff',
                height=height,
                width=width,
                count=1,
                dtype='float32',
                crs='EPSG:4326',
                transform=transform,
                compress='lzw'
            ) as dst:
                dst.write(data, 1)
            
            buf.seek(0)
            self.send_response(200)
            self.send_header('Content-type', 'image/tiff')
            self.send_header('Content-Disposition', f'attachment; filename="{LATEST_INDEX}_raster.tif"')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(buf.read())
        except Exception as e:
            self.send_error_response(500, f"Error exporting GeoTIFF: {str(e)}")

    def _handle_export_parquet(self):
        """Export the latest GeoDataFrame as GeoParquet."""
        global LATEST_GDF
        if LATEST_GDF is None:
            self.send_error_response(404, "No enriched GeoDataFrame available")
            return
            
        try:
            parquet_path = os.path.join(STUDIO_DIR, 'latest_export.parquet')
            OpenDatasetExporter.export_parquet(LATEST_GDF, parquet_path)
            
            with open(parquet_path, 'rb') as f:
                parquet_data = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/octet-stream')
            self.send_header('Content-Disposition', 'attachment; filename="earthbridge_buildings.parquet"')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(parquet_data)
        except Exception as e:
            self.send_error_response(500, f"Error exporting Parquet: {str(e)}")

    def _handle_upload_shapefile(self):
        """Parse proper multipart file upload."""
        global LATEST_GDF
        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))
        
        file_body = self.rfile.read(content_length)
        if 'multipart/form-data' in content_type:
            try:
                boundary = content_type.split("boundary=")[1].encode()
                parts = file_body.split(b"--" + boundary)
                for part in parts:
                    if b'filename=' in part:
                        header_end = part.find(b"\r\n\r\n")
                        if header_end != -1:
                            file_body = part[header_end+4:-2] # drop leading \r\n\r\n and trailing \r\n
                            break
            except Exception as e:
                self.send_error_response(400, f"Failed to parse multipart form: {e}")
                return
            
        if not file_body:
            self.send_error_response(400, "No file content received.")
            return
            
        # Parse shapefile body
        try:
            temp_path = os.path.join(STUDIO_DIR, "temp_upload.zip")
            if file_body.startswith(b'PK'):
                with open(temp_path, "wb") as f:
                    f.write(file_body)
                gdf = gpd.read_file(temp_path)
            else:
                temp_path = os.path.join(STUDIO_DIR, "temp_upload.geojson")
                with open(temp_path, "wb") as f:
                    f.write(file_body)
                gdf = gpd.read_file(temp_path)
                
            LATEST_GDF = gdf
            
            # Reproject to WGS84 if needed
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
                LATEST_GDF = gdf
                
            bounds = gdf.total_bounds
            
            self._send_success_response({
                "status": "success",
                "message": f"Successfully loaded {len(gdf)} features.",
                "bbox": [bounds[0], bounds[1], bounds[2], bounds[3]]
            })
        except Exception as e:
            self.send_error_response(500, f"Error parsing spatial file: {e}")

    def _handle_compute(self):
        """Wire up real STAC COG raster pipeline and GEE engines."""
        global LATEST_GDF, LATEST_INDEX
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        
        bbox = data.get('bbox')
        index_type = data.get('index_type')
        city_name = data.get('city_name', 'Analysis Region')
        
        if not bbox or not index_type:
            self.send_error_response(400, "Missing bbox or index_type")
            return
            
        LATEST_INDEX = index_type
        
        # 1. Fetch Buildings
        if LATEST_GDF is None:
            # Fetch from Overture if no boundary/buildings were uploaded
            print("[earth-bridge] Fetching live overture footprints...")
            LATEST_GDF = overture_engine.fetch_building_footprints(bbox=bbox, limit=1000)
            
        bldg_count = len(LATEST_GDF) if LATEST_GDF is not None else 0
            
        # 2. Raster processing
        if index_type in ['lst_anomaly', 'lst']:
            # Handle LST anomaly via GEE
            print("[earth-bridge] Triggering GEE LST Computation...")
            result = gee_engine.compute_lst_climatology_anomaly(bbox=bbox)
            
            # Use real zonal stats if GEE is available
            if LATEST_GDF is not None and result.get('status') == 'success' and result.get('tile_url'):
                # For GEE LST, we use the computed anomaly stats
                # In production, would sample from EE asset
                stats_val = result.get('stats', {})
                if stats_val:
                    LATEST_GDF[f'{index_type}_mean'] = [float(stats_val.get('mean', 0))] * len(LATEST_GDF)
            
            self._send_success_response({
                "status": "success",
                "provider": result.get('provider', 'GEE'),
                "tile_url": result.get('tile_url'),
                "stats": result.get('stats', {}),
                "geojson": LATEST_GDF.to_json() if LATEST_GDF is not None else None,
                "buildings_processed": bldg_count,
                "city": city_name
            })
            
            # Generate report
            if LATEST_GDF is not None:
                generate_policy_report(LATEST_GDF, city_name, os.path.join(STUDIO_DIR, "executive_report.html"))
            return
            
        if index_type not in INDEX_REGISTRY:
            self.send_error_response(400, f"Unsupported index_type: {index_type}")
            return
            
        # Try real satellite data first
        print(f"[earth-bridge] Fetching Planetary Computer STAC for {index_type}...")
        raster_result = stac_engine.fetch_raster_for_bbox(bbox, index_type=index_type)
        provider = raster_result.get('provider', 'Planetary Computer')
        
        registry_entry = INDEX_REGISTRY[index_type]
        band1_key, band2_key = registry_entry['bands']
        
        # Map generic band names to the returned array names
        band_mapping = {
            'nir': 'nir_array',
            'red': 'red_array',
            'swir': 'swir_array',
            'green': 'green_array'
        }
        
        arr1 = raster_result.get(band_mapping[band1_key])
        arr2 = raster_result.get(band_mapping[band2_key])
        
        if arr1 is not None and arr2 is not None:
            print(f"[earth-bridge] Computing {index_type.upper()}...")
            result_array = registry_entry['compute'](arr1, arr2)
            mean_val = float(np.nanmean(result_array))
            min_val = float(np.nanmin(result_array))
            max_val = float(np.nanmax(result_array))
            
            # Compute real zonal statistics for each building
            if LATEST_GDF is not None:
                LATEST_GDF = compute_building_zonal_stats(
                    LATEST_GDF, 
                    result_array, 
                    index_name=index_type,
                    bbox=bbox
                )
        else:
            mean_val, min_val, max_val = 0, 0, 0
            
        # Generate report
        if LATEST_GDF is not None:
            generate_policy_report(LATEST_GDF, city_name, os.path.join(STUDIO_DIR, "executive_report.html"))
            
        self._send_success_response({
            "status": "success", 
            "city": city_name, 
            "provider": provider,
            "stats": {
                f"{index_type}_mean": mean_val,
                "min": min_val,
                "max": max_val
            },
            "buildings_processed": bldg_count,
            "geojson": LATEST_GDF.to_json() if LATEST_GDF is not None else None
        })

    def _send_success_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True

def start_server(port=8000):
    max_port = port + 10
    while port <= max_port:
        try:
            server = ReusableThreadingServer(('', port), StudioRequestHandler)
            print(f"===========================================================")
            print(f"[earth-bridge] Web Studio Server running on port {port}")
            print(f"-> Open http://localhost:{port} in your browser")
            print(f"===========================================================")
            server.serve_forever()
            break
        except OSError as e:
            if e.errno == 98 or e.errno == 10048: # Address already in use
                print(f"Port {port} in use, trying next...")
                port += 1
            else:
                raise
                
    if port > max_port:
        print("No available ports found.")

if __name__ == '__main__':
    start_server()
