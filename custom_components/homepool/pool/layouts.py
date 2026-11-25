"""Pool layout catalog loader.

Pure Python module, no Home Assistant dependencies.
Loads and validates the layouts.yaml catalog.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_LOGGER = logging.getLogger(__name__)

DEFAULT_LAYOUTS_PATH = Path(__file__).parent.parent / "data" / "layouts.yaml"


@dataclass
class LayoutVariant:
    """A single layout variant for a pool shape."""

    id: str
    name: str
    requires_orientation: str | bool  # false, "corner", "short_side", "long_side", "any_side"
    volume_adjustment: float = 1.0
    svg_template: str | None = None


@dataclass
class LayoutCatalog:
    """Complete layout catalog organized by pool shape."""

    layouts: dict[str, list[LayoutVariant]] = field(default_factory=dict)

    def get_variants_for_shape(self, shape: str) -> list[LayoutVariant]:
        """Get all layout variants for a given pool shape."""
        return self.layouts.get(shape, [self._default_plain()])

    def get_variant(self, shape: str, variant_id: str) -> LayoutVariant:
        """Get a specific variant, falling back to 'plain' if not found."""
        variants = self.get_variants_for_shape(shape)
        for v in variants:
            if v.id == variant_id:
                return v
        _LOGGER.warning(
            "Layout variant '%s' not found for shape '%s'; using 'plain'",
            variant_id, shape,
        )
        return self._default_plain()

    @staticmethod
    def _default_plain() -> LayoutVariant:
        return LayoutVariant(
            id="plain",
            name="No interior elements",
            requires_orientation=False,
            volume_adjustment=1.0,
        )


def load_catalog(path: Path | None = None) -> LayoutCatalog:
    """Load the layout catalog from YAML.

    Falls back to a minimal catalog with only 'plain' layout
    if the file is missing or invalid.
    """
    catalog_path = path or DEFAULT_LAYOUTS_PATH
    catalog = LayoutCatalog()

    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            _LOGGER.warning("layouts.yaml root is not a dict; using defaults")
            return catalog

        for shape, variants_raw in raw.items():
            if not isinstance(variants_raw, list):
                continue
            variants: list[LayoutVariant] = []
            for v in variants_raw:
                if not isinstance(v, dict) or "id" not in v:
                    continue
                variants.append(LayoutVariant(
                    id=v["id"],
                    name=v.get("name", v["id"]),
                    requires_orientation=v.get("requires_orientation", False),
                    volume_adjustment=float(v.get("volume_adjustment", 1.0)),
                    svg_template=v.get("svg_template"),
                ))
            if variants:
                catalog.layouts[shape] = variants

    except FileNotFoundError:
        _LOGGER.warning("layouts.yaml not found at %s; using defaults", catalog_path)
    except (yaml.YAMLError, ValueError) as exc:
        _LOGGER.warning("Error loading layouts.yaml: %s; using defaults", exc)

    return catalog


def get_orientation_options(requires_orientation: str | bool) -> list[str]:
    """Return the list of orientation options for a layout variant."""
    if requires_orientation is False or requires_orientation == "false":
        return []
    mapping = {
        "corner": ["top_left", "top_right", "bottom_left", "bottom_right"],
        "short_side": ["top", "bottom"],
        "long_side": ["left", "right"],
        "any_side": ["top", "right", "bottom", "left"],
    }
    return mapping.get(str(requires_orientation), [])
