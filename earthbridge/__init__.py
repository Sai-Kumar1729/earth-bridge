"""
earth-bridge
============
Open Earth Data & Cross-Cloud STAC Engine
Bridging Google Earth Engine, Microsoft Planetary Computer, and Overture Maps Foundation.
"""

__version__ = "0.2.0"

from .gee_engine import GEEOperationEngine
from .stac_engine import ProductionSTACEngine
from .overture_engine import ProductionOvertureEngine
from .zonal_stats import compute_building_zonal_stats
from .spectral_indexes import SpectralIndexCalculator, compute_ndvi, compute_ndwi
from .report_engine import ExecutiveReportEngine, PolicyReportGenerator, generate_policy_report
from .tiling import partition_state_bbox
from .stac_reader import ZeroAuthSTACReader, search_stac_anonymously
from .exporter import export_open_dataset, OpenDatasetExporter
from .gee_stac import GEEToSTACConverter, export_gee_to_stac

__all__ = [
    "GEEOperationEngine",
    "ProductionSTACEngine",
    "ProductionOvertureEngine",
    "compute_building_zonal_stats",
    "SpectralIndexCalculator",
    "compute_ndvi",
    "compute_ndwi",
    "ExecutiveReportEngine",
    "PolicyReportGenerator",
    "generate_policy_report",
    "partition_state_bbox",
    "ZeroAuthSTACReader",
    "search_stac_anonymously",
    "export_open_dataset",
    "OpenDatasetExporter",
    "GEEToSTACConverter",
    "export_gee_to_stac",
]
