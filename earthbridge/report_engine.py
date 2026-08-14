"""
Executive Visual Map & Policy Report Generator
===============================================
Generates standalone, visually stunning interactive HTML map reports tailored for urban planners and policy makers.
"""

import os
import json
import geopandas as gpd

class PolicyReportGenerator:
    """Generates executive visual spatial reports for city mayors, urban planners, and policy makers."""

    @staticmethod
    def generate_executive_html_report(
        enriched_gdf: gpd.GeoDataFrame,
        city_name: str = "Analysis Region",
        index_name: str = "Greenery & Microclimate Score",
        output_filepath: str = "executive_report.html"
    ) -> str:
        """Creates a standalone, beautiful HTML interactive spatial dashboard file."""
        total_bldgs = len(enriched_gdf)
        
        # Try to find a score column dynamically for python-side summary stats
        scores = []
        score_col = None
        for col in enriched_gdf.columns:
            if '_mean' in col or 'index' in col or 'score' in col:
                score_col = col
                scores = enriched_gdf[col].dropna()
                break
                
        if len(scores) > 0:
            mean_score = float(scores.mean())
            high_risk_count = int((scores < 0.3).sum())
            moderate_count = int(((scores >= 0.3) & (scores < 0.6)).sum())
            optimal_count = int((scores >= 0.6).sum())
        else:
            mean_score = 0.5
            high_risk_count = 0
            moderate_count = total_bldgs
            optimal_count = 0

        geojson_str = enriched_gdf.to_json()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{city_name} Urban Policy & Climate Report</title>
  
  <!-- Leaflet CSS & Fonts -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  
  <style>
    :root {{
      --bg-dark: #0f172a;
      --bg-card: #1e293b;
      --border-color: #334155;
      --text-bright: #f8fafc;
      --text-muted: #94a3b8;
      --accent-green: #22c55e;
      --accent-yellow: #eab308;
      --accent-red: #ef4444;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text-bright); height: 100vh; display: flex; flex-direction: column; }}
    
    header {{ height: 70px; background-color: var(--bg-card); border-bottom: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; }}
    header h1 {{ font-size: 1.25rem; font-weight: 700; color: #fff; }}
    header h1 span {{ color: #38bdf8; font-weight: 400; }}
    .subtitle {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 2px; }}
    
    .container {{ display: flex; flex: 1; height: calc(100vh - 70px); }}
    
    .executive-summary {{ width: 360px; background-color: #0f172a; border-right: 1px solid var(--border-color); padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; }}
    
    .metric-card {{ background-color: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 6px; }}
    .metric-title {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.5px; }}
    .metric-value {{ font-size: 1.8rem; font-weight: 700; color: #fff; }}
    
    .breakdown-list {{ display: flex; flex-direction: column; gap: 10px; margin-top: 6px; }}
    .breakdown-item {{ display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; padding: 8px 12px; border-radius: 6px; background-color: rgba(255,255,255,0.03); }}
    .status-red {{ border-left: 4px solid var(--accent-red); }}
    .status-yellow {{ border-left: 4px solid var(--accent-yellow); }}
    .status-green {{ border-left: 4px solid var(--accent-green); }}

    .map-section {{ flex: 1; position: relative; }}
    #map {{ width: 100%; height: 100%; background-color: #1e293b; z-index: 1; }}

    .legend {{ position: absolute; bottom: 30px; right: 30px; z-index: 1000; background: var(--bg-card); padding: 14px 18px; border-radius: 8px; border: 1px solid var(--border-color); font-size: 0.8rem; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
    .legend-item {{ display: flex; align-items: center; gap: 10px; }}
    .color-box {{ width: 14px; height: 14px; border-radius: 3px; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>{city_name} Urban Policy & Microclimate Report <span>| Executive Dashboard</span></h1>
      <p class="subtitle">Powered by earth-bridge & Overture Building Intelligence</p>
    </div>
    <button onclick="window.print()" style="background: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600;">Print / Save PDF</button>
  </header>

  <div class="container">
    <aside class="executive-summary">
      <div class="metric-card">
        <span class="metric-title">Target Region</span>
        <span class="metric-value">{city_name}</span>
      </div>

      <div class="metric-card">
        <span class="metric-title">Average {index_name}</span>
        <span class="metric-value" style="color: #38bdf8;">{mean_score:.3f}</span>
      </div>

      <div class="metric-card">
        <span class="metric-title">Building Vulnerability Breakdown</span>
        <div class="breakdown-list">
          <div class="breakdown-item status-red">
            <span>High Risk / Deficit (&lt; 0.30)</span>
            <strong>{high_risk_count} buildings</strong>
          </div>
          <div class="breakdown-item status-yellow">
            <span>Moderate (0.30 - 0.60)</span>
            <strong>{moderate_count} buildings</strong>
          </div>
          <div class="breakdown-item status-green">
            <span>Optimal (&gt; 0.60)</span>
            <strong>{optimal_count} buildings</strong>
          </div>
        </div>
      </div>

      <div class="metric-card">
        <span class="metric-title">Policy Recommendation</span>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.5; margin-top: 4px;">
          Prioritize targeted interventions (e.g., tree canopy planting, cool roof retrofits) for red-coded building blocks in urban dense sectors.
        </p>
      </div>
    </aside>

    <section class="map-section">
      <div id="map"></div>

      <div class="legend">
        <strong>Building Vulnerability Index</strong>
        <div class="legend-item"><div class="color-box" style="background: #ef4444;"></div> High Vulnerability / Low Greenery (&lt; 0.30)</div>
        <div class="legend-item"><div class="color-box" style="background: #eab308;"></div> Moderate Greenery / Heat Risk (0.30 - 0.60)</div>
        <div class="legend-item"><div class="color-box" style="background: #22c55e;"></div> High Canopy / Cool Microclimate (&gt; 0.60)</div>
      </div>
    </section>
  </div>

  <script>
    const map = L.map('map').setView([17.3850, 78.4867], 13);

    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    }}).addTo(map);

    const geoData = {geojson_str};

    const geoLayer = L.geoJSON(geoData, {{
      style: function(feature) {{
        const props = feature.properties;
        const scoreKeys = Object.keys(props).filter(k => k.includes('_mean') || k.includes('score') || k.includes('index'));
        const score = scoreKeys.length > 0 ? (props[scoreKeys[0]] || 0.5) : 0.5;
        
        let color = '#eab308';
        if (score < 0.3) color = '#ef4444';
        else if (score >= 0.6) color = '#22c55e';

        return {{
          color: color,
          weight: 1,
          fillColor: color,
          fillOpacity: 0.6
        }};
      }},
      onEachFeature: function(feature, layer) {{
        const props = feature.properties;
        const scoreKeys = Object.keys(props).filter(k => k.includes('_mean') || k.includes('score') || k.includes('index'));
        const score = scoreKeys.length > 0 ? (props[scoreKeys[0]] || 0.5) : 0.5;
        
        layer.bindPopup(`
          <div style="font-family: sans-serif; font-size: 13px; color: #1e293b;">
            <strong style="color: #0f172a;">Building ID: ${{props.id || 'N/A'}}</strong><br>
            Subtype: ${{props.subtype || 'residential'}}<br>
            Height: ${{props.height || 12}} meters<br>
            <hr style="margin: 6px 0; border: none; border-top: 1px solid #cbd5e1;">
            Microclimate Score: <strong style="color: ${{score < 0.3 ? '#ef4444' : (score > 0.6 ? '#22c55e' : '#d97706')}};">${{score.toFixed(3)}}</strong>
          </div>
        `);
      }}
    }}).addTo(map);

    if (geoLayer.getBounds().isValid()) {{
      map.fitBounds(geoLayer.getBounds());
    }}
  </script>
</body>
</html>"""

        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        return os.path.abspath(output_filepath)

# Aliases to consolidate previous duplicated modules
class ExecutiveReportEngine(PolicyReportGenerator):
    @staticmethod
    def generate_report(gdf: gpd.GeoDataFrame, output_path: str = "report.html") -> str:
        return PolicyReportGenerator.generate_executive_html_report(gdf, output_filepath=output_path)

def generate_policy_report(enriched_gdf: gpd.GeoDataFrame, city_name: str = "Analysis Region", output_filepath: str = "executive_report.html") -> str:
    return PolicyReportGenerator.generate_executive_html_report(enriched_gdf, city_name=city_name, output_filepath=output_filepath)
