"""Missão M01, transição, cruzeiro e energia do Propulsion Lab."""

from __future__ import annotations

from typing import Any

from .contracts import evidence
from .control_allocation_engine import ControlAllocationEngine
from .propulsion_engine import PropulsionEngine


class MissionEngine:
    @staticmethod
    def _aero(layout: dict[str, Any], mass_state: dict[str, Any], speed: float) -> dict[str, float | None]:
        vehicle = layout["vehicle"]
        density = vehicle.get("airDensity")
        wing_area = vehicle.get("wingArea")
        lift_coefficient = vehicle.get("liftCoefficient")
        body_drag_area = vehicle.get("bodyDragArea")
        if None in (density, wing_area, lift_coefficient, body_drag_area):
            return {"wingLift": None, "bodyDrag": None}
        dynamic = 0.5 * float(density) * speed * speed
        return {
            "wingLift": dynamic * float(wing_area) * float(lift_coefficient),
            "bodyDrag": dynamic * float(body_drag_area),
        }

    @staticmethod
    def _phase(layout: dict[str, Any], mass_state: dict[str, Any], name: str, duration: float,
               speed_factor: float, wing_factor: float) -> dict[str, Any]:
        weight = float(mass_state.get("totalMass") or 0.0) * 9.80665
        cruise_speed = layout["vehicle"].get("cruiseSpeed")
        speed = float(cruise_speed) * speed_factor if cruise_speed is not None else 0.0
        aero = MissionEngine._aero(layout, mass_state, speed)
        wing_lift = float(aero["wingLift"]) * wing_factor if aero["wingLift"] is not None else None
        vertical = max(0.0, weight - wing_lift) if wing_lift is not None and weight > 0 else (weight if name in {"TAKEOFF", "LANDING"} and weight > 0 else None)
        installation_drag_area = 0.0
        drag_complete = True
        for unit in layout["units"]:
            if unit.get("frontalArea") is None or unit.get("dragCoefficient") is None:
                drag_complete = False
                break
            installation_drag_area += float(unit["frontalArea"]) * float(unit["dragCoefficient"])
        propulsion_drag = None
        density = layout["vehicle"].get("airDensity")
        if drag_complete and density is not None:
            propulsion_drag = 0.5 * float(density) * speed * speed * installation_drag_area
        forward = float(aero["bodyDrag"]) + propulsion_drag if aero["bodyDrag"] is not None and propulsion_drag is not None else (0.0 if name in {"TAKEOFF", "LANDING"} else None)
        demand = {
            "LIFT": vertical or 0.0, "FORWARD": forward or 0.0,
            "ROLL": 0.0, "PITCH": 0.0, "YAW": 0.0,
        }
        allocation = ControlAllocationEngine.allocate(layout, mass_state, demand)
        state = PropulsionEngine.calculate(layout, mass_state, commands=allocation["commands"])
        watts = state.get("totalEnergyDemandWatts")
        energy = watts * duration / 3600.0 if watts is not None else None
        return {
            "name": name, "durationSeconds": duration, "speed": round(speed, 6),
            "vehicleWeight": round(weight, 6) if weight > 0 else None,
            "requiredVerticalForce": round(vertical, 6) if vertical is not None else None,
            "availableVerticalForce": allocation["achieved"]["LIFT"],
            "thrustMargin": round(allocation["achieved"]["LIFT"] - vertical, 6) if vertical is not None else None,
            "wingLift": round(wing_lift, 6) if wing_lift is not None else None,
            "requiredForwardForce": round(forward, 6) if forward is not None else None,
            "powerWatts": watts, "energyWh": round(energy, 6) if energy is not None else None,
            "thermalLoadWatts": state.get("totalThermalOutputWatts"),
            "allocation": allocation,
            "status": "CONTROL_AUTHORITY_INSUFFICIENT" if allocation["controlAuthorityInsufficient"] else "PASS",
        }

    @staticmethod
    def cruise_optimization(layout: dict[str, Any], mass_state: dict[str, Any]) -> dict[str, Any]:
        configured = layout["vehicle"].get("cruiseSpeed")
        if configured is None or configured <= 0 or mass_state.get("totalMass") is None:
            return {"minimumEnergyCruise": None, "maximumEnduranceCruise": None, "status": "DATA_REQUIRED"}
        candidates = []
        for step in range(11):
            speed = float(configured) * (0.5 + step * 0.1)
            aero = MissionEngine._aero(layout, mass_state, speed)
            if aero["wingLift"] is None or aero["bodyDrag"] is None:
                continue
            weight = float(mass_state["totalMass"]) * 9.80665
            vertical = max(0.0, weight - float(aero["wingLift"]))
            drag_area = 0.0
            if any(unit.get("frontalArea") is None or unit.get("dragCoefficient") is None for unit in layout["units"]):
                continue
            for unit in layout["units"]:
                drag_area += float(unit["frontalArea"]) * float(unit["dragCoefficient"])
            density = layout["vehicle"].get("airDensity")
            if density is None:
                continue
            forward = float(aero["bodyDrag"]) + 0.5 * float(density) * speed * speed * drag_area
            allocation = ControlAllocationEngine.allocate(layout, mass_state, {"LIFT": vertical, "FORWARD": forward, "ROLL": 0, "PITCH": 0, "YAW": 0})
            state = PropulsionEngine.calculate(layout, mass_state, commands=allocation["commands"])
            power = state.get("totalEnergyDemandWatts")
            if power is None or allocation["controlAuthorityInsufficient"]:
                continue
            candidates.append({"speed": speed, "powerWatts": power, "energyPerMeter": power / speed})
        if not candidates:
            return {"minimumEnergyCruise": None, "maximumEnduranceCruise": None, "status": "INSUFFICIENT_DATA_OR_AUTHORITY"}
        range_best = min(candidates, key=lambda item: item["energyPerMeter"])
        endurance_best = min(candidates, key=lambda item: item["powerWatts"])
        return {
            "minimumEnergyCruise": {key: round(value, 6) for key, value in range_best.items()},
            "maximumEnduranceCruise": {key: round(value, 6) for key, value in endurance_best.items()},
            "status": "MODELED",
            "note": "The two speeds may differ; this is a bounded search around the configured reference speed.",
        }

    @staticmethod
    def run(layout: dict[str, Any], mass_state: dict[str, Any]) -> dict[str, Any]:
        phase_defs = (
            ("TAKEOFF", 0.0, 0.0),
            ("TRANSITION", 0.55, 0.5),
            ("CRUISE", 1.0, 1.0),
            ("LANDING", 0.0, 0.0),
        )
        phases = []
        for name, speed_factor, wing_factor in phase_defs:
            duration = layout["mission"]["phases"].get(name)
            if duration is None:
                phases.append({"name": name, "status": "DATA_REQUIRED", "durationSeconds": None})
            else:
                phases.append(MissionEngine._phase(layout, mass_state, name, float(duration), speed_factor, wing_factor))
        energy_values = [phase.get("energyWh") for phase in phases]
        total_energy = sum(float(value) for value in energy_values if value is not None) if all(value is not None for value in energy_values) else None
        capacity = layout["vehicle"].get("energyCapacityWh")
        reserve_percent = layout["vehicle"].get("energyReservePercent")
        usable = float(capacity) * (1.0 - float(reserve_percent) / 100.0) if capacity is not None and reserve_percent is not None else None
        reserve = usable - total_energy if usable is not None and total_energy is not None else None
        transition = []
        transition_duration = layout["mission"]["phases"].get("TRANSITION")
        if transition_duration is not None and mass_state.get("totalMass") is not None:
            weight = float(mass_state["totalMass"]) * 9.80665
            for step in range(6):
                fraction = step / 5.0
                speed = float(layout["vehicle"].get("cruiseSpeed") or 0.0) * fraction
                aero = MissionEngine._aero(layout, mass_state, speed)
                wing = float(aero["wingLift"]) if aero["wingLift"] is not None else None
                transition.append({
                    "timeSeconds": round(float(transition_duration) * fraction, 3),
                    "verticalThrust": round(max(0.0, weight - wing), 6) if wing is not None else None,
                    "forwardThrust": round(float(aero["bodyDrag"]), 6) if aero["bodyDrag"] is not None else None,
                    "wingLift": round(wing, 6) if wing is not None else None,
                })
        status = "PASS"
        if any(phase.get("status") == "DATA_REQUIRED" for phase in phases) or total_energy is None or usable is None:
            status = "INSUFFICIENT_DATA"
        elif any(phase.get("status") != "PASS" for phase in phases) or reserve is None or reserve < 0:
            status = "FAIL"
        return {
            "missionId": "M01", "targetEnduranceSeconds": layout["mission"]["targetEnduranceSeconds"],
            "phases": phases, "transitionTimeline": transition,
            "totalEnergyWh": round(total_energy, 6) if total_energy is not None else None,
            "usableEnergyWh": round(usable, 6) if usable is not None else None,
            "energyReserveWh": round(reserve, 6) if reserve is not None else None,
            "status": status,
            "cruiseOptimization": MissionEngine.cruise_optimization(layout, mass_state),
            "evidence": evidence(
                "Static phase demands with simplified wing lift, drag and bounded control allocation",
                ["User-supplied phase durations", "No transient flight dynamics", "M01 target is 02:00:00"],
                "LOW",
            ),
        }
