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
  checkGeeStatus();
  // Set initial map view without triggering compute
  map.fitBounds([
    [currentBbox[1], currentBbox[0]],
    [currentBbox[3], currentBbox[2]]
  ]);
});

async function checkGeeStatus() {
  const statusBadge = document.getElementById('geeStatusText');
  try {
    const resp = await fetch('/api/gee_status');
    const data = await resp.json();
    if (data.initialized) {
      statusBadge.textContent = data.project_id ? `Connected (${data.project_id})` : 'Connected';
      statusBadge.style.color = '#56d364';
    } else {
      statusBadge.textContent = 'Setup Project ID';
      statusBadge.style.color = '#e3b341';
    }
  } catch (e) {
    statusBadge.textContent = 'Offline';
  }
}

function initMap() {
  map = L.map('map', {
    zoomControl: false,
    layers: []
  }).setView([17.40, 78.45], 13);
  L.control.zoom({ position: 'bottomright' }).addTo(map);

  // Add high-resolution, reliable base layers
  const darkCanvasLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
  });
  
  const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: '&copy; Esri, Maxar, Earthstar Geographics',
    maxZoom: 19
  });
  
  const lightCanvasLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
  });

  const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  });
  
  // Set Dark Canvas as active default basemap
  darkCanvasLayer.addTo(map);

  buildingsLayer = L.geoJSON(null, {
    style: getBuildingStyle,
    onEachFeature: onEachBuilding
  }).addTo(map);

  // Layer control for base layers
  const baseLayers = {
    'Dark Canvas (CARTO)': darkCanvasLayer,
    'Satellite Imagery (Esri)': satelliteLayer,
    'Light Canvas (CARTO)': lightCanvasLayer,
    'OpenStreetMap Standard': osmLayer
  };
  
  const overlayLayers = {
    'Building Footprints': buildingsLayer
  };
  
  layersControl = L.control.layers(baseLayers, overlayLayers, { position: 'topright' }).addTo(map);

  // Initialize Geoman Drawing Controls on Map
  if (map.pm) {
    map.pm.addControls({
      position: 'topleft',
      drawCircle: false,
      drawCircleMarker: false,
      drawMarker: false,
      drawPolyline: false,
      drawText: false,
      cutPolygon: false,
      drawRectangle: true,
      drawPolygon: true,
      editMode: true,
      dragMode: true,
      removalMode: true
    });

    // Custom dark styling for Geoman drawing
    map.pm.setPathOptions({
      color: '#38bdf8',
      fillColor: '#38bdf8',
      fillOpacity: 0.2,
      weight: 2
    });

    // Listen to shape creation events
    map.on('pm:create', (e) => {
      handleDrawnShape(e.layer, e.shape);
    });
  }

  // Force map to render correctly inside flex container
  setTimeout(() => map.invalidateSize(), 100);
}

// Uploaded Vector Layers & Drawn Shapes Registry
let layersControl;
let uploadedLayers = {};
let layerColorIndex = 0;
let drawnShapeLayer = null;
let drawnShapeCount = 1;
let latestRoiGeoJson = null;
let roiMaskLayer = null;

const LAYER_COLORS = [
  '#38bdf8', // Sky blue
  '#34d399', // Emerald
  '#f59e0b', // Amber
  '#ec4899', // Pink
  '#8b5cf6', // Violet
  '#06b6d4', // Cyan
  '#10b981'  // Green
];

function getNextLayerColor() {
  const color = LAYER_COLORS[layerColorIndex % LAYER_COLORS.length];
  layerColorIndex++;
  return color;
}

function extractRingsFromGeom(geom, holesArray) {
  if (!geom) return;
  if (geom.type === 'Polygon') {
    if (geom.coordinates && geom.coordinates.length > 0) {
      holesArray.push(geom.coordinates[0]);
    }
  } else if (geom.type === 'MultiPolygon') {
    if (geom.coordinates) {
      geom.coordinates.forEach(polyCoords => {
        if (polyCoords && polyCoords.length > 0) {
          holesArray.push(polyCoords[0]);
        }
      });
    }
  }
}

function applyRoiInvertedMask(geojsonGeometry) {
  if (roiMaskLayer && map.hasLayer(roiMaskLayer)) {
    map.removeLayer(roiMaskLayer);
    roiMaskLayer = null;
  }
  
  if (!geojsonGeometry) return;
  
  try {
    // World boundary box [-180, -90] to [180, 90]
    const worldPolygon = [
      [-180, -90],
      [180, -90],
      [180, 90],
      [-180, 90],
      [-180, -90]
    ];
    
    let holes = [];
    
    if (geojsonGeometry.type === 'FeatureCollection') {
      geojsonGeometry.features.forEach(feat => {
        extractRingsFromGeom(feat.geometry, holes);
      });
    } else if (geojsonGeometry.type === 'Feature') {
      extractRingsFromGeom(geojsonGeometry.geometry, holes);
    } else {
      extractRingsFromGeom(geojsonGeometry, holes);
    }
    
    if (holes.length === 0) return;
    
    const maskFeature = {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [worldPolygon, ...holes]
      }
    };
    
    roiMaskLayer = L.geoJSON(maskFeature, {
      style: {
        fillColor: '#0b0f14',
        fillOpacity: 0.96,
        stroke: false,
        weight: 0,
        interactive: false
      }
    }).addTo(map);
    
    // Bring boundaries to front
    Object.values(uploadedLayers).forEach(item => {
      if (item.layer && map.hasLayer(item.layer)) {
        item.layer.bringToFront();
      }
    });
  } catch (err) {
    console.warn("Mask error:", err);
  }
}

function handleDrawnShape(layer, shapeType = 'Polygon') {
  // If a previous single-ROI shape was drawn, remove old one if user only wants 1 primary ROI
  if (drawnShapeLayer && map.hasLayer(drawnShapeLayer)) {
    map.removeLayer(drawnShapeLayer);
  }
  drawnShapeLayer = layer;

  // Extract Bounding Box
  const bounds = layer.getBounds();
  const minLon = bounds.getWest();
  const minLat = bounds.getSouth();
  const maxLon = bounds.getEast();
  const maxLat = bounds.getNorth();

  currentBbox = [minLon, minLat, maxLon, maxLat];
  latestRoiGeoJson = layer.toGeoJSON();

  // Update coordinate inputs
  const inputMinLon = document.getElementById('coordMinLon');
  const inputMinLat = document.getElementById('coordMinLat');
  const inputMaxLon = document.getElementById('coordMaxLon');
  const inputMaxLat = document.getElementById('coordMaxLat');
  if (inputMinLon) inputMinLon.value = minLon.toFixed(4);
  if (inputMinLat) inputMinLat.value = minLat.toFixed(4);
  if (inputMaxLon) inputMaxLon.value = maxLon.toFixed(4);
  if (inputMaxLat) inputMaxLat.value = maxLat.toFixed(4);

  // Update summary info
  const summaryBox = document.getElementById('drawnRoiSummary');
  const summaryCoords = document.getElementById('drawnRoiCoords');
  if (summaryBox && summaryCoords) {
    summaryBox.style.display = 'block';
    summaryCoords.innerHTML = `<strong>Drawn ${shapeType}:</strong> [${minLon.toFixed(3)}, ${minLat.toFixed(3)}] to [${maxLon.toFixed(3)}, ${maxLat.toFixed(3)}]`;
  }

  // Register in Uploaded Boundaries manager
  const layerId = `drawn_roi_${Date.now()}`;
  const layerColor = getNextLayerColor();

  layer.setStyle({
    color: layerColor,
    weight: 2,
    dashArray: '4, 4',
    fillColor: layerColor,
    fillOpacity: 0.2
  });

  layer.bindPopup(`
    <div style="font-family: var(--font-sans); color: #c9d1d9;">
      <strong style="color: #fff;">Drawn ROI #${drawnShapeCount} (${shapeType})</strong><br>
      Extent: ${minLon.toFixed(3)}, ${minLat.toFixed(3)} to ${maxLon.toFixed(3)}, ${maxLat.toFixed(3)}<br>
      <small style="color: #38bdf8;">Ready for immediate satellite compute</small>
    </div>
  `);

  uploadedLayers[layerId] = {
    name: `Drawn ${shapeType} #${drawnShapeCount}`,
    layer: layer,
    color: layerColor,
    count: 1,
    bbox: currentBbox
  };

  drawnShapeCount++;
  renderUploadedLayersList();

  if (layersControl) {
    layersControl.addOverlay(layer, `✏️ Drawn ${shapeType}`);
  }

  // Flash confirmation
  showError(`Captured drawn ${shapeType}: [${minLon.toFixed(3)}, ${minLat.toFixed(3)}] to [${maxLon.toFixed(3)}, ${maxLat.toFixed(3)}]`);
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
  // GEE Modal Listeners
  const btnGeeConfig = document.getElementById('btnGeeConfig');
  const geeModal = document.getElementById('geeModal');
  const btnCloseGeeModal = document.getElementById('btnCloseGeeModal');
  const btnConnectGee = document.getElementById('btnConnectGee');
  const geeProjectIdInput = document.getElementById('geeProjectIdInput');
  const geeInitFeedback = document.getElementById('geeInitFeedback');

  if (btnGeeConfig && geeModal) {
    btnGeeConfig.addEventListener('click', () => {
      geeModal.classList.remove('hidden');
      geeInitFeedback.textContent = '';
    });
  }

  if (btnCloseGeeModal && geeModal) {
    btnCloseGeeModal.addEventListener('click', () => {
      geeModal.classList.add('hidden');
    });
  }

  if (btnConnectGee) {
    btnConnectGee.addEventListener('click', async () => {
      const projectId = geeProjectIdInput.value.trim();
      if (!projectId) {
        geeInitFeedback.innerHTML = '<span style="color: #f85149;">Please enter a valid Google Cloud Project ID.</span>';
        return;
      }
      geeInitFeedback.innerHTML = '<span style="color: #58a6ff;">Authenticating with Earth Engine...</span>';
      try {
        const resp = await fetch('/api/init_gee', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: projectId })
        });
        const data = await resp.json();
        if (data.status === 'success') {
          geeInitFeedback.innerHTML = `<span style="color: #56d364;">${data.message}</span>`;
          checkGeeStatus();
          setTimeout(() => geeModal.classList.add('hidden'), 1200);
        } else {
          geeInitFeedback.innerHTML = `<span style="color: #f85149;">${data.message || 'Failed to authenticate GEE'}</span>`;
        }
      } catch (e) {
        geeInitFeedback.innerHTML = `<span style="color: #f85149;">Error: ${e.message}</span>`;
      }
    });
  }
  // 1. Sidebar Collapse / Expand Toggle
  const btnToggleSidebar = document.getElementById('btnToggleSidebar');
  const sidebar = document.getElementById('sidebar');
  const toggleIcon = document.getElementById('sidebarToggleIcon');

  if (btnToggleSidebar && sidebar) {
    btnToggleSidebar.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      const isCollapsed = sidebar.classList.contains('collapsed');
      if (toggleIcon) {
        toggleIcon.setAttribute('data-lucide', isCollapsed ? 'chevrons-right' : 'chevrons-left');
        lucide.createIcons();
      }
      setTimeout(() => map.invalidateSize(), 150);
    });
  }

  // 2. Drag to Resize Sidebar
  const resizer = document.getElementById('sidebarResizer');
  if (resizer && sidebar) {
    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
      isResizing = true;
      resizer.classList.add('resizing');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isResizing) return;
      const newWidth = Math.min(Math.max(e.clientX, 240), 650);
      sidebar.style.width = `${newWidth}px`;
      map.invalidateSize();
    });

    document.addEventListener('mouseup', () => {
      if (isResizing) {
        isResizing = false;
        resizer.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        map.invalidateSize();
      }
    });
  }

  // 3. Collapsible Section Headers
  document.querySelectorAll('.section-header').forEach(header => {
    header.addEventListener('click', () => {
      const targetId = header.dataset.target;
      const body = document.getElementById(targetId);
      if (body) {
        header.classList.toggle('collapsed');
        body.classList.toggle('collapsed');
      }
    });
  });

  // 4. ROI Tab Switching (Upload vs Draw vs Manual Coordinates)
  const tabUpload = document.getElementById('tabRoiUpload');
  const tabDraw = document.getElementById('tabRoiDraw');
  const tabManual = document.getElementById('tabRoiManual');
  const viewUpload = document.getElementById('roiUploadView');
  const viewDraw = document.getElementById('roiDrawView');
  const viewManual = document.getElementById('roiManualView');

  if (tabUpload && tabDraw && tabManual) {
    tabUpload.addEventListener('click', () => {
      tabUpload.classList.add('active');
      tabDraw.classList.remove('active');
      tabManual.classList.remove('active');
      viewUpload.classList.remove('hidden');
      viewDraw.classList.add('hidden');
      viewManual.classList.add('hidden');
    });

    tabDraw.addEventListener('click', () => {
      tabDraw.classList.add('active');
      tabUpload.classList.remove('active');
      tabManual.classList.remove('active');
      viewDraw.classList.remove('hidden');
      viewUpload.classList.add('hidden');
      viewManual.classList.add('hidden');
    });

    tabManual.addEventListener('click', () => {
      tabManual.classList.add('active');
      tabUpload.classList.remove('active');
      tabDraw.classList.remove('active');
      viewManual.classList.remove('hidden');
      viewUpload.classList.add('hidden');
      viewDraw.classList.add('hidden');
    });
  }

  // 5. Draw Tools Buttons
  const btnDrawRect = document.getElementById('btnDrawRect');
  const btnDrawPolygon = document.getElementById('btnDrawPolygon');
  const btnClearDraw = document.getElementById('btnClearDraw');

  if (btnDrawRect) {
    btnDrawRect.addEventListener('click', () => {
      if (map && map.pm) {
        map.pm.enableDraw('Rectangle', {
          snappable: true,
          cursorMarker: true,
          finishOn: 'click'
        });
      }
    });
  }

  if (btnDrawPolygon) {
    btnDrawPolygon.addEventListener('click', () => {
      if (map && map.pm) {
        map.pm.enableDraw('Polygon', {
          snappable: true,
          cursorMarker: true,
          finishOn: 'dblclick'
        });
      }
    });
  }

  if (btnClearDraw) {
    btnClearDraw.addEventListener('click', () => {
      if (map && map.pm) {
        map.pm.disableDraw();
      }
      if (drawnShapeLayer && map.hasLayer(drawnShapeLayer)) {
        map.removeLayer(drawnShapeLayer);
        drawnShapeLayer = null;
      }
      const summaryBox = document.getElementById('drawnRoiSummary');
      if (summaryBox) summaryBox.style.display = 'none';
    });
  }

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
      handleFileUpload(e.dataTransfer.files);
    }
  });

  shapefileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      handleFileUpload(e.target.files);
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

async function handleFileUpload(files) {
  let fileNames = Array.from(files).map(f => f.name).join(', ');
  const primaryName = files[0].name;
  document.getElementById('uploadFileName').textContent = fileNames;
  showLoading(`Parsing boundary: ${fileNames}...`);
  
  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append('file_' + i, files[i]);
  }
  
  try {
    const response = await fetch('/api/upload_shapefile', {
      method: 'POST',
      body: formData
    });
    const result = await response.json();
    
    if(result.status === 'success' && result.bbox) {
      currentBbox = result.bbox;
      // Update coordinate inputs
      document.getElementById('coordMinLon').value = currentBbox[0].toFixed(3);
      document.getElementById('coordMinLat').value = currentBbox[1].toFixed(3);
      document.getElementById('coordMaxLon').value = currentBbox[2].toFixed(3);
      document.getElementById('coordMaxLat').value = currentBbox[3].toFixed(3);
      
      const bounds = [
        [currentBbox[1], currentBbox[0]],
        [currentBbox[3], currentBbox[2]]
      ];
      map.fitBounds(bounds);
      
      // Add and register vector layer
      if (result.geojson) {
        const geojsonObj = typeof result.geojson === 'string' ? JSON.parse(result.geojson) : result.geojson;
        latestRoiGeoJson = geojsonObj;
        const layerId = 'layer_' + Date.now();
        const color = getNextLayerColor();
        const count = geojsonObj.features ? geojsonObj.features.length : 1;
        
        const shapeLayer = L.geoJSON(geojsonObj, {
          style: {
            color: color,
            weight: 2.5,
            fillColor: color,
            fillOpacity: 0.12,
            dashArray: '6, 4'
          },
          onEachFeature: (feature, layer) => {
            if (feature.properties && Object.keys(feature.properties).length > 0) {
              let rows = '';
              for (const [k, v] of Object.entries(feature.properties)) {
                rows += `<tr><td style="color: #8b949e; font-weight: 500; padding: 2px 6px;">${k}</td><td style="color: #fff; padding: 2px 6px;">${v}</td></tr>`;
              }
              layer.bindPopup(`
                <div style="font-family: var(--font-sans); font-size: 0.8rem; max-height: 200px; overflow-y: auto;">
                  <strong style="color: ${color}; font-size: 0.85rem;"><i data-lucide="map-pin"></i> ${primaryName}</strong>
                  <table style="margin-top: 6px; width: 100%; border-collapse: collapse;">${rows}</table>
                </div>
              `);
            }
          }
        }).addTo(map);
        
        // Add to Leaflet top-right layer switcher
        if (layersControl) {
          layersControl.addOverlay(shapeLayer, `📁 ${primaryName}`);
        }
        
        // Store in registry
        uploadedLayers[layerId] = {
          id: layerId,
          name: primaryName,
          layer: shapeLayer,
          color: color,
          count: count,
          bbox: currentBbox
        };
        
        renderUploadedLayersList();
      }
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

function renderUploadedLayersList() {
  const container = document.getElementById('uploadedLayersList');
  if (!container) return;
  
  const layerIds = Object.keys(uploadedLayers);
  if (layerIds.length === 0) {
    container.innerHTML = '<p class="empty-state">No custom boundaries uploaded yet</p>';
    return;
  }
  
  container.innerHTML = '';
  layerIds.forEach(id => {
    const item = uploadedLayers[id];
    const card = document.createElement('div');
    card.className = 'uploaded-layer-card';
    card.id = `card_${id}`;
    card.innerHTML = `
      <div class="layer-card-left">
        <label class="switch switch-sm">
          <input type="checkbox" checked id="toggle_${id}">
          <span class="slider round"></span>
        </label>
        <span class="layer-color-dot" style="background-color: ${item.color};"></span>
        <div class="layer-info" title="${item.name}">
          <span class="layer-title">${item.name}</span>
          <span class="layer-meta">${item.count} feature${item.count > 1 ? 's' : ''}</span>
        </div>
      </div>
      <div class="layer-card-actions">
        <button class="btn-icon" onclick="zoomToUploadedLayer('${id}')" title="Zoom to boundary extent">
          <i data-lucide="crosshair"></i>
        </button>
        <button class="btn-icon btn-icon-danger" onclick="removeUploadedLayer('${id}')" title="Remove layer">
          <i data-lucide="trash-2"></i>
        </button>
      </div>
    `;
    
    container.appendChild(card);
    
    // Wire toggle
    const toggle = card.querySelector(`#toggle_${id}`);
    toggle.addEventListener('change', (e) => {
      if (e.target.checked) {
        map.addLayer(item.layer);
      } else {
        map.removeLayer(item.layer);
      }
    });
  });
  
  lucide.createIcons();
}

function zoomToUploadedLayer(id) {
  const item = uploadedLayers[id];
  if (!item || !item.bbox) return;
  
  currentBbox = item.bbox;
  document.getElementById('coordMinLon').value = currentBbox[0].toFixed(3);
  document.getElementById('coordMinLat').value = currentBbox[1].toFixed(3);
  document.getElementById('coordMaxLon').value = currentBbox[2].toFixed(3);
  document.getElementById('coordMaxLat').value = currentBbox[3].toFixed(3);
  
  map.fitBounds([
    [item.bbox[1], item.bbox[0]],
    [item.bbox[3], item.bbox[2]]
  ]);
  
  // Flash layer on map to indicate focus
  if (!map.hasLayer(item.layer)) {
    map.addLayer(item.layer);
    const toggle = document.getElementById(`toggle_${id}`);
    if (toggle) toggle.checked = true;
  }
}

function removeUploadedLayer(id) {
  const item = uploadedLayers[id];
  if (!item) return;
  
  if (map.hasLayer(item.layer)) {
    map.removeLayer(item.layer);
  }
  if (layersControl) {
    layersControl.removeLayer(item.layer);
  }
  
  delete uploadedLayers[id];
  renderUploadedLayersList();
}

// Make globally accessible for inline onclick handlers
window.zoomToUploadedLayer = zoomToUploadedLayer;
window.removeUploadedLayer = removeUploadedLayer;

async function runMasterCompute() {
  const indexType = document.getElementById('indexSelect').value;
  const indexLabel = document.getElementById('indexSelect').options[document.getElementById('indexSelect').selectedIndex].text;
  
  showLoading(`Querying ${indexLabel} on live data...`);
  const statusBadge = document.getElementById('computeStatusBadge');
  statusBadge.className = 'status-pill status-running';
  statusBadge.textContent = 'Computing...';

  try {
    const response = await fetch('/api/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bbox: currentBbox,
        index_type: indexType,
        city_name: 'Selected ROI'
      })
    });

    const data = await response.json();
    
    if (data.status === 'unauthenticated') {
      showError(data.message || 'Google Earth Engine authentication required.');
      const geeModal = document.getElementById('geeModal');
      if (geeModal) geeModal.classList.remove('hidden');
      statusBadge.className = 'status-pill status-error';
      statusBadge.textContent = 'Auth Required';
      return;
    }
    
    if (data.status === 'error') {
      throw new Error(data.message || 'Compute failed');
    }

    updateDashboard(data, indexLabel);
    
    if (data.geojson) {
      const geojsonObj = typeof data.geojson === 'string' ? JSON.parse(data.geojson) : data.geojson;
      buildingsLayer.clearLayers();
      buildingsLayer.addData(geojsonObj);
    }
    
    if (data.tile_url) {
      if (tileLayer) map.removeLayer(tileLayer);
      
      const roiBounds = L.latLngBounds(
        [currentBbox[1], currentBbox[0]],
        [currentBbox[3], currentBbox[2]]
      );

      tileLayer = L.tileLayer(data.tile_url, { 
        opacity: 0.88,
        maxZoom: 19,
        bounds: roiBounds,
        attribution: data.provider || 'MODIS 250m Satellite'
      }).addTo(map);
      
      // Store in index layers registry
      indexLayers[indexType] = tileLayer;
      
      // Apply inverted polygon mask so satellite layer is strictly inside the ROI
      if (latestRoiGeoJson) {
        applyRoiInvertedMask(latestRoiGeoJson);
      }
      
      // Bring all uploaded boundary layers to front
      Object.values(uploadedLayers).forEach(item => {
        if (item.layer && map.hasLayer(item.layer)) {
          item.layer.bringToFront();
        }
      });
      
      // Add index layer toggle for this computed index
      addIndexLayerToggle(indexType, data.layer_name || indexLabel);
      
      if (layersControl) {
        layersControl.addOverlay(tileLayer, `🛰️ ${data.layer_name || indexLabel}`);
      }
      
      if (buildingsLayer) buildingsLayer.bringToFront();
    }

    statusBadge.className = 'status-pill status-success';
    statusBadge.textContent = 'Active Layer';
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
  if (!container) return;
  
  // Remove empty state message if present
  const emptyState = container.querySelector('.empty-state');
  if (emptyState) emptyState.remove();
  
  // Check if toggle already exists
  if (container.querySelector(`[data-index="${indexType}"]`)) return;
  
  const toggleDiv = document.createElement('div');
  toggleDiv.className = 'toggle-control index-layer-toggle';
  toggleDiv.dataset.index = indexType;
  toggleDiv.innerHTML = `
    <label class="switch switch-sm">
      <input type="checkbox" checked>
      <span class="slider round"></span>
    </label>
    <span style="font-size: 0.78rem; font-weight: 500;">${indexLabel}</span>
    <button class="btn-icon btn-icon-danger" onclick="removeIndexLayer('${indexType}')" title="Remove layer">
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
    if (layersControl) layersControl.removeLayer(indexLayers[indexType]);
    delete indexLayers[indexType];
  }
  const toggle = document.querySelector(`[data-index="${indexType}"]`);
  if (toggle) toggle.remove();
  
  // Show empty state if no layers
  const container = document.getElementById('indexLayerToggles');
  if (container && container.children.length === 0) {
    container.innerHTML = '<p class="empty-state">Run compute to enable index layers</p>';
  }
}

// Make removeIndexLayer globally accessible
window.removeIndexLayer = removeIndexLayer;

function updateDashboard(data, indexLabel) {
  document.getElementById('statIndexName').textContent = data.layer_name || indexLabel.split('—')[0];
  document.getElementById('statProvider').textContent = data.provider || 'Google Earth Engine';
  document.getElementById('statBldgCount').textContent = data.buildings_processed ? `${data.buildings_processed} polygons` : 'Regional ROI (250m)';
  
  let statsObj = data.stats || {};
  
  // Format Tree Canopy Cover percentages
  if (statsObj.Percent_Tree_Cover_mean !== undefined) {
    document.getElementById('statMean').textContent = `${statsObj.Percent_Tree_Cover_mean.toFixed(1)}% Canopy`;
    document.getElementById('statRange').textContent = `${statsObj.min.toFixed(0)}% — ${statsObj.max.toFixed(0)}%`;
  } else {
    let meanKey = Object.keys(statsObj).find(k => k.includes('mean')) || Object.keys(statsObj)[0];
    if (meanKey && typeof statsObj[meanKey] === 'number') {
      document.getElementById('statMean').textContent = statsObj[meanKey].toFixed(3);
    } else {
      document.getElementById('statMean').textContent = statsObj.resolution || 'Live Cloud';
    }
    
    if (statsObj.min !== undefined && statsObj.max !== undefined) {
      document.getElementById('statRange').textContent = `${statsObj.min.toFixed(2)} / ${statsObj.max.toFixed(2)}`;
    } else {
      document.getElementById('statRange').textContent = statsObj.composite_period || 'Continuous';
    }
  }

  // Populate Table
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  tbody.innerHTML = '';
  
  if (!data.geojson) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state" style="padding: 12px !important;">Active layer: <strong>${data.layer_name || 'MODIS Raster'}</strong> mapped across ROI.</td></tr>`;
    return;
  }
  
  const features = (typeof data.geojson === 'string' ? JSON.parse(data.geojson) : data.geojson).features || [];
  if (features.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No vector features in this region.</td></tr>';
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
