"""Operações vetoriais pequenas, sem dependência numérica externa."""

from __future__ import annotations

import math
from typing import Iterable

Vector = tuple[float, float, float]


def add(a: Vector, b: Vector) -> Vector:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def sub(a: Vector, b: Vector) -> Vector:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def scale(a: Vector, factor: float) -> Vector:
    return a[0] * factor, a[1] * factor, a[2] * factor


def cross(a: Vector, b: Vector) -> Vector:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def magnitude(a: Vector) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vector) -> Vector:
    length = magnitude(a)
    return scale(a, 1.0 / length) if length > 1e-12 else (0.0, 0.0, 0.0)


def weighted_center(items: Iterable[tuple[float, Vector]]) -> Vector | None:
    total = 0.0
    result = (0.0, 0.0, 0.0)
    for weight, position in items:
        if weight <= 0:
            continue
        total += weight
        result = add(result, scale(position, weight))
    return scale(result, 1.0 / total) if total > 0 else None


def as_dict(value: Vector | None, digits: int = 6) -> dict[str, float] | None:
    if value is None:
        return None
    return {axis: round(number, digits) for axis, number in zip(("x", "y", "z"), value)}


def from_dict(value: dict) -> Vector:
    return float(value.get("x", 0.0)), float(value.get("y", 0.0)), float(value.get("z", 0.0))


def thrust_direction(pitch_degrees: float, yaw_degrees: float) -> Vector:
    """Direção axial a partir de +Y; roll não altera uma fonte axial."""
    pitch = math.radians(pitch_degrees)
    yaw = math.radians(yaw_degrees)
    return unit((math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch)))
