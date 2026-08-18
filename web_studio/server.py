"""
earth-bridge Studio — local HTTP server backing the browser UI.

Binds to loopback only. The process holds live Google Earth Engine credentials
and accepts file uploads without authentication, and must therefore not be
reachable from the network. EARTHBRIDGE_STUDIO_HOST overrides the bind address
and should be set only where that exposure is understood and intended.
"""

import os
import sys
import json
import time
import threading
import traceback
import shutil
import tempfile
import zipfile
import email
import email.policy
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import geopandas as gpd

from earthbridge.stac_engine import STACBackend
from earthbridge.gee_engine import EarthEngineBackend
from earthbridge.overture_engine import OvertureBackend
from earthbridge.exporter import OpenDatasetExporter

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_HOST = os.environ.get("EARTHBRIDGE_STUDIO_HOST", "127.0.0.1")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_PREVIEW_FEATURES = 5000

stac_backend = STACBackend()
earth_engine = EarthEngineBackend()
overture_backend = OvertureBackend()

# Guards the session state below. The server is single-user by design, but a
# browser issues concurrent requests and this handler is threaded, so unguarded
# module state can interleave between an export and the compute that replaced it.
_state_lock = threading.Lock()
_session = {"gdf": None, "index": None, "bbox": None}


def _safe_extract(archive: zipfile.ZipFile, dest: str) -> None:
    """Extract a zip, rejecting entries that escape `dest`.

    zipfile.extractall follows '../' components and absolute paths in member
    names, which lets an uploaded archive write anywhere the process can reach.
    """
    dest_root = os.path.realpath(dest)
    for member in archive.infolist():
        target = os.path.realpath(os.path.join(dest_root, member.filename))
        if target != dest_root and not target.startswith(dest_root + os.sep):
            raise ValueError(f"Refusing zip entry outside archive root: {member.filename!r}")
    archive.extractall(dest_root)


class StudioRequestHandler(SimpleHTTPRequestHandler):
    server_version = "earth-bridge-studio"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STUDIO_DIR, **kwargs)

    # -- plumbing ------------------------------------------------------

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, code, message, remedy=None):
        self._json({"status": "error", "message": message, "remedy": remedy, "code": code}, code)

    def _bytes(self, data: bytes, content_type: str, filename=None):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if not self.path.endswith((".css", ".js", ".png", ".ico")):
            sys.stderr.write(f"[earth-bridge] {fmt % args}\n")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # -- routing -------------------------------------------------------

    def do_GET(self):
        routes = {
            "/api/gee_status": self._gee_status,
            "/api/export_geojson": self._export_geojson,
            "/api/export_csv": self._export_csv,
            "/api/export_parquet": self._export_parquet,
            "/api/export_stac": self._export_stac,
        }
        handler = routes.get(self.path)
        if handler is None:
            if self.path.startswith("/api/"):
                self._fail(404, f"No such endpoint: {self.path}")
            else:
                super().do_GET()
            return
        try:
            handler()
        except Exception as e:
            traceback.print_exc()
            self._fail(500, str(e))

    def do_POST(self):
        routes = {
            "/api/compute": self._compute,
            "/api/buildings": self._buildings,
            "/api/upload_shapefile": self._upload,
            "/api/init_gee": self._init_gee,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._fail(404, f"No such endpoint: {self.path}")
            return
        try:
            handler()
        except Exception as e:
            traceback.print_exc()
            self._fail(500, str(e))

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        if length > MAX_UPLOAD_BYTES:
            raise ValueError("Request body too large.")
        return json.loads(self.rfile.read(length))

    # -- Earth Engine --------------------------------------------------

    def _gee_status(self):
        self._json({
            "initialized": earth_engine.initialized,
            "project_id": earth_engine.project_id or "",
            "error": earth_engine.init_error,
        })

    def _init_gee(self):
        data = self._read_json_body()
        ok, message = earth_engine.reconnect(data.get("project_id", ""))
        if ok:
            self._json({"status": "success", "message": message,
                        "project_id": earth_engine.project_id})
        else:
            self._fail(400, message,
                       remedy="Run 'earthengine authenticate' in a terminal, then retry.")

    # -- compute -------------------------------------------------------

    def _compute(self):
        data = self._read_json_body()
        bbox = data.get("bbox")
        index_type = data.get("index_type")
        if not bbox or not index_type:
            self._fail(400, "Request must include 'bbox' and 'index_type'.")
            return

        with _state_lock:
            _session["index"] = index_type
            _session["bbox"] = bbox

        # Earth Engine gives measured statistics. Without it, only display tiles
        # are available, and the response says so rather than implying the
        # numbers are simply missing.
        if earth_engine.initialized:
            result = earth_engine.compute_spectral_index(bbox=bbox, index_type=index_type)
            if result.get("status") == "success":
                self._json({**result, "compute_mode": "earth-engine"})
                return
            print(f"[earth-bridge] Earth Engine: {result.get('reason')}")

        result = stac_backend.tiles_for(bbox=bbox, layer=index_type)
        if result.get("status") != "success":
            self._json({**result, "compute_mode": "none"})
            return

        self._json({
            **result,
            "compute_mode": "tiles-only",
            "note": (
                "Display tiles only — no measured values. Tile colours are a "
                "rendered stretch, not data. Connect Earth Engine for statistics."
            ),
        })

    def _buildings(self):
        """Fetch building footprints for a bbox and hold them for export."""
        data = self._read_json_body()
        bbox = data.get("bbox")
        if not bbox:
            self._fail(400, "Request must include 'bbox'.")
            return
        limit = int(data.get("limit", 1000))

        gdf = overture_backend.fetch_building_footprints(bbox=bbox, limit=limit)
        provenance = gdf.attrs.get("provenance")
        if len(gdf) == 0:
            self._json({
                "status": "unavailable",
                "reason": "No building footprints found for this area.",
                "provenance": provenance,
                "count": 0,
            })
            return

        with _state_lock:
            _session["gdf"] = gdf

        preview = gdf.iloc[:MAX_PREVIEW_FEATURES] if len(gdf) > MAX_PREVIEW_FEATURES else gdf
        self._json({
            "status": "success",
            "count": int(len(gdf)),
            "preview_count": int(len(preview)),
            "provenance": provenance,
            "source": sorted(gdf["source"].dropna().unique().tolist()) if "source" in gdf else [],
            "geojson": preview.to_json(),
        })

    # -- exports -------------------------------------------------------

    def _current_gdf(self):
        with _state_lock:
            gdf = _session["gdf"]
        if gdf is None:
            self._fail(
                404,
                "Nothing to export yet.",
                remedy="Upload a boundary or fetch building footprints first.",
            )
            return None
        return gdf

    def _export_geojson(self):
        gdf = self._current_gdf()
        if gdf is None:
            return
        self._bytes(gdf.to_json().encode(), "application/geo+json", "earthbridge.geojson")

    def _export_csv(self):
        gdf = self._current_gdf()
        if gdf is None:
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export.csv")
            OpenDatasetExporter.export_csv(gdf, path)
            with open(path, "rb") as f:
                self._bytes(f.read(), "text/csv", "earthbridge.csv")

    def _export_parquet(self):
        gdf = self._current_gdf()
        if gdf is None:
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export.parquet")
            try:
                OpenDatasetExporter.export_parquet(gdf, path)
            except ImportError as e:
                self._fail(501, str(e))
                return
            with open(path, "rb") as f:
                self._bytes(f.read(), "application/octet-stream", "earthbridge.parquet")

    def _export_stac(self):
        """Export held features as a STAC ItemCollection."""
        gdf = self._current_gdf()
        if gdf is None:
            return
        with _state_lock:
            provenance = gdf.attrs.get("provenance")

        features = []
        for idx, row in gdf.iterrows():
            props = {k: v for k, v in row.items() if k != gdf.geometry.name}
            geom = row[gdf.geometry.name]
            props = {k: (None if v is not None and v != v else v) for k, v in props.items()}
            if provenance:
                props["earthbridge:provenance"] = provenance
            features.append({
                "type": "Feature",
                "stac_version": "1.0.0",
                "id": str(props.get("id") or f"feature-{idx}"),
                "geometry": geom.__geo_interface__ if geom is not None else None,
                "bbox": list(geom.bounds) if geom is not None else None,
                "properties": props,
                "assets": {},
            })

        payload = {"type": "FeatureCollection", "stac_version": "1.0.0", "features": features}
        self._bytes(
            json.dumps(payload, indent=2, default=str).encode(),
            "application/json", "earthbridge_stac.json",
        )

    # -- upload --------------------------------------------------------

    def _upload(self):
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))

        if "multipart/form-data" not in content_type:
            self._fail(400, "Upload must be multipart/form-data.")
            return
        if length <= 0:
            self._fail(400, "Empty upload.")
            return
        if length > MAX_UPLOAD_BYTES:
            self._fail(413, f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024*1024)} MB limit.")
            return

        body = self.rfile.read(length)
        temp_dir = tempfile.mkdtemp(prefix="eb_upload_")
        try:
            saved = self._save_parts(body, content_type, temp_dir)
            if not saved:
                self._fail(400, "No files could be read from the upload.")
                return

            gdf = self._read_vector(saved, temp_dir)
            if gdf is None:
                return
            if len(gdf) == 0:
                self._fail(400, "The uploaded file contains no geometries.")
                return

            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
                crs_note = "No CRS was declared in the file; assumed EPSG:4326."
            elif gdf.crs.to_epsg() != 4326:
                original = str(gdf.crs)
                gdf = gdf.to_crs("EPSG:4326")
                crs_note = f"Reprojected from {original} to EPSG:4326."
            else:
                crs_note = None

            with _state_lock:
                _session["gdf"] = gdf

            preview = gdf.iloc[:MAX_PREVIEW_FEATURES] if len(gdf) > MAX_PREVIEW_FEATURES else gdf
            bounds = gdf.total_bounds.tolist()
            self._json({
                "status": "success",
                "message": f"Loaded {len(gdf)} features.",
                "count": int(len(gdf)),
                "preview_count": int(len(preview)),
                "truncated": len(preview) < len(gdf),
                "crs_note": crs_note,
                "bbox": bounds,
                "geojson": preview.to_json(),
            })
        except ValueError as e:
            self._fail(400, str(e))
        except Exception as e:
            traceback.print_exc()
            self._fail(500, f"Could not read the uploaded file: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _save_parts(body: bytes, content_type: str, temp_dir: str):
        """Write each uploaded part to `temp_dir`, returning the saved paths."""
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin1")
        msg = email.message_from_bytes(header + body, policy=email.policy.default)

        saved = []
        for part in msg.iter_attachments():
            filename = part.get_filename()
            if not filename:
                continue
            # basename strips any directory component a client may have sent.
            clean = os.path.basename(filename)
            if not clean or clean in (".", ".."):
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                raw = part.get_payload()
                payload = raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else None
            if not payload:
                continue
            path = os.path.join(temp_dir, clean)
            with open(path, "wb") as f:
                f.write(payload)
            saved.append(path)
        return saved

    def _read_vector(self, saved, temp_dir):
        """Locate and read a vector layer among the uploaded files."""
        vector_exts = (".geojson", ".json", ".gpkg", ".kml")
        zip_path = next((p for p in saved if p.lower().endswith(".zip")), None)
        shp_path = next((p for p in saved if p.lower().endswith(".shp")), None)
        geo_path = next((p for p in saved if p.lower().endswith(vector_exts)), None)

        if zip_path:
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(zip_path) as z:
                    _safe_extract(z, extract_dir)
            except ValueError as e:
                self._fail(400, str(e))
                return None
            except zipfile.BadZipFile:
                self._fail(400, "That file is not a readable zip archive.")
                return None

            found_shp = found_geo = None
            for root, _, files in os.walk(extract_dir):
                for name in files:
                    lower = name.lower()
                    if lower.endswith(".shp") and not found_shp:
                        found_shp = os.path.join(root, name)
                    elif lower.endswith(vector_exts) and not found_geo:
                        found_geo = os.path.join(root, name)
            target = found_shp or found_geo
            if not target:
                self._fail(400, "No .shp, .geojson or .gpkg layer was found inside the zip.")
                return None
            return gpd.read_file(target)

        if shp_path:
            base = os.path.splitext(shp_path)[0]
            if not any(os.path.exists(base + ext) for ext in (".shx", ".SHX")):
                self._fail(
                    400,
                    "A shapefile needs its sidecar files.",
                    remedy="Select the .shp, .shx and .dbf together, or upload a .zip containing them.",
                )
                return None
            return gpd.read_file(shp_path)

        if geo_path:
            return gpd.read_file(geo_path)

        self._fail(400, "Upload a .zip, .shp (with .shx/.dbf), .geojson, .gpkg or .kml file.")
        return None


def start_server(port: int = 8000, host: str = DEFAULT_HOST) -> None:
    """Serve the Studio, trying successive ports if the first is taken."""
    last_error = None
    for candidate in range(port, port + 11):
        try:
            server = ThreadingHTTPServer((host, candidate), StudioRequestHandler)
        except OSError as e:
            last_error = e
            continue

        url = f"http://{host}:{candidate}"
        # The launcher reads this line to learn which port was actually bound.
        print(f"EARTHBRIDGE_STUDIO_URL={url}", flush=True)
        print(f"[earth-bridge] Studio running at {url}", flush=True)
        print(f"[earth-bridge] Bound to {host} (loopback only). Ctrl-C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[earth-bridge] Shutting down.")
        finally:
            server.server_close()
        return

    raise SystemExit(
        f"[earth-bridge] No free port between {port} and {port + 10}: {last_error}"
    )


if __name__ == "__main__":
    cli_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    start_server(port=cli_port)
