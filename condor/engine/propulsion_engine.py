"""Forças, momentos, energia, arrasto e falhas de fontes abstratas."""

from __future__ import annotations

import math
from typing import Any

from .contracts import evidence
from .vector import Vector, add, as_dict, cross, from_dict, magnitude, scale, sub, thrust_direction, weighted_center


def _curve_value(curve: list[dict[str, float]], command: float, key: str) -> float | None:
    if not curve:
        return None
    if command <= curve[0]["powerCommand"]:
        return curve[0][key]
    if command >= curve[-1]["powerCommand"]:
        return curve[-1][key]
    for left, right in zip(curve, curve[1:]):
        if left["powerCommand"] <= command <= right["powerCommand"]:
            span = right["powerCommand"] - left["powerCommand"]
            ratio = (command - left["powerCommand"]) / span if span else 0.0
            return left[key] + (right[key] - left[key]) * ratio
    return None


def _unit_state(unit: dict[str, Any], command_override: float | None = None) -> dict[str, Any]:
    command = command_override if command_override is not None else unit.get("powerCommand")
    active = unit["status"] == "ACTIVE" and command is not None and unit.get("maxThrust") is not None
    command = min(1.0, max(0.0, float(command or 0.0)))
    operational_limit = unit.get("operationalLimit")
    limit = min(1.0, float(operational_limit)) if operational_limit is not None else 1.0
    effective_command = min(command, limit)
    thrust = float(unit["maxThrust"]) * effective_command if active else 0.0
    direction = thrust_direction(unit["orientationPitch"], unit["orientationYaw"])
    force = scale(direction, thrust)
    watts = _curve_value(unit.get("energyConsumptionCurve", []), effective_command, "watts") if active else 0.0
    efficiency = _curve_value(unit.get("efficiencyCurve", []), effective_command, "efficiency") if active else None
    thermal = float(unit["thermalOutput"]) * effective_command if active and unit.get("thermalOutput") is not None else None
    return {
        "unitId": unit["id"], "command": command, "effectiveCommand": effective_command,
        "direction": as_dict(direction), "force": force, "thrust": thrust,
        "watts": watts, "efficiency": efficiency, "thermalOutput": thermal,
        "saturated": active and command >= limit - 1e-9,
        "status": unit["status"],
    }


class PropulsionEngine:
    @staticmethod
    def calculate(layout: dict[str, Any], mass_state: dict[str, Any], *, failed: set[str] | None = None,
                  commands: dict[str, float] | None = None) -> dict[str, Any]:
        failed = failed or set()
        commands = commands or {}
        cg_dict = mass_state.get("vehicleCg")
        cg = from_dict(cg_dict) if cg_dict else (0.0, 0.0, 0.0)
        total_force: Vector = (0.0, 0.0, 0.0)
        total_moment: Vector = (0.0, 0.0, 0.0)
        unit_states: list[dict[str, Any]] = []
        thrust_points: list[tuple[float, Vector]] = []
        total_energy_watts = 0.0
        energy_complete = True
        total_thermal = 0.0
        thermal_complete = True
        total_drag_area = 0.0
        drag_complete = True

        for unit in layout["units"]:
            if unit["id"] in failed:
                state = _unit_state({**unit, "status": "FAILED"}, 0.0)
            else:
                state = _unit_state(unit, commands.get(unit["id"]))
            position = (unit["positionX"], unit["positionY"], unit["positionZ"])
            moment = cross(sub(position, cg), state["force"])
            state["forceVector"] = as_dict(state.pop("force"))
            state["momentVector"] = as_dict(moment)
            state["position"] = as_dict(position)
            total_force = add(total_force, from_dict(state["forceVector"]))
            total_moment = add(total_moment, moment)
            if state["thrust"] > 0:
                thrust_points.append((state["thrust"], position))
            if state["watts"] is None:
                energy_complete = False
            else:
                total_energy_watts += float(state["watts"])
            if state["thermalOutput"] is None:
                thermal_complete = False
            else:
                total_thermal += float(state["thermalOutput"])
            if unit.get("frontalArea") is None or unit.get("dragCoefficient") is None:
                drag_complete = False
            else:
                total_drag_area += float(unit["frontalArea"]) * float(unit["dragCoefficient"])
            unit_states.append(state)

        center_of_thrust = weighted_center(thrust_points)
        cg_offset = sub(center_of_thrust, cg) if center_of_thrust is not None and cg_dict else None
        total_mass = mass_state.get("totalMass")
        weight = float(total_mass) * 9.80665 if total_mass is not None else None
        thrust_to_weight = magnitude(total_force) / weight if weight and weight > 0 else None
        return {
            "totalThrust": round(magnitude(total_force), 6),
            "totalForce": as_dict(total_force),
            "totalMoment": as_dict(total_moment),
            "centerOfThrust": as_dict(center_of_thrust),
            "cgOffset": as_dict(cg_offset),
            "cgOffsetDistance": round(magnitude(cg_offset), 6) if cg_offset is not None else None,
            "thrustCgMisalignment": bool(cg_offset is not None and magnitude(cg_offset) > 0.05),
            "thrustToWeight": round(thrust_to_weight, 6) if thrust_to_weight is not None else None,
            "totalEnergyDemandWatts": round(total_energy_watts, 6) if energy_complete else None,
            "totalThermalOutputWatts": round(total_thermal, 6) if thermal_complete else None,
            "propulsionDragArea": round(total_drag_area, 8) if drag_complete else None,
            "unitStates": unit_states,
            "saturation": [item["unitId"] for item in unit_states if item["saturated"]],
            "evidence": evidence(
                "Vector sum of axial abstract thrust sources; moment is r cross F about calculated CG",
                ["X=right, Y=up, Z=forward", "Steady command snapshot", "No internal propulsion hardware model"],
                "MEDIUM" if cg_dict and all(unit.get("maxThrust") is not None for unit in layout["units"]) else "LOW",
            ),
        }

    @staticmethod
    def installation_drag(layout: dict[str, Any], propulsion: dict[str, Any]) -> dict[str, Any]:
        vehicle = layout["vehicle"]
        density = vehicle.get("airDensity")
        speed = vehicle.get("cruiseSpeed")
        drag_area = propulsion.get("propulsionDragArea")
        drag = 0.5 * density * speed * speed * drag_area if None not in (density, speed, drag_area) else None
        return {
            "installationDragNewtons": round(drag, 6) if drag is not None else None,
            "equivalentDragArea": drag_area,
            "evidence": evidence(
                "D = 0.5 * rho * V^2 * sum(Cd * frontal area)",
                ["No CFD interaction correction", "Each installation coefficient must be supplied"],
                "LOW",
            ),
        }


def symmetry_analysis(layout: dict[str, Any]) -> dict[str, Any]:
    left = [unit for unit in layout["units"] if unit["positionX"] < -1e-6]
    right = [unit for unit in layout["units"] if unit["positionX"] > 1e-6]
    left_mass = sum(unit.get("mass") or 0.0 for unit in left)
    right_mass = sum(unit.get("mass") or 0.0 for unit in right)
    left_thrust = sum(unit.get("maxThrust") or 0.0 for unit in left)
    right_thrust = sum(unit.get("maxThrust") or 0.0 for unit in right)
    mass_base = max(left_mass, right_mass, 1e-9)
    thrust_base = max(left_thrust, right_thrust, 1e-9)
    position_left = sum(abs(unit["positionX"]) for unit in left) / len(left) if left else 0.0
    position_right = sum(abs(unit["positionX"]) for unit in right) / len(right) if right else 0.0
    position_base = max(position_left, position_right, 1e-9)
    errors = [abs(left_mass - right_mass) / mass_base, abs(left_thrust - right_thrust) / thrust_base,
              abs(position_left - position_right) / position_base]
    error = min(100.0, sum(errors) / len(errors) * 100.0)
    return {
        "leftMass": round(left_mass, 6), "rightMass": round(right_mass, 6),
        "leftMaxThrust": round(left_thrust, 6), "rightMaxThrust": round(right_thrust, 6),
        "symmetryErrorPercent": round(error, 3), "asymmetry": error > 1.0,
        "requiredControlCorrection": "CALCULATED_IN_CONTROL_MATRIX" if error > 1.0 else "NONE",
        "energyPenalty": "MODEL_REQUIRES_CONTROL_DEMAND" if error > 1.0 else 0.0,
        "stabilityPenalty": round(error, 3),
        "note": "Symmetry is measured, not required; compensating authority is evaluated separately.",
    }
