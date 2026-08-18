"""
Standalone HTML map export.

Writes a self-contained page with a Leaflet map of a GeoDataFrame, coloured by a
numeric column, plus the provenance of the underlying data.

What this deliberately does not do: assign risk categories, or recommend
interventions. Earlier versions labelled buildings "High Risk" and emitted a
"Policy Recommendation" using fixed cut-offs of 0.3 and 0.6 applied to whatever
column happened to be found first — the same thresholds for NDVI, for a
temperature anomaly in degrees Celsius, and for a unitless index. Those
categories were not meaningful, and presenting them to planners implied a
validation that had never been done.

The map now classifies by quantiles of the column actually selected, states
which column that is, and leaves interpretation to the reader.
"""

import os
import json
import html
from typing import Optional, Dict, Any

import geopandas as gpd
import numpy as np
from pandas.api.types import is_numeric_dtype

# Inlining the whole GeoJSON into the HTML stops being viable well before this,
# but a hard cap prevents accidentally writing a several-hundred-megabyte file.
MAX_INLINE_FEATURES = 20000

QUANTILE_COLORS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]


def _pick_numeric_column(gdf: gpd.GeoDataFrame, preferred: Optional[str] = None) -> Optional[str]:
    """Choose the column to colour by, preferring an explicit caller choice."""
    if preferred and preferred in gdf.columns:
        return preferred
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        # pandas extension dtypes such as StringDtype raise from np.issubdtype,
        # so the check has to go through the pandas type API.
        if is_numeric_dtype(gdf[col]) and gdf[col].notna().any():
            return col
    return None


def write_map_report(
    gdf: gpd.GeoDataFrame,
    title: str = "earth-bridge map export",
    value_column: Optional[str] = None,
    output_path: str = "map_report.html",
) -> str:
    """Write a self-contained HTML map of `gdf`.

    Args:
        gdf: Features to map. Must be in EPSG:4326.
        title: Page heading.
        value_column: Numeric column to colour by. Auto-selected if omitted.
        output_path: Destination path.

    Returns:
        Absolute path to the written file.
    """
    if len(gdf) == 0:
        raise ValueError("Cannot write a map report for an empty GeoDataFrame.")
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    truncated = False
    if len(gdf) > MAX_INLINE_FEATURES:
        gdf = gdf.iloc[:MAX_INLINE_FEATURES]
        truncated = True

    column = _pick_numeric_column(gdf, value_column)

    if column is not None:
        values = gdf[column].dropna()
        # Quantile breaks describe this dataset only. They are not thresholds
        # carried over from any external standard.
        breaks = [float(v) for v in np.nanquantile(values, [0.2, 0.4, 0.6, 0.8])] if len(values) else []
        summary = {
            "column": column,
            "count": int(len(values)),
            "mean": float(values.mean()) if len(values) else None,
            "min": float(values.min()) if len(values) else None,
            "max": float(values.max()) if len(values) else None,
        }
    else:
        breaks = []
        summary = {"column": None, "count": len(gdf), "mean": None, "min": None, "max": None}

    provenance = gdf.attrs.get("provenance")
    bounds = gdf.total_bounds.tolist()

    def fmt(v, digits=3):
        return "—" if v is None else f"{v:.{digits}f}"

    if provenance:
        prov_rows = "".join(
            f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
            for k, v in provenance.items()
            if v is not None and k != "requested"
        )
        prov_html = f"<table class='prov'>{prov_rows}</table>"
    else:
        prov_html = (
            "<p class='muted'>No provenance recorded for this dataset. "
            "Data produced by earth-bridge carries provenance in "
            "<code>gdf.attrs['provenance']</code>.</p>"
        )

    legend_html = ""
    if column and breaks:
        labels = [
            f"&lt; {breaks[0]:.3g}",
            f"{breaks[0]:.3g} – {breaks[1]:.3g}",
            f"{breaks[1]:.3g} – {breaks[2]:.3g}",
            f"{breaks[2]:.3g} – {breaks[3]:.3g}",
            f"&ge; {breaks[3]:.3g}",
        ]
        items = "".join(
            f"<div class='legend-item'><span class='swatch' style='background:{c}'></span>{l}</div>"
            for c, l in zip(QUANTILE_COLORS, labels)
        )
        legend_html = (
            f"<strong>{html.escape(column)}</strong>"
            f"<div class='muted' style='margin:4px 0 8px'>quintiles of this dataset</div>{items}"
        )

    payload = {
        "geojson": json.loads(gdf.to_json()),
        "column": column,
        "breaks": breaks,
        "colors": QUANTILE_COLORS,
        "bounds": bounds,
    }

    banner = (
        f"<div class='banner'>Showing the first {MAX_INLINE_FEATURES:,} of "
        f"{len(gdf):,}+ features. Export to GeoParquet for the full dataset.</div>"
        if truncated else ""
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --line:#334155; --fg:#f8fafc; --muted:#94a3b8; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:system-ui,-apple-system,'Segoe UI',sans-serif; background:var(--bg);
         color:var(--fg); height:100vh; display:flex; flex-direction:column; }}
  header {{ padding:14px 24px; background:var(--card); border-bottom:1px solid var(--line); }}
  header h1 {{ font-size:1.1rem; font-weight:600; }}
  header p {{ font-size:.78rem; color:var(--muted); margin-top:2px; }}
  .banner {{ background:#78350f; color:#fed7aa; font-size:.78rem; padding:6px 24px; }}
  .container {{ display:flex; flex:1; min-height:0; }}
  aside {{ width:320px; padding:20px; overflow-y:auto; border-right:1px solid var(--line);
           display:flex; flex-direction:column; gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }}
  .card h2 {{ font-size:.7rem; text-transform:uppercase; letter-spacing:.5px;
              color:var(--muted); font-weight:600; margin-bottom:8px; }}
  .metric {{ font-size:1.5rem; font-weight:700; }}
  .kv {{ display:flex; justify-content:space-between; font-size:.8rem; padding:3px 0; }}
  .kv span:first-child {{ color:var(--muted); }}
  .muted {{ color:var(--muted); font-size:.75rem; line-height:1.45; }}
  table.prov {{ width:100%; border-collapse:collapse; font-size:.72rem; }}
  table.prov td {{ padding:3px 4px; vertical-align:top; border-bottom:1px solid var(--line); }}
  table.prov td:first-child {{ color:var(--muted); white-space:nowrap; padding-right:10px; }}
  #map {{ flex:1; background:#1e293b; }}
  .legend {{ position:absolute; bottom:24px; right:24px; z-index:1000; background:var(--card);
             border:1px solid var(--line); border-radius:8px; padding:12px 14px; font-size:.75rem;
             box-shadow:0 8px 20px rgba(0,0,0,.5); }}
  .legend-item {{ display:flex; align-items:center; gap:8px; padding:2px 0; }}
  .swatch {{ width:14px; height:14px; border-radius:3px; display:inline-block; }}
  .viewport {{ flex:1; position:relative; display:flex; }}
</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <p>Generated by earth-bridge — descriptive map export, not a validated assessment</p>
</header>
{banner}
<div class="container">
  <aside>
    <div class="card">
      <h2>Features</h2>
      <div class="metric">{len(gdf):,}</div>
    </div>
    <div class="card">
      <h2>{html.escape(column) if column else 'No numeric column'}</h2>
      <div class="kv"><span>mean</span><span>{fmt(summary['mean'])}</span></div>
      <div class="kv"><span>min</span><span>{fmt(summary['min'])}</span></div>
      <div class="kv"><span>max</span><span>{fmt(summary['max'])}</span></div>
      <div class="kv"><span>non-null</span><span>{summary['count']:,}</span></div>
    </div>
    <div class="card">
      <h2>Data provenance</h2>
      {prov_html}
    </div>
    <div class="card">
      <h2>Reading this map</h2>
      <p class="muted">Colours are quintiles of <code>{html.escape(column) if column else 'n/a'}</code>
      within this dataset. They are relative to these features only and carry no
      external threshold or standard. No suitability, risk or priority judgement
      is implied.</p>
    </div>
  </aside>
  <div class="viewport">
    <div id="map"></div>
    {f'<div class="legend">{legend_html}</div>' if legend_html else ''}
  </div>
</div>
<script>
const DATA = {json.dumps(payload)};
const map = L.map('map');
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO', subdomains:'abcd'
}}).addTo(map);

function colorFor(v) {{
  if (v === null || v === undefined || DATA.breaks.length === 0) return '#64748b';
  for (let i = 0; i < DATA.breaks.length; i++) if (v < DATA.breaks[i]) return DATA.colors[i];
  return DATA.colors[DATA.colors.length - 1];
}}

const layer = L.geoJSON(DATA.geojson, {{
  style: f => {{
    const c = colorFor(DATA.column ? f.properties[DATA.column] : null);
    return {{ color:c, weight:1, fillColor:c, fillOpacity:0.65 }};
  }},
  pointToLayer: (f, latlng) => L.circleMarker(latlng, {{ radius:5 }}),
  onEachFeature: (f, lyr) => {{
    const rows = Object.entries(f.properties)
      .map(([k, v]) => `<tr><td style="color:#64748b;padding-right:8px">${{k}}</td><td>${{v}}</td></tr>`)
      .join('');
    lyr.bindPopup(`<table style="font:12px system-ui;border-collapse:collapse">${{rows}}</table>`);
  }}
}}).addTo(map);

const b = DATA.bounds;
map.fitBounds([[b[1], b[0]], [b[3], b[2]]]);
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return os.path.abspath(output_path)


def generate_policy_report(
    enriched_gdf: Optional[gpd.GeoDataFrame] = None,
    city_name: str = "Analysis Region",
    output_filepath: str = "map_report.html",
    *,
    gdf: Optional[gpd.GeoDataFrame] = None,
    output_path: Optional[str] = None,
    value_column: Optional[str] = None,
) -> str:
    """Deprecated alias for `write_map_report`.

    Accepts both the old positional names (`enriched_gdf`, `output_filepath`) and
    the keyword names the top-level `eb.report()` was passing (`gdf`,
    `output_path`), which previously raised TypeError.
    """
    frame = gdf if gdf is not None else enriched_gdf
    if frame is None:
        raise TypeError("generate_policy_report requires a GeoDataFrame.")
    return write_map_report(
        frame,
        title=city_name,
        value_column=value_column,
        output_path=output_path or output_filepath,
    )


class PolicyReportGenerator:
    """Deprecated. Use `write_map_report`."""

    @staticmethod
    def generate_executive_html_report(
        enriched_gdf: gpd.GeoDataFrame,
        city_name: str = "Analysis Region",
        index_name: str = "",
        output_filepath: str = "map_report.html",
    ) -> str:
        return write_map_report(
            enriched_gdf, title=city_name,
            value_column=index_name or None, output_path=output_filepath,
        )


class ExecutiveReportEngine(PolicyReportGenerator):
    """Deprecated. Use `write_map_report`."""

    @staticmethod
    def generate_report(gdf: gpd.GeoDataFrame, output_path: str = "map_report.html") -> str:
        return write_map_report(gdf, output_path=output_path)
