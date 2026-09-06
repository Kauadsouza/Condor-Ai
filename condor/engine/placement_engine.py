"""Avaliação geométrica, térmica e de placement do Condor X."""

from __future__ import annotations

import copy
import math
from typing import Any

from .contracts import CANDIDATE_ZONES, evidence
from .vector import cross, magnitude, sub, thrust_direction


PILOT_VOLUMES = {
    "HEAD": ((0.0, 1.52, 0.0), 0.18),
    "NECK": ((0.0, 1.30, 0.0), 0.11),
    "SPINE": ((0.0, 0.87, -0.08), 0.17),
    "CHEST": ((0.0, 0.93, 0.0), 0.28),
    "BACK": ((0.0, 0.93, -0.14), 0.24),
    "LEFT_ARM": ((-0.38, 0.72, 0.0), 0.18),
    "RIGHT_ARM": ((0.38, 0.72, 0.0), 0.18),
    "LEFT_LEG": ((-0.16, -0.34, 0.0), 0.22),
    "RIGHT_LEG": ((0.16, -0.34, 0.0), 0.22),
}

WING_VOLUMES = {
    "LEFT_WING": ((-0.78, 1.00, -0.12), 0.40),
    "RIGHT_WING": ((0.78, 1.00, -0.12), 0.40),
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _position(unit: dict[str, Any]) -> tuple[float, float, float]:
    return unit["positionX"], unit["positionY"], unit["positionZ"]


def _minimum_clearance(position: tuple[float, float, float], volumes: dict[str, tuple[tuple[float, float, float], float]]) -> tuple[str, float]:
    nearest = min(
        ((name, magnitude(sub(position, center)) - radius) for name, (center, radius) in volumes.items()),
        key=lambda item: item[1],
    )
    return nearest


def _aabb(unit: dict[str, Any], service: bool = False) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    envelope = unit["serviceEnvelope" if service else "installationEnvelope"]
    values = [envelope.get(axis) for axis in ("width", "height", "length")]
    if any(value is None for value in values):
        return None
    px, py, pz = _position(unit)
    hx, hy, hz = (float(value) / 2.0 for value in values)
    return (px - hx, py - hy, pz - hz), (px + hx, py + hy, pz + hz)


def _overlap(a, b) -> bool:
    return all(a[0][index] <= b[1][index] and a[1][index] >= b[0][index] for index in range(3))


class PlacementEngine:
    @staticmethod
    def unit_metrics(unit: dict[str, Any], layout: dict[str, Any], cg: tuple[float, float, float]) -> dict[str, Any]:
        position = _position(unit)
        distance_cg = magnitude(sub(position, cg))
        nearest_pilot, pilot_clearance = _minimum_clearance(position, PILOT_VOLUMES)
        nearest_wing, wing_clearance = _minimum_clearance(position, WING_VOLUMES)
        thermal_radius = unit.get("thermalRadiusEstimate")
        thermal_clearance = pilot_clearance - float(thermal_radius) if thermal_radius is not None else None
        direction = thrust_direction(unit["orientationPitch"], unit["orientationYaw"])
        lever = magnitude(cross(sub(position, cg), direction))
        dry_mass = layout["vehicle"].get("dryMass")

        scores: dict[str, float | None] = {
            "CG_COMPATIBILITY": _clamp(100.0 - distance_cg * 55.0),
            "THRUST_LEVER_ARM": _clamp(35.0 + min(1.0, lever) * 55.0),
            "THERMAL_SAFETY": _clamp(50.0 + thermal_clearance * 125.0) if thermal_clearance is not None else None,
            "PILOT_EXPOSURE": _clamp(50.0 + pilot_clearance * 110.0),
            "AERODYNAMIC_INTERFERENCE": _clamp(50.0 + min(pilot_clearance, wing_clearance) * 80.0) if unit.get("frontalArea") is not None and unit.get("dragCoefficient") is not None else None,
            "STRUCTURAL_SUPPORT": unit.get("structuralSupportScore"),
            "CONTROL_AUTHORITY": _clamp(lever * 100.0),
            "REDUNDANCY_VALUE": 80.0 if unit["redundancyGroup"] != "unassigned" else 30.0,
            "MASS_PENALTY": _clamp(100.0 - float(unit["mass"]) / float(dry_mass) * 500.0) if unit.get("mass") is not None and dry_mass else None,
            "FAILURE_CONSEQUENCE": None,
            "MAINTENANCE_ACCESS": unit.get("maintenanceAccessScore"),
            "WING_INTERFERENCE": _clamp(50.0 + wing_clearance * 100.0),
            "BODY_INTERFERENCE": _clamp(50.0 + pilot_clearance * 100.0),
        }
        available = [float(value) for value in scores.values() if value is not None]
        critical_ready = all(scores[key] is not None for key in ("THERMAL_SAFETY", "PILOT_EXPOSURE", "MASS_PENALTY"))
        placement_score = sum(available) / len(available) if available and critical_ready else None
        if placement_score is None:
            grade = "NOT_EVALUATED"
        elif thermal_clearance is not None and thermal_clearance < 0:
            grade = "REJECTED"
            placement_score = min(placement_score, 24.0)
        elif placement_score >= 75:
            grade = "FAVORABLE"
        elif placement_score >= 55:
            grade = "COMPROMISES"
        elif placement_score >= 35:
            grade = "HIGH_RISK"
        else:
            grade = "REJECTED"
        reasons = []
        ranked = sorted(((key, value) for key, value in scores.items() if value is not None), key=lambda item: item[1])
        reasons.extend(f"poor {key.lower().replace('_', ' ')}" for key, value in ranked[:2] if value < 50)
        reasons.extend(f"good {key.lower().replace('_', ' ')}" for key, value in reversed(ranked[-2:]) if value >= 70)
        return {
            "unitId": unit["id"], "mountZone": unit["mountZone"],
            "placementScore": round(placement_score, 3) if placement_score is not None else None,
            "grade": grade, "components": {key: round(value, 3) if value is not None else None for key, value in scores.items()},
            "distanceFromCg": round(distance_cg, 6), "thrustLeverArm": round(lever, 6),
            "nearestPilotZone": nearest_pilot, "pilotClearance": round(pilot_clearance, 6),
            "nearestWingZone": nearest_wing, "wingClearance": round(wing_clearance, 6),
            "thermalClearance": round(thermal_clearance, 6) if thermal_clearance is not None else None,
            "explainability": reasons or ["DATA REQUIRED for a complete placement score"],
        }

    @staticmethod
    def evaluate(layout: dict[str, Any], mass_state: dict[str, Any]) -> dict[str, Any]:
        cg_dict = mass_state.get("vehicleCg") or {"x": 0.0, "y": 0.0, "z": 0.0}
        cg = (cg_dict["x"], cg_dict["y"], cg_dict["z"])
        metrics = [PlacementEngine.unit_metrics(unit, layout, cg) for unit in layout["units"]]
        collisions = []
        for index, unit in enumerate(layout["units"]):
            box = _aabb(unit)
            if box is None:
                continue
            for other in layout["units"][index + 1:]:
                other_box = _aabb(other)
                if other_box is not None and _overlap(box, other_box):
                    collisions.append({"type": "GEOMETRY_CONFLICT", "a": unit["id"], "b": other["id"]})
        rejected = [item for item in metrics if item["grade"] == "REJECTED"]
        return {
            "units": metrics,
            "geometryConflicts": collisions,
            "rejectedUnits": [item["unitId"] for item in rejected],
            "evidence": evidence(
                "Distance, point-mass, abstract envelope and thrust-lever heuristics in the digital reference frame",
                ["Candidate zones are simulation areas", "Pilot and wing volumes are non-certified abstract references", "No mounting design"],
                "LOW",
            ),
        }

    @staticmethod
    def candidate_zones(layout: dict[str, Any], mass_state: dict[str, Any], selected_unit_id: str | None) -> list[dict[str, Any]]:
        selected = next((unit for unit in layout["units"] if unit["id"] == selected_unit_id), None)
        if selected is None:
            return [copy.deepcopy(zone) for zone in CANDIDATE_ZONES.values()]
        result = []
        for zone in CANDIDATE_ZONES.values():
            moved_layout = copy.deepcopy(layout)
            moved = next(unit for unit in moved_layout["units"] if unit["id"] == selected_unit_id)
            moved.update({
                "positionX": zone["position"]["x"], "positionY": zone["position"]["y"],
                "positionZ": zone["position"]["z"], "mountZone": zone["id"],
            })
            # A candidata desloca a massa antes de receber score; o CG usado
            # nunca é o do layout anterior.
            from .inertia_engine import InertiaEngine
            moved_mass = InertiaEngine.calculate(moved_layout)
            cg_dict = moved_mass.get("vehicleCg") or {"x": 0.0, "y": 0.0, "z": 0.0}
            metric = PlacementEngine.unit_metrics(moved, moved_layout, (cg_dict["x"], cg_dict["y"], cg_dict["z"]))
            result.append({**copy.deepcopy(zone), "status": metric["grade"], "placementScore": metric["placementScore"], "explainability": metric["explainability"]})
        return result

    @staticmethod
    def thermal(layout: dict[str, Any]) -> dict[str, Any]:
        pilot_zones = {name: {"riskIndex": 0.0, "contributors": []} for name in PILOT_VOLUMES}
        intersections = []
        unit_rows = []
        total_heat = 0.0
        complete = True
        energy_zone = layout["vehicle"].get("energyStorageZone", {})
        energy_ready = all(energy_zone.get(key) is not None for key in ("x", "y", "z", "radius"))
        energy_center = (energy_zone.get("x") or 0.0, energy_zone.get("y") or 0.0, energy_zone.get("z") or 0.0)
        energy_separations = []
        for unit in layout["units"]:
            heat = unit.get("thermalOutput")
            radius = unit.get("thermalRadiusEstimate")
            command = unit.get("powerCommand")
            if None in (heat, radius, command):
                complete = False
                unit_rows.append({"unitId": unit["id"], "status": "DATA_REQUIRED"})
                continue
            effective_heat = float(heat) * float(command)
            total_heat += effective_heat
            nearest_name, clearance = _minimum_clearance(_position(unit), PILOT_VOLUMES)
            thermal_clearance = clearance - float(radius)
            if thermal_clearance < 0:
                intersections.append({"type": "PILOT_SURVIVAL_VOLUME_INTERSECTION", "unitId": unit["id"], "pilotZone": nearest_name})
            _, wing_clearance = _minimum_clearance(_position(unit), WING_VOLUMES)
            if wing_clearance - float(radius) < 0:
                intersections.append({"type": "WING_STRUCTURE_INTERSECTION", "unitId": unit["id"]})
            if energy_ready:
                energy_clearance = magnitude(sub(_position(unit), energy_center)) - float(energy_zone["radius"]) - float(radius)
                energy_separations.append(energy_clearance)
                if energy_clearance < 0:
                    intersections.append({"type": "ENERGY_STORAGE_INTERSECTION", "unitId": unit["id"]})
            for name, (center, body_radius) in PILOT_VOLUMES.items():
                distance = max(0.01, magnitude(sub(_position(unit), center)) - body_radius)
                risk = effective_heat / (distance * distance) if effective_heat > 0 else 0.0
                pilot_zones[name]["riskIndex"] += risk
                pilot_zones[name]["contributors"].append({"unitId": unit["id"], "relativeHeatFluxIndex": round(risk, 6)})
            timeline = []
            resistance = unit.get("thermalResistance")
            time_constant = unit.get("thermalTimeConstant")
            cooling = unit.get("coolingEffectiveness")
            for minutes in (0, 10, 30, 60, 90, 120):
                delta = None
                if None not in (resistance, time_constant, cooling) and float(time_constant) > 0:
                    steady = effective_heat * float(resistance) * (1.0 - float(cooling))
                    delta = steady * (1.0 - math.exp(-(minutes * 60.0) / float(time_constant)))
                timeline.append({"minutes": minutes, "temperatureRiseEstimate": round(delta, 6) if delta is not None else None,
                                 "accumulatedHeatWh": round(effective_heat * minutes / 60.0, 6)})
            unit_rows.append({
                "unitId": unit["id"], "thermalPower": round(effective_heat, 6),
                "thermalRadiusEstimate": radius, "nearestPilotZone": nearest_name,
                "thermalClearance": round(thermal_clearance, 6), "timeline": timeline,
                "thermalSoakRisk": "REQUIRES_THERMAL_PROPERTIES" if resistance is None or time_constant is None else ("HIGH" if thermal_clearance < 0 else "MODELED"),
            })
        for value in pilot_zones.values():
            value["riskIndex"] = round(value["riskIndex"], 6)
            value["contributors"].sort(key=lambda item: item["relativeHeatFluxIndex"], reverse=True)
        minimum_energy_separation = min(energy_separations) if energy_separations else None
        pilot_intersection = any(item["type"] == "PILOT_SURVIVAL_VOLUME_INTERSECTION" for item in intersections)
        return {
            "totalThermalOutputWatts": round(total_heat, 6) if complete else None,
            "units": unit_rows, "pilotCoreEnvironment": pilot_zones,
            "intersections": intersections,
            "energyStorageSeparation": {
                "thermalSeparationScore": _clamp(50.0 + minimum_energy_separation * 100.0) if minimum_energy_separation is not None else None,
                "impactCouplingScore": _clamp(50.0 + minimum_energy_separation * 70.0) if minimum_energy_separation is not None else None,
                "systemConcentrationScore": _clamp(50.0 + minimum_energy_separation * 55.0) if minimum_energy_separation is not None else None,
                "minimumClearance": round(minimum_energy_separation, 6) if minimum_energy_separation is not None else None,
            },
            "pilotNoHeatZoneStatus": "REJECTED" if pilot_intersection else ("DATA_REQUIRED" if not complete else "CLEAR_IN_ABSTRACT_MODEL"),
            "evidence": evidence(
                "Inverse-distance exposure index plus optional first-order lumped thermal response",
                ["Not CFD", "Not a burn model", "Temperature requires user-supplied resistance and time constant"],
                "LOW",
            ),
        }
