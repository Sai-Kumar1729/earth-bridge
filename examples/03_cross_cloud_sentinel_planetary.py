"""
Example 03: Cross-Cloud Query Harmonization (GEE & MS Planetary Computer)
========================================================================
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from earthbridge.planetary_sync import query_planetary_and_gee

def main():
    print("=== earth-bridge Example 03: GEE & Planetary Computer Dual Query ===")
    
    bbox = [78.400, 17.300, 78.500, 17.400]
    snippets = query_planetary_and_gee(
        collection="sentinel-2-l2a",
        bbox=bbox,
        start_date="2026-06-01",
        end_date="2026-08-01"
    )
    
    print("\n--- Google Earth Engine Code Snippet ---")
    print(snippets["gee_code"][:300] + "...\n")
    
    print("--- Microsoft Planetary Computer Code Snippet ---")
    print(snippets["planetary_code"][:300] + "...\n")

if __name__ == "__main__":
    main()
