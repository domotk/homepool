"""Hardware catalogue loader (pumps, filters, salt chlorinators).

Pure Python. Reads ``data/catalog.yaml``; a missing or broken file gives an
empty catalogue, never an error, because the catalogue only pre-fills the
setup form and everything in it can be typed by hand.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

_LOGGER = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path(__file__).parent.parent / "data" / "catalog.yaml"
CATEGORIES = ("pumps", "filters", "salt_chlorinators")


def model_key(item: dict[str, Any]) -> str:
    """The identifier stored in the config entry: ``Brand Model``."""
    return f"{item.get('brand', '').strip()} {item.get('model', '').strip()}".strip()


def load_hardware(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Every category as a list of entries, each with a ``key``."""
    catalog: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    try:
        raw = yaml.safe_load((path or DEFAULT_CATALOG_PATH).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        _LOGGER.warning("Hardware catalogue unreadable (%s); continuing without it", err)
        return catalog
    if not isinstance(raw, dict):
        return catalog
    for category in CATEGORIES:
        for item in raw.get(category) or []:
            if isinstance(item, dict) and item.get("brand") and item.get("model"):
                catalog[category].append({**item, "key": model_key(item)})
    return catalog


def find(catalog: dict[str, list[dict[str, Any]]], category: str, key: str | None):
    """The entry with this key, or None."""
    if not key:
        return None
    for item in catalog.get(category, []):
        if item["key"] == key:
            return item
    return None
