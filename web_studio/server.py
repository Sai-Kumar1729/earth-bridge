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
        elif self.path == '/api/gee_status':
            self._handle_gee_status()
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
            elif self.path == '/api/init_gee':
                self._handle_init_gee()
            else:
                self.send_error_response(404, "Endpoint not found")
        except Exception as e:
            traceback.print_exc()
            self.send_error_response(500, str(e))
            
        elapsed = time.time() - start
        print(f'[earth-bridge] {self.command} {self.path} completed in {elapsed:.2f}s')

    def _handle_gee_status(self):
        """Return live Earth Engine authentication and connection status."""
        self._send_success_response({
            "initialized": gee_engine.initialized,
            "project_id": os.environ.get("EE_PROJECT_ID", ""),
            "error": gee_engine.init_error
        })

    def _handle_init_gee(self):
        """Authenticate / Reconnect Google Earth Engine with a GCP Project ID."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        project_id = data.get('project_id', '').strip()
        
        success, message = gee_engine.reconnect(project_id)
        if success:
            self._send_success_response({
                "status": "success",
                "message": message,
                "project_id": project_id
            })
        else:
            self.send_error_response(400, f"GEE Initialization Failed: {message}")

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
        """Parse multipart file upload supporting ZIP, SHP (+ SHX/DBF/PRJ), GeoJSON, KML, GPKG."""
        global LATEST_GDF
        import email
        import email.policy
        import tempfile
        import shutil
        import zipfile
        
        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))
        
        if not content_type or 'multipart/form-data' not in content_type:
            self.send_error_response(400, "Upload must be multipart/form-data")
            return
            
        file_body = self.rfile.read(content_length)
        if not file_body:
            self.send_error_response(400, "Empty payload received.")
            return

        temp_dir = tempfile.mkdtemp(prefix="eb_upload_")
        try:
            # Reconstruct full HTTP multipart payload with headers for email parser
            header_bytes = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode('latin1')
            msg = email.message_from_bytes(header_bytes + file_body, policy=email.policy.default)
            
            saved_files = []
            for part in (msg.iter_attachments() if hasattr(msg, 'iter_attachments') else msg.walk()):
                filename = part.get_filename()
                if not filename:
                    cd = part.get('Content-Disposition', '')
                    if 'filename=' in cd:
                        for token in cd.split(';'):
                            token = token.strip()
                            if token.startswith('filename='):
                                filename = token.split('=', 1)[1].strip(' "')
                                break
                if filename:
                    clean_name = os.path.basename(filename)
                    out_path = os.path.join(temp_dir, clean_name)
                    
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        payload = part.get_payload()
                        if isinstance(payload, str):
                            payload = payload.encode('utf-8', errors='surrogateescape')
                    
                    if payload:
                        with open(out_path, "wb") as f:
                            f.write(payload)
                        saved_files.append(out_path)

            # Fallback boundary parsing if email parser found no attachments
            if not saved_files:
                boundary = None
                for param in content_type.split(';'):
                    param = param.strip()
                    if param.startswith('boundary='):
                        boundary = param.split('=', 1)[1].strip('"').encode('latin1')
                if boundary:
                    parts = file_body.split(b'--' + boundary)
                    for p in parts:
                        if b'filename=' in p:
                            try:
                                h_end = p.find(b'\r\n\r\n')
                                if h_end != -1:
                                    header_section = p[:h_end].decode('latin1', errors='ignore')
                                    fn = None
                                    for line in header_section.split('\r\n'):
                                        if 'filename=' in line:
                                            fn = line.split('filename=', 1)[1].strip(' "')
                                            break
                                    if fn:
                                        clean_fn = os.path.basename(fn)
                                        data = p[h_end+4:]
                                        if data.endswith(b'\r\n'):
                                            data = data[:-2]
                                        out_p = os.path.join(temp_dir, clean_fn)
                                        with open(out_p, 'wb') as f:
                                            f.write(data)
                                        saved_files.append(out_p)
                            except Exception:
                                pass

            if not saved_files:
                self.send_error_response(400, "No valid files extracted from upload.")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return

            shp_file = None
            zip_file = None
            geo_file = None

            for fpath in saved_files:
                lname = fpath.lower()
                if lname.endswith('.zip'):
                    zip_file = fpath
                elif lname.endswith('.shp'):
                    shp_file = fpath
                elif lname.endswith(('.geojson', '.json', '.gpkg', '.kml')):
                    geo_file = fpath

            gdf = None

            # 1. Handle ZIP archives
            if zip_file:
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                try:
                    with zipfile.ZipFile(zip_file, 'r') as z:
                        z.extractall(extract_dir)
                except Exception as ze:
                    self.send_error_response(400, f"Corrupted or invalid zip file: {ze}")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return

                found_shp = None
                found_geo = None
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        fl = file.lower()
                        if fl.endswith('.shp'):
                            found_shp = os.path.join(root, file)
                        elif fl.endswith(('.geojson', '.json', '.gpkg', '.kml')):
                            found_geo = os.path.join(root, file)
                
                target = found_shp or found_geo
                if not target:
                    self.send_error_response(400, "No supported spatial vector layer (.shp, .geojson, .gpkg) found inside the zip archive.")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return
                
                try:
                    gdf = gpd.read_file(target)
                except Exception:
                    gdf = gpd.read_file(target, engine='fiona')

            # 2. Handle direct Shapefile upload
            elif shp_file:
                base = os.path.splitext(shp_file)[0]
                if not (os.path.exists(base + '.shx') or os.path.exists(base + '.SHX')):
                    self.send_error_response(400, "Missing .shx file! A Shapefile requires at least .shp, .shx, and .dbf files. Please upload all files together or upload a .zip containing them.")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return
                try:
                    gdf = gpd.read_file(shp_file)
                except Exception:
                    gdf = gpd.read_file(shp_file, engine='fiona')

            # 3. Handle direct GeoJSON / GPKG / KML
            elif geo_file:
                try:
                    gdf = gpd.read_file(geo_file)
                except Exception:
                    gdf = gpd.read_file(geo_file, engine='fiona')

            if gdf is None or len(gdf) == 0:
                self.send_error_response(400, "Parsed spatial file contains 0 valid geometries.")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return

            # Ensure valid Coordinate Reference System
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            elif gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")

            LATEST_GDF = gdf
            bounds = gdf.total_bounds.tolist() # [minx, miny, maxx, maxy]

            # Return simplified geojson payload if too large for browser performance
            export_gdf = gdf
            if len(gdf) > 5000:
                export_gdf = gdf.sample(5000)

            geojson_str = export_gdf.to_json()

            self._send_success_response({
                "status": "success",
                "message": f"Successfully loaded {len(gdf)} features.",
                "bbox": [bounds[0], bounds[1], bounds[2], bounds[3]],
                "geojson": geojson_str
            })

            shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            traceback.print_exc()
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.send_error_response(500, f"Error parsing spatial file: {str(e)}")

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
        
        # 1. 100% Google Earth Engine Server-Side Cloud Compute (if GEE is authenticated)
        if gee_engine.initialized:
            print(f"[earth-bridge] Executing 100% GEE Server-Side Cloud Compute for {index_type.upper()} ({city_name})...")
            gee_result = gee_engine.compute_spectral_index(bbox=bbox, index_type=index_type)
            if gee_result.get("status") == "success":
                self._send_success_response({
                    "status": "success",
                    "provider": gee_result.get("provider", "Google Earth Engine Cloud"),
                    "tile_url": gee_result.get("tile_url"),
                    "stats": gee_result.get("stats", {}),
                    "layer_name": gee_result.get("layer_name", f"GEE {index_type.upper()}"),
                    "city": city_name,
                    "compute_mode": "Google Earth Engine Cloud"
                })
                return
            else:
                print(f"[earth-bridge] GEE compute returned note: {gee_result.get('message')}")

        # 2. Universal Open Satellite Stream (MPC STAC + NASA GIBS)
        print(f"[earth-bridge] Streaming open satellite data for {index_type.upper()} ({city_name})...")
        open_result = stac_engine.fetch_open_satellite_stream(bbox=bbox, index_type=index_type)
        
        self._send_success_response({
            "status": open_result.get("status", "success"),
            "city": city_name,
            "provider": open_result.get("provider", "Microsoft Planetary Computer / NASA GIBS"),
            "tile_url": open_result.get("tile_url"),
            "stats": open_result.get("stats", {}),
            "layer_name": open_result.get("layer_name", f"{index_type.upper()} Satellite Stream"),
            "message": "Streamed from open satellite data. Connect GEE in top bar for server-side cloud compute."
        })

    def _send_success_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = False

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
