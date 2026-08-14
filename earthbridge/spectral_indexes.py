"""
Spectral Index Calculator Module
=================================
Fast, memory-efficient calculation of satellite spectral indices for Sentinel-2, Landsat, MODIS, and local GeoTIFFs.
Supports NumPy arrays, GeoPandas DataFrames, Xarray DataArrays, and GEE Expressions.
"""

from typing import Union, Dict, Any, Optional
import numpy as np

class SpectralIndexCalculator:
    """Calculates standardized satellite spectral indices on 16GB-RAM friendly arrays."""

    @staticmethod
    def ndvi(nir: np.ndarray, red: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """
        Normalized Difference Vegetation Index (NDVI)
        NDVI = (NIR - Red) / (NIR + Red)
        """
        nir = np.asarray(nir, dtype=np.float32)
        red = np.asarray(red, dtype=np.float32)
        denom = nir + red
        denom = np.where(denom == 0, eps, denom)
        return (nir - red) / denom

    @staticmethod
    def ndwi(green: np.ndarray, nir: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """
        Normalized Difference Water Index (NDWI)
        NDWI = (Green - NIR) / (Green + NIR)
        """
        green = np.asarray(green, dtype=np.float32)
        nir = np.asarray(nir, dtype=np.float32)
        denom = green + nir
        denom = np.where(denom == 0, eps, denom)
        return (green - nir) / denom

    @staticmethod
    def lswi(nir: np.ndarray, swir: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """
        Land Surface Water Index (LSWI)
        LSWI = (NIR - SWIR) / (NIR + SWIR)
        """
        nir = np.asarray(nir, dtype=np.float32)
        swir = np.asarray(swir, dtype=np.float32)
        denom = nir + swir
        denom = np.where(denom == 0, eps, denom)
        return (nir - swir) / denom

    @staticmethod
    def nbr(nir: np.ndarray, swir2: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """
        Normalized Burn Ratio (NBR)
        NBR = (NIR - SWIR2) / (NIR + SWIR2)
        """
        nir = np.asarray(nir, dtype=np.float32)
        swir2 = np.asarray(swir2, dtype=np.float32)
        denom = nir + swir2
        denom = np.where(denom == 0, eps, denom)
        return (nir - swir2) / denom

    @staticmethod
    def ndbi(swir: np.ndarray, nir: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """
        Normalized Difference Built-up Index (NDBI)
        NDBI = (SWIR - NIR) / (SWIR + NIR)
        """
        swir = np.asarray(swir, dtype=np.float32)
        nir = np.asarray(nir, dtype=np.float32)
        denom = swir + nir
        denom = np.where(denom == 0, eps, denom)
        return (swir - nir) / denom

    @staticmethod
    def lst_anomaly(lst_observed: np.ndarray, lst_climatology_mean: np.ndarray) -> np.ndarray:
        """
        Land Surface Temperature (LST) Anomaly Deviation
        Deviation = Observed LST - Historical Mean LST
        """
        lst_obs = np.asarray(lst_observed, dtype=np.float32)
        lst_mean = np.asarray(lst_climatology_mean, dtype=np.float32)
        return lst_obs - lst_mean

# High-level convenient wrappers
def compute_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    return SpectralIndexCalculator.ndvi(nir, red)

def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return SpectralIndexCalculator.ndwi(green, nir)

def compute_lswi(nir: np.ndarray, swir: np.ndarray) -> np.ndarray:
    return SpectralIndexCalculator.lswi(nir, swir)

def compute_nbr(nir: np.ndarray, swir2: np.ndarray) -> np.ndarray:
    return SpectralIndexCalculator.nbr(nir, swir2)

def compute_ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return SpectralIndexCalculator.ndbi(swir, nir)
