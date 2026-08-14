// Global State
let map;
let baseLayer;
let buildingsLayer;
let tileLayer;
let currentBbox = [78.350, 17.300, 78.550, 17.500];
let currentIndexLayer = null;
let indexLayers = {};  // Store multiple index layers

// DOM Elements
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const errorToastContainer = document.getElementById('errorToastContainer');

document.addEventListener('DOMContentLoaded', () => {
  initMap();
  setupEventListeners();
  // Set initial map view without triggering compute
  map.fitBounds([
    [currentBbox[1], currentBbox[0]],
    [currentBbox[3], currentBbox[2]]
  ]);
});

function initMap() {
  map = L.map('map', {
    zoomControl: false,
    layers: []
  }).setView([17.40, 78.45], 13);
  L.control.zoom({ position: 'bottomright' }).addTo(map);

  // Add multiple base layers
  baseLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    name: 'Dark Canvas'
  });
  
  const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: '&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    name: 'Satellite'
  });
  
  const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    name: 'OpenStreetMap'
  });
  
  // Default to satellite for better visual context
  satelliteLayer.addTo(map);
  baseLayer = satelliteLayer;

  buildingsLayer = L.geoJSON(null, {
    style: getBuildingStyle,
    onEachFeature: onEachBuilding
  }).addTo(map);

  // Layer control for base layers
  const baseLayers = {
    'Satellite': satelliteLayer,
    'Dark Canvas': baseLayer,
    'OpenStreetMap': osmLayer
  };
  
  const overlayLayers = {
    'Building Footprints': buildingsLayer
  };
  
  L.control.layers(baseLayers, overlayLayers, { position: 'topright' }).addTo(map);

  // Force map to render correctly inside flex container
  setTimeout(() => map.invalidateSize(), 100);
}

function showError(msg) {
  const toast = document.createElement('div');
  toast.className = 'error-toast';
  toast.innerHTML = `<i data-lucide="alert-circle" style="vertical-align: middle; margin-right: 8px;"></i> ${msg}`;
  errorToastContainer.appendChild(toast);
  lucide.createIcons();
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

function showLoading(msg = 'Computing spatial indices...') {
  loadingMessage.textContent = msg;
  loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
  loadingOverlay.classList.add('hidden');
}

function setupEventListeners() {
  // Compute Button
  document.getElementById('btnRunCompute').addEventListener('click', runMasterCompute);

  // Map Layer Toggles
  document.getElementById('overtureToggle').addEventListener('change', (e) => {
    if(e.target.checked) map.addLayer(buildingsLayer);
    else map.removeLayer(buildingsLayer);
  });
  document.getElementById('tilingToggle').addEventListener('change', (e) => {
    if(e.target.checked && tileLayer) map.addLayer(tileLayer);
    else if(tileLayer) map.removeLayer(tileLayer);
  });

  // Manual BBox entry
  document.getElementById('btnSetBbox').addEventListener('click', () => {
    const minLon = parseFloat(document.getElementById('coordMinLon').value);
    const minLat = parseFloat(document.getElementById('coordMinLat').value);
    const maxLon = parseFloat(document.getElementById('coordMaxLon').value);
    const maxLat = parseFloat(document.getElementById('coordMaxLat').value);
    
    if (isNaN(minLon) || isNaN(minLat) || isNaN(maxLon) || isNaN(maxLat)) {
      showError('Invalid coordinates entered.');
      return;
    }
    currentBbox = [minLon, minLat, maxLon, maxLat];
    map.fitBounds([
      [minLat, minLon],
      [maxLat, maxLon]
    ]);
  });

  // Drag and drop for shapefile
  const dropZone = document.getElementById('dropZone');
  const shapefileInput = document.getElementById('shapefileInput');
  const btnBrowseFile = document.getElementById('btnBrowseFile');

  btnBrowseFile.addEventListener('click', () => shapefileInput.click());
  
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-active');
  });
  
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-active'));
  
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-active');
    if (e.dataTransfer.files.length) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  shapefileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      handleFileUpload(e.target.files[0]);
    }
  });

  // Exports
  document.getElementById('btnExportGeoJSON').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/export_geojson');
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'earthbridge_buildings.geojson';
      a.click();
      URL.revokeObjectURL(url);
    } catch(e) { 
      showError('Export failed: ' + e.message); 
    }
  });

  document.getElementById('btnExportCSV').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/export_csv');
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'earthbridge_scores.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch(e) { 
      showError('Export failed: ' + e.message); 
    }
  });

  document.getElementById('btnExportSTAC').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/export_stac');
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'earthbridge_stac.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch(e) { 
      showError('Export failed: ' + e.message); 
    }
  });

  document.getElementById('btnExportParquet').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/export_parquet');
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'earthbridge_buildings.parquet';
      a.click();
      URL.revokeObjectURL(url);
    } catch(e) { 
      showError('Export failed: ' + e.message); 
    }
  });

  document.getElementById('btnExportTIFF').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/export_tif');
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'earthbridge_raster.tif';
      a.click();
      URL.revokeObjectURL(url);
    } catch(e) { 
      showError('Export failed: ' + e.message); 
    }
  });
}

async function handleFileUpload(file) {
  document.getElementById('uploadFileName').textContent = file.name;
  showLoading(`Parsing boundary: ${file.name}...`);
  
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const response = await fetch('/api/upload_shapefile', {
      method: 'POST',
      body: formData
    });
    const result = await response.json();
    
    if(result.status === 'success' && result.bbox) {
      currentBbox = result.bbox;
      // Update inputs
      document.getElementById('coordMinLon').value = currentBbox[0].toFixed(3);
      document.getElementById('coordMinLat').value = currentBbox[1].toFixed(3);
      document.getElementById('coordMaxLon').value = currentBbox[2].toFixed(3);
      document.getElementById('coordMaxLat').value = currentBbox[3].toFixed(3);
      
      map.fitBounds([
        [currentBbox[1], currentBbox[0]],
        [currentBbox[3], currentBbox[2]]
      ]);
    } else {
      throw new Error(result.message || 'Upload failed');
    }
  } catch (error) {
    console.error(error);
    showError("File upload error: " + error.message);
  } finally {
    hideLoading();
  }
}

async function runMasterCompute() {
  const indexType = document.getElementById('indexSelect').value;
  const indexLabel = document.getElementById('indexSelect').options[document.getElementById('indexSelect').selectedIndex].text.split('—')[0].trim();
  
  showLoading(`Computing ${indexLabel} on live data...`);
  const statusBadge = document.getElementById('computeStatusBadge');
  statusBadge.className = 'status-pill status-running';
  statusBadge.textContent = 'Running Compute...';

  try {
    const response = await fetch('/api/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bbox: currentBbox,
        index_type: indexType,
        city_name: 'Analysis Region'
      })
    });

    const data = await response.json();
    if(data.status === 'error') throw new Error(data.message);

    updateDashboard(data, indexLabel);
    
    if (data.geojson) {
      const geojsonObj = typeof data.geojson === 'string' ? JSON.parse(data.geojson) : data.geojson;
      buildingsLayer.clearLayers();
      buildingsLayer.addData(geojsonObj);
    }
    
    // Add index layer toggle for this computed index
    addIndexLayerToggle(indexType, indexLabel);
    
    if (data.tile_url) {
      if(tileLayer) map.removeLayer(tileLayer);
      tileLayer = L.tileLayer(data.tile_url, { opacity: 0.6 }).addTo(map);
      // Ensure layer ordering (vector on top)
      buildingsLayer.bringToFront();
    }

    statusBadge.className = 'status-pill status-success';
    statusBadge.textContent = 'Compute Success';
  } catch (error) {
    console.error(error);
    showError(error.message);
    statusBadge.className = 'status-pill status-ready';
    statusBadge.textContent = 'Error';
  } finally {
    hideLoading();
  }
}

function addIndexLayerToggle(indexType, indexLabel) {
  const container = document.getElementById('indexLayerToggles');
  
  // Remove empty state message if present
  const emptyState = container.querySelector('.empty-state');
  if (emptyState) emptyState.remove();
  
  // Check if toggle already exists
  if (container.querySelector(`[data-index="${indexType}"]`)) return;
  
  const toggleDiv = document.createElement('div');
  toggleDiv.className = 'toggle-control index-layer-toggle';
  toggleDiv.dataset.index = indexType;
  toggleDiv.innerHTML = `
    <label class="switch">
      <input type="checkbox" checked>
      <span class="slider round"></span>
    </label>
    <span>${indexLabel}</span>
    <button class="btn btn-sm btn-secondary" onclick="removeIndexLayer('${indexType}')" title="Remove layer">
      <i data-lucide="trash-2"></i>
    </button>
  `;
  
  const checkbox = toggleDiv.querySelector('input');
  checkbox.addEventListener('change', (e) => {
    if (e.target.checked) {
      if (indexLayers[indexType]) {
        map.addLayer(indexLayers[indexType]);
      }
    } else {
      if (indexLayers[indexType]) {
        map.removeLayer(indexLayers[indexType]);
      }
    }
  });
  
  container.appendChild(toggleDiv);
  lucide.createIcons();
}

function removeIndexLayer(indexType) {
  if (indexLayers[indexType]) {
    map.removeLayer(indexLayers[indexType]);
    delete indexLayers[indexType];
  }
  const toggle = document.querySelector(`[data-index="${indexType}"]`);
  if (toggle) toggle.remove();
  
  // Show empty state if no layers
  const container = document.getElementById('indexLayerToggles');
  if (container.children.length === 0) {
    container.innerHTML = '<p class="empty-state">Run a compute to enable index layers</p>';
  }
}

// Make removeIndexLayer globally accessible
window.removeIndexLayer = removeIndexLayer;

function updateDashboard(data, indexLabel) {
  document.getElementById('statIndexName').textContent = indexLabel;
  document.getElementById('statProvider').textContent = data.provider || 'Local Memory';
  document.getElementById('statBldgCount').textContent = data.buildings_processed || '0';
  
  let statsObj = data.stats || {};
  let meanKey = Object.keys(statsObj).find(k => k.includes('mean')) || Object.keys(statsObj)[0];
  
  if (meanKey) {
    document.getElementById('statMean').textContent = statsObj[meanKey].toFixed(4);
  } else {
    document.getElementById('statMean').textContent = 'N/A';
  }
  
  if (statsObj.min !== undefined && statsObj.max !== undefined) {
    document.getElementById('statRange').textContent = `${statsObj.min.toFixed(2)} / ${statsObj.max.toFixed(2)}`;
  } else if (statsObj.LST_Anomaly_min !== undefined) {
      document.getElementById('statRange').textContent = `${statsObj.LST_Anomaly_min.toFixed(2)} / ${statsObj.LST_Anomaly_max.toFixed(2)}`;
  } else {
      document.getElementById('statRange').textContent = 'N/A';
  }

  // Populate Table based on geojson properties
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';
  
  if (!data.geojson) return;
  const features = (typeof data.geojson === 'string' ? JSON.parse(data.geojson) : data.geojson).features || [];
  
  if (features.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No buildings found in this region.</td></tr>';
    return;
  }
  
  features.slice(0, 15).forEach(f => {
    const props = f.properties;
    const scoreKeys = Object.keys(props).filter(k => k.includes('_mean') || k.includes('score'));
    const score = scoreKeys.length > 0 ? (props[scoreKeys[0]] || 0) : 0;
    
    let vulText = 'Moderate';
    let vulColor = '#e3b341';
    if(score < 0.3) { vulText = 'High Risk'; vulColor = '#f85149'; }
    else if(score > 0.6) { vulText = 'Optimal'; vulColor = '#56d364'; }
    
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${props.id || 'bldg_...'}</td>
      <td style="text-transform: capitalize;">${props.subtype || 'Unknown'}</td>
      <td>${(props.height || 0).toFixed(1)}m</td>
      <td style="font-weight: 600;">${score.toFixed(3)}</td>
      <td style="color: ${vulColor}; font-weight: 500;">${vulText}</td>
    `;
    tbody.appendChild(tr);
  });
}

function getBuildingStyle(feature) {
  const props = feature.properties;
  const scoreKeys = Object.keys(props).filter(k => k.includes('_mean') || k.includes('score'));
  const score = scoreKeys.length > 0 ? (props[scoreKeys[0]] || 0.5) : 0.5;

  let color = '#d29922'; // Moderate / Yellow
  if (score < 0.3) color = '#f85149'; // Deficit / Red
  else if (score >= 0.6) color = '#2ea043'; // Optimal / Green

  return {
    color: color,
    weight: 1,
    fillColor: color,
    fillOpacity: 0.6
  };
}

function onEachBuilding(feature, layer) {
  const props = feature.properties;
  const scoreKeys = Object.keys(props).filter(k => k.includes('_mean') || k.includes('score'));
  const score = scoreKeys.length > 0 ? (props[scoreKeys[0]] || 0) : 0;
  
  layer.bindPopup(`
    <div style="font-family: var(--font-sans); color: #c9d1d9;">
      <strong style="color: #fff;">Bldg: ${props.id || 'N/A'}</strong><br>
      Subtype: ${props.subtype || 'Residential'}<br>
      Height: ${(props.height || 0).toFixed(1)}m<br>
      <hr style="border-color: #30363d; margin: 8px 0;">
      Zonal Mean: <strong style="color: #58a6ff;">${score.toFixed(3)}</strong>
    </div>
  `);
}

lucide.createIcons();
