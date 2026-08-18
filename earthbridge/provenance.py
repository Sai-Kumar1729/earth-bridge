"""
Provenance records for every result earth-bridge returns.

Every value this library produces comes from a specific sensor, scene, date and
provider, under a specific licence. Those facts travel with the result instead of
being discarded, so a caller can always answer "where did this number come from?"
and "am I allowed to redistribute it?".

This matters most where earth-bridge falls back between providers: a building
query may be answered by Overture or by OpenStreetMap, and those carry different
schemas and different licences. The fallback is allowed; hiding it is not.
"""

from typing import Any, Dict, List, Optional

# Attribution and licence per upstream provider. Keyed by the `backend` value
# used in Provenance records.
PROVIDER_LICENSES = {
    "earth-engine": {
        "attribution": "Google Earth Engine",
        "license": "Varies by dataset; see the Earth Engine Data Catalog entry",
        "url": "https://developers.google.com/earth-engine/datasets",
    },
    "planetary-computer": {
        "attribution": "Microsoft Planetary Computer",
        "license": "Varies by collection; most are open (CC-BY-4.0 or public domain)",
        "url": "https://planetarycomputer.microsoft.com/catalog",
    },
    "nasa-gibs": {
        "attribution": "NASA EOSDIS GIBS",
        "license": "Public domain (NASA open data policy)",
        "url": "https://nasa-gibs.github.io/gibs-api-docs/",
    },
    "overture": {
        "attribution": "Overture Maps Foundation",
        "license": "ODbL-1.0 / CDLA-Permissive-2.0 depending on source feature",
        "url": "https://docs.overturemaps.org/attribution/",
    },
    "openstreetmap": {
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL-1.0 (share-alike: derived databases must also be ODbL)",
        "url": "https://www.openstreetmap.org/copyright",
    },
}


class Provenance:
    """Where a result came from.

    Attributes:
        backend: Provider key, e.g. "earth-engine", "planetary-computer",
            "nasa-gibs", "overture", "openstreetmap".
        collection: Dataset or collection identifier, e.g. "MODIS/061/MOD44B".
        scene_id: Specific scene/item identifier when a single scene was used.
        datetime: Acquisition timestamp, or the compositing window.
        resolution: Native pixel size of the source, e.g. "250m".
        notes: Anything a caller needs to know to interpret the result
            correctly, including known limitations of how it was produced.
        requested: The parameters the caller asked for, so a result can be
            reproduced.
    """

    __slots__ = (
        "backend",
        "collection",
        "scene_id",
        "datetime",
        "resolution",
        "notes",
        "requested",
    )

    def __init__(
        self,
        backend: str,
        collection: Optional[str] = None,
        scene_id: Optional[str] = None,
        datetime: Optional[str] = None,
        resolution: Optional[str] = None,
        notes: Optional[List[str]] = None,
        requested: Optional[Dict[str, Any]] = None,
    ):
        self.backend = backend
        self.collection = collection
        self.scene_id = scene_id
        self.datetime = datetime
        self.resolution = resolution
        self.notes = list(notes) if notes else []
        self.requested = dict(requested) if requested else {}

    @property
    def attribution(self) -> str:
        return PROVIDER_LICENSES.get(self.backend, {}).get("attribution", self.backend)

    @property
    def license(self) -> str:
        return PROVIDER_LICENSES.get(self.backend, {}).get("license", "Unknown")

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "backend": self.backend,
            "collection": self.collection,
            "scene_id": self.scene_id,
            "datetime": self.datetime,
            "resolution": self.resolution,
            "attribution": self.attribution,
            "license": self.license,
            "license_url": PROVIDER_LICENSES.get(self.backend, {}).get("url"),
            "requested": self.requested,
        }
        if self.notes:
            out["notes"] = self.notes
        return out

    def __repr__(self) -> str:
        bits = [self.backend]
        if self.collection:
            bits.append(self.collection)
        if self.scene_id:
            bits.append(self.scene_id)
        return f"<Provenance {' | '.join(bits)}>"


def success(provenance: Provenance, **payload: Any) -> Dict[str, Any]:
    """Build a successful result carrying its provenance."""
    return {"status": "success", "provenance": provenance.to_dict(), **payload}


def unavailable(reason: str, remedy: Optional[str] = None, **payload: Any) -> Dict[str, Any]:
    """Build a result for work that could not be performed.

    Used where earth-bridge previously returned plausible-looking substitute
    values. A caller must be able to tell "no data" apart from "here is a
    number", so this never carries a numeric payload.
    """
    return {
        "status": "unavailable",
        "reason": reason,
        "remedy": remedy,
        "provenance": None,
        **payload,
    }
