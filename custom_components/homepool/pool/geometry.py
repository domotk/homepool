"""Pool geometry calculations.

Pure Python module, no Home Assistant dependencies.
Calculates pool volume from shape and dimensions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PoolDimensions:
    """Dimensions of a pool, fields used depend on shape."""

    shape: str

    # Square
    side: float | None = None

    # Rectangular / Oval / Kidney
    length: float | None = None
    width: float | None = None

    # Round
    diameter: float | None = None

    # L-shape
    length_1: float | None = None
    width_1: float | None = None
    length_2: float | None = None
    width_2: float | None = None

    # Depth (always required)
    depth_min: float = 0.0
    depth_max: float = 0.0

    # Layout adjustment
    volume_adjustment: float = 1.0

    # Override
    volume_override: float | None = None


def calculate_average_depth(depth_min: float, depth_max: float) -> float:
    """Calculate average depth from min and max."""
    return (depth_min + depth_max) / 2.0


def calculate_surface_area(dims: PoolDimensions) -> float:
    """Calculate the surface area of the pool in m²."""
    shape = dims.shape

    if shape == "square":
        if dims.side is None:
            raise ValueError("Square pool requires 'side' dimension")
        return dims.side ** 2

    if shape == "rectangular":
        if dims.length is None or dims.width is None:
            raise ValueError("Rectangular pool requires 'length' and 'width'")
        return dims.length * dims.width

    if shape == "oval":
        if dims.length is None or dims.width is None:
            raise ValueError("Oval pool requires 'length' and 'width'")
        return math.pi * (dims.length / 2) * (dims.width / 2)

    if shape == "round":
        if dims.diameter is None:
            raise ValueError("Round pool requires 'diameter'")
        return math.pi * (dims.diameter / 2) ** 2

    if shape == "kidney":
        if dims.length is None or dims.width is None:
            raise ValueError("Kidney pool requires 'length' and 'width'")
        # Kidney shape approximation: ~85% of bounding rectangle
        return dims.length * dims.width * 0.85

    if shape == "l_shape":
        if any(
            v is None
            for v in [dims.length_1, dims.width_1, dims.length_2, dims.width_2]
        ):
            raise ValueError("L-shape pool requires length_1, width_1, length_2, width_2")
        return (dims.length_1 * dims.width_1) + (dims.length_2 * dims.width_2)

    raise ValueError(f"Unknown pool shape: {shape}")


def calculate_volume(dims: PoolDimensions) -> float:
    """Calculate pool volume in m³.

    If volume_override is set, returns that value directly.
    Otherwise calculates from geometry, depth, and layout adjustment.

    Returns:
        Volume in cubic meters, rounded to 1 decimal.
    """
    if dims.volume_override is not None and dims.volume_override > 0:
        return round(dims.volume_override, 1)

    surface = calculate_surface_area(dims)
    avg_depth = calculate_average_depth(dims.depth_min, dims.depth_max)
    volume = surface * avg_depth * dims.volume_adjustment

    return round(volume, 1)


def calculate_cycle_duration_minutes(
    volume_m3: float,
    flow_rate_m3h: float,
) -> int:
    """Calculate duration of one complete filtration cycle in minutes.

    Args:
        volume_m3: Pool volume in cubic meters.
        flow_rate_m3h: Pump nominal flow rate in m³/h.

    Returns:
        Duration in minutes for one complete turnover.
    """
    if flow_rate_m3h <= 0:
        raise ValueError("Flow rate must be positive")
    return round((volume_m3 / flow_rate_m3h) * 60)
