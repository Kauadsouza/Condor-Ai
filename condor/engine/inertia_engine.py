"""Distribuição de massa e inércia aproximada do Condor X."""

from __future__ import annotations

from typing import Any

from .contracts import evidence
from .vector import Vector, as_dict, from_dict, magnitude, sub, weighted_center


class InertiaEngine:
    """Modelo de massa pontual L2.

    Não estima a inércia da estrutura seca sem geometria/matriz fornecida. Os
    valores Ixx/Iyy/Izz abaixo são a contribuição das unidades abstratas em
    relação ao CG total calculado.
    """

    @staticmethod
    def calculate(layout: dict[str, Any]) -> dict[str, Any]:
        vehicle = layout["vehicle"]
        dry_mass = vehicle.get("dryMass")
        dry_cg = from_dict(vehicle.get("dryCg", {}))
        units_complete = all(unit.get("mass") is not None for unit in layout["units"])
        dry_cg_complete = all(vehicle.get("dryCgProvided", {}).get(axis) for axis in ("x", "y", "z"))
        valid_units = [unit for unit in layout["units"] if unit.get("mass") is not None]
        propulsion_mass = sum(float(unit["mass"]) for unit in valid_units) if layout["units"] and units_complete else None
        propulsion_com = weighted_center(
            (float(unit["mass"]), (unit["positionX"], unit["positionY"], unit["positionZ"]))
            for unit in valid_units
        ) if units_complete else None
        cg_items: list[tuple[float, Vector]] = [
            (float(unit["mass"]), (unit["positionX"], unit["positionY"], unit["positionZ"]))
            for unit in valid_units
        ]
        if dry_mass is not None and dry_cg_complete and units_complete:
            cg_items.append((float(dry_mass), dry_cg))
        vehicle_cg = weighted_center(cg_items) if dry_mass is not None and dry_cg_complete and units_complete else None
        total_mass = float(dry_mass) + sum(float(unit["mass"]) for unit in valid_units) if dry_mass is not None and units_complete else None

        ixx = iyy = izz = 0.0
        contributions = []
        if vehicle_cg is not None:
            for unit in valid_units:
                mass = float(unit["mass"])
                relative = sub((unit["positionX"], unit["positionY"], unit["positionZ"]), vehicle_cg)
                dx, dy, dz = relative
                item = {
                    "unitId": unit["id"],
                    "distanceFromCg": round(magnitude(relative), 6),
                    "Ixx": round(mass * (dy * dy + dz * dz), 6),
                    "Iyy": round(mass * (dx * dx + dz * dz), 6),
                    "Izz": round(mass * (dx * dx + dy * dy), 6),
                }
                ixx += item["Ixx"]
                iyy += item["Iyy"]
                izz += item["Izz"]
                contributions.append(item)

        return {
            "dryMass": dry_mass,
            "propulsionMass": round(propulsion_mass, 6) if propulsion_mass is not None else None,
            "totalMass": round(total_mass, 6) if total_mass is not None else None,
            "vehicleCg": as_dict(vehicle_cg),
            "propulsionCom": as_dict(propulsion_com),
            "propulsionPointMassInertia": {
                "Ixx": round(ixx, 6), "Iyy": round(iyy, 6), "Izz": round(izz, 6),
                "unit": "kg*m^2",
                "scope": "PROPULSION_UNITS_ONLY",
            } if vehicle_cg is not None else None,
            "unitContributions": contributions,
            "massConcentrationMap": {
                "dryVehicle": {"mass": dry_mass, "center": as_dict(dry_cg) if dry_mass is not None else None},
                "propulsion": {"mass": round(propulsion_mass, 6) if propulsion_mass is not None else None, "center": as_dict(propulsion_com)},
                "pilot": "DATA_REQUIRED", "structure": "DATA_REQUIRED", "energy": "DATA_REQUIRED",
                "wings": "DATA_REQUIRED", "avionics": "DATA_REQUIRED", "thermalSystems": "DATA_REQUIRED",
            },
            "explanation": "Moving configured mass farther from the calculated CG increases its rotational inertia contribution.",
            "evidence": evidence(
                "Point-mass center of mass and parallel-axis inertia contribution",
                ["Unit dimensions are not used in inertia", "Dry-body inertia remains DATA REQUIRED"],
                "MEDIUM" if dry_mass is not None and len(valid_units) == len(layout["units"]) else "LOW",
            ),
        }
