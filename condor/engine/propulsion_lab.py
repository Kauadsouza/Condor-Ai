"""Orquestrador acoplado do Propulsion Placement Lab do Condor X."""

from __future__ import annotations

import copy
import itertools
from typing import Any

from .contracts import ANALYSIS_SCHEMA, CANDIDATE_ZONES, blank_layout, data_requirements, evidence, normalize_layout, normalize_unit
from .control_allocation_engine import ControlAllocationEngine
from .inertia_engine import InertiaEngine
from .mission_engine import MissionEngine
from .placement_engine import PlacementEngine
from .propulsion_engine import PropulsionEngine, symmetry_analysis


def _average(values) -> float | None:
    available = [float(value) for value in values if value is not None]
    return sum(available) / len(available) if available else None


class PropulsionLabEngine:
    """Recalcula todas as engines a cada alteração relevante."""

    def normalize(self, payload: Any) -> dict[str, Any]:
        return normalize_layout(payload)

    def blank(self, layout_id: str, name: str) -> dict[str, Any]:
        return blank_layout(layout_id, name)

    def analyze(self, payload: Any) -> dict[str, Any]:
        layout = normalize_layout(payload)
        missing = data_requirements(layout)
        mass = InertiaEngine.calculate(layout)
        propulsion = PropulsionEngine.calculate(layout, mass)
        drag = PropulsionEngine.installation_drag(layout, propulsion)
        symmetry = symmetry_analysis(layout)
        control = ControlAllocationEngine.authority(layout, mass)
        failures = ControlAllocationEngine.failures(layout, mass)
        placement = PlacementEngine.evaluate(layout, mass)
        thermal = PlacementEngine.thermal(layout)
        mission = MissionEngine.run(layout, mass)
        candidate_zones = PlacementEngine.candidate_zones(layout, mass, layout.get("selectedUnitId"))

        weight = (mass.get("totalMass") or 0.0) * 9.80665
        lift_capacity = control["positive"]["LIFT"]
        control_margin = min(100.0, lift_capacity / weight * 100.0) if weight > 0 else None
        placement_scores = [item["placementScore"] for item in placement["units"]]
        thermal_score = None if thermal["pilotNoHeatZoneStatus"] == "DATA_REQUIRED" else (0.0 if thermal["intersections"] else 100.0)
        landing_rows = [row.get("landingCapability") for row in failures["singleUnitFailure"] if row.get("landingCapability") is not None]
        landing_score = sum(100.0 if value else 0.0 for value in landing_rows) / len(landing_rows) if landing_rows else None
        safety_components = {
            "pilotHeatExposure": thermal_score,
            "failureAsymmetry": max(0.0, 100.0 - symmetry["symmetryErrorPercent"]),
            "structuralLoad": _average(item["components"].get("STRUCTURAL_SUPPORT") for item in placement["units"]),
            "energyProximity": thermal["energyStorageSeparation"]["thermalSeparationScore"],
            "controlMargin": control_margin,
            "redundancy": failures["propulsionRedundancyScore"],
            "landingSurvivability": landing_score,
        }
        safety_index = _average(safety_components.values())
        safety_critical_complete = safety_components["pilotHeatExposure"] is not None and safety_components["controlMargin"] is not None
        if not safety_critical_complete:
            safety_index = None

        rejection_reasons = []
        if placement["geometryConflicts"]:
            rejection_reasons.append("geometry collision")
        if thermal["intersections"]:
            rejection_reasons.append("pilot safety / thermal envelope violated")
        if weight > 0 and lift_capacity < weight:
            rejection_reasons.append("control authority insufficient for configured weight")
        if layout["vehicle"].get("cgEnvelopeRadius") is not None and mass.get("vehicleCg"):
            cg = mass["vehicleCg"]
            if (cg["x"] ** 2 + cg["y"] ** 2 + cg["z"] ** 2) ** 0.5 > float(layout["vehicle"]["cgEnvelopeRadius"]):
                rejection_reasons.append("CG outside configured envelope")
        if mission["status"] == "FAIL":
            rejection_reasons.append("M01 energy or phase requirement impossible")
        if failures["singleUnitFailure"] and all(row["classification"] in {"CRITICAL", "UNRECOVERABLE"} for row in failures["singleUnitFailure"]):
            rejection_reasons.append("unacceptable single-unit failure behavior")

        if missing:
            decision = "INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT"
        elif rejection_reasons:
            decision = "REJECTED"
        else:
            decision = "CANDIDATE_FOR_FURTHER_SIMULATION"

        unit_values = self._unit_values(layout, propulsion, control, placement)
        questions = self._questions(layout, mass, propulsion, drag, thermal, failures, unit_values)
        architecture_studies = self._architecture_studies(layout, placement)
        minimum_viable = self._minimum_viable(layout, unit_values)
        force_complete = bool(layout["units"]) and all(
            unit["status"] != "ACTIVE" or (unit.get("maxThrust") is not None and unit.get("powerCommand") is not None)
            for unit in layout["units"]
        )
        moment_complete = force_complete and mass.get("vehicleCg") is not None
        return {
            "schema": ANALYSIS_SCHEMA,
            "layout": layout,
            "decision": decision,
            "missingData": missing,
            "rejection": {
                "primary": rejection_reasons[0] if rejection_reasons else None,
                "secondary": rejection_reasons[1] if len(rejection_reasons) > 1 else None,
                "tertiary": rejection_reasons[2] if len(rejection_reasons) > 2 else None,
                "all": rejection_reasons,
            },
            "massEngine": mass,
            "inertiaEngine": mass.get("propulsionPointMassInertia"),
            "propulsionEngine": propulsion,
            "aeroEngine": drag,
            "stabilityEngine": {"symmetry": symmetry, "thrustCgMisalignment": propulsion["thrustCgMisalignment"]},
            "controlAllocationEngine": control,
            "placementEngine": placement,
            "thermalEngine": thermal,
            "energyEngine": {"instantaneousDemandWatts": propulsion["totalEnergyDemandWatts"], "missionEnergyWh": mission["totalEnergyWh"]},
            "missionEngine": mission,
            "failureEngine": failures,
            "safetyEngine": {
                "propulsionSafetyIndex": round(safety_index, 3) if safety_index is not None else None,
                "components": {key: round(value, 3) if value is not None else None for key, value in safety_components.items()},
                "priorityOrder": ["HUMAN_SAFETY", "CONTROLLABILITY", "FAILURE_SURVIVABILITY", "STRUCTURAL_INTEGRITY", "THERMAL_SAFETY", "AERODYNAMIC_EFFICIENCY", "ENDURANCE", "SPEED"],
            },
            "candidateZones": candidate_zones,
            "architectureStudies": architecture_studies,
            "unitValueScores": unit_values,
            "minimumViablePropulsion": minimum_viable,
            "designQuestions": questions,
            "dashboard": {
                "unitsActive": sum(unit["status"] == "ACTIVE" for unit in layout["units"]),
                "totalThrust": propulsion["totalThrust"] if force_complete else None,
                "verticalComponent": propulsion["totalForce"]["y"] if force_complete else None,
                "forwardComponent": propulsion["totalForce"]["z"] if force_complete else None,
                "thrustWeight": propulsion["thrustToWeight"],
                "centerOfThrust": propulsion["centerOfThrust"],
                "cgOffset": propulsion["cgOffset"],
                "rollMoment": propulsion["totalMoment"]["z"] if moment_complete else None,
                "pitchMoment": propulsion["totalMoment"]["x"] if moment_complete else None,
                "yawMoment": propulsion["totalMoment"]["y"] if moment_complete else None,
                "totalPropulsionMass": mass["propulsionMass"],
                "totalPropulsionEnergyWatts": propulsion["totalEnergyDemandWatts"] if layout["units"] else None,
                "totalThermalOutputWatts": propulsion["totalThermalOutputWatts"] if layout["units"] else None,
                "propulsionDragNewtons": drag["installationDragNewtons"],
                "redundancyScore": failures["propulsionRedundancyScore"],
                "safetyIndex": round(safety_index, 3) if safety_index is not None else None,
            },
            "evidenceChain": evidence(
                "Coupled recalculation: mass -> CG -> inertia -> thrust/moments -> placement/thermal/aero -> control/failure -> mission/safety",
                ["Abstract propulsion only", "Configured inputs remain authoritative", "No CFD, FEA or experimental validation"],
                "LOW",
            ),
        }

    @staticmethod
    def _architecture_studies(layout, placement):
        families = {
            "DORSAL_ARCHITECTURE": {"zones": {"dorsal"}, "benefits": ["central-axis proximity", "mass centralization"], "risks": ["pilot back heat", "wing interference", "pitch moment"]},
            "LATERAL_ARCHITECTURE": {"zones": {"lateral", "shoulder"}, "benefits": ["roll authority", "left/right redundancy"], "risks": ["width", "drag", "failure asymmetry"]},
            "LOW_CENTER_PROPULSION_STUDY": {"zones": {"pelvis"}, "benefits": ["lower mass region", "pitch-control potential"], "risks": ["leg interference", "mobility", "pilot heat"]},
            "LEG_PROPULSION_STUDY": {"zones": {"upper-leg", "lower-leg"}, "benefits": ["control lever arm"], "risks": ["mobility penalty", "thermal exposure", "failure asymmetry"]},
            "FOOT_REGION_STUDY": {"zones": {"foot"}, "benefits": ["control potential"], "risks": ["landing interference", "long moment arm", "failure consequence"]},
            "WING_PROPULSION_STUDY": {"zones": {"wing-root", "wing-mid"}, "benefits": ["possible cruise integration"], "risks": ["rotational inertia", "wing load", "failure asymmetry"]},
        }
        by_id = {item["unitId"]: item for item in placement["units"]}
        result = []
        for name, study in families.items():
            units = [unit for unit in layout["units"] if CANDIDATE_ZONES.get(unit["mountZone"], {}).get("family") in study["zones"]]
            score = _average(by_id[unit["id"]]["placementScore"] for unit in units)
            result.append({"id": name, "units": [unit["id"] for unit in units], "score": round(score, 3) if score is not None else None,
                           "status": "EVALUATED" if score is not None else "NOT_EVALUATED", "potentialBenefits": study["benefits"], "potentialRisks": study["risks"],
                           "note": "Study output, not a physical recommendation."})
        return result

    @staticmethod
    def _minimum_viable(layout, unit_values):
        if not layout["units"] or any(value["unitValueScore"] is None for value in unit_values):
            return {"status": "DATA_REQUIRED", "unitCount": None, "unitIds": []}
        working = copy.deepcopy(layout)
        ordered = [item["unitId"] for item in sorted(unit_values, key=lambda item: item["unitValueScore"])]
        removed = []
        for unit_id in ordered:
            if len(working["units"]) <= 1:
                break
            trial = copy.deepcopy(working)
            trial["units"] = [unit for unit in trial["units"] if unit["id"] != unit_id]
            mass = InertiaEngine.calculate(trial)
            placement = PlacementEngine.evaluate(trial, mass)
            thermal = PlacementEngine.thermal(trial)
            mission = MissionEngine.run(trial, mass)
            control = ControlAllocationEngine.authority(trial, mass)
            failures = ControlAllocationEngine.failures(trial, mass)
            weight = (mass.get("totalMass") or 0.0) * 9.80665
            single_failure_ok = bool(failures["singleUnitFailure"]) and any(row["classification"] in {"RECOVERABLE", "DEGRADED"} for row in failures["singleUnitFailure"])
            if mission["status"] == "PASS" and not placement["geometryConflicts"] and not thermal["intersections"] and control["positive"]["LIFT"] >= weight and single_failure_ok:
                working = trial
                removed.append(unit_id)
        return {
            "status": "CANDIDATE_ONLY" if removed else "NO_REMOVAL_DEMONSTRATED",
            "unitCount": len(working["units"]), "unitIds": [unit["id"] for unit in working["units"]],
            "removedCandidates": removed,
            "note": "Abstract mission screen only; this is not approval to remove physical redundancy.",
        }

    @staticmethod
    def _unit_values(layout, propulsion, control, placement):
        state = {item["unitId"]: item for item in propulsion["unitStates"]}
        matrix = {item["unitId"]: item for item in control["controlMatrix"]}
        placements = {item["unitId"]: item for item in placement["units"]}
        maxima = {
            "thrust": max([item["thrust"] for item in state.values()] + [1.0]),
            "watts": max([item["watts"] or 0.0 for item in state.values()] + [1.0]),
            "thermal": max([item["thermalOutput"] or 0.0 for item in state.values()] + [1.0]),
            "mass": max([unit.get("mass") or 0.0 for unit in layout["units"]] + [1.0]),
        }
        level = {"NONE": 0.0, "LOW": 25.0, "MEDIUM": 60.0, "HIGH": 100.0}
        result = []
        for unit in layout["units"]:
            item = state[unit["id"]]
            controls = matrix[unit["id"]]
            control_score = _average(level[controls[axis]] for axis in ("Roll", "Pitch", "Yaw")) or 0.0
            score = _average([
                item["thrust"] / maxima["thrust"] * 100.0,
                control_score,
                80.0 if unit["redundancyGroup"] != "unassigned" else 20.0,
                100.0 - (item["watts"] or maxima["watts"]) / maxima["watts"] * 100.0,
                100.0 - (item["thermalOutput"] or maxima["thermal"]) / maxima["thermal"] * 100.0,
                100.0 - (unit.get("mass") or maxima["mass"]) / maxima["mass"] * 100.0,
                placements[unit["id"]]["placementScore"],
            ])
            result.append({"unitId": unit["id"], "unitValueScore": round(score, 3) if score is not None else None})
        return result

    @staticmethod
    def _questions(layout, mass, propulsion, drag, thermal, failures, unit_values):
        states = propulsion["unitStates"]
        def top(key):
            values = [item for item in states if item.get(key) is not None]
            return max(values, key=lambda item: abs(float(item[key]))) ["unitId"] if values else "DATA_REQUIRED"
        moment_axis = lambda axis: max(states, key=lambda item: abs(item["momentVector"][axis]))["unitId"] if states else "DATA_REQUIRED"
        drag_units = [unit for unit in layout["units"] if unit.get("frontalArea") is not None and unit.get("dragCoefficient") is not None]
        worst_value = min((item for item in unit_values if item["unitValueScore"] is not None), key=lambda item: item["unitValueScore"], default=None)
        return {
            "whereIsPropulsionMassConcentrated": mass.get("propulsionCom") or "DATA_REQUIRED",
            "howFarIsThrustFromCg": propulsion.get("cgOffsetDistance"),
            "largestPitchContributor": moment_axis("x"),
            "largestRollContributor": moment_axis("z"),
            "largestYawContributor": moment_axis("y"),
            "largestHeatContributor": top("thermalOutput"),
            "largestEnergyConsumer": top("watts"),
            "mostDangerousFailure": failures.get("worstFailure", {}).get("failedUnitId") if failures.get("worstFailure") else "DATA_REQUIRED",
            "largestDragContributor": max(drag_units, key=lambda unit: unit["frontalArea"] * unit["dragCoefficient"])["id"] if drag_units else "DATA_REQUIRED",
            "lowestMissionValueUnit": worst_value["unitId"] if worst_value else "DATA_REQUIRED",
        }

    def compare(self, payloads: list[Any]) -> dict[str, Any]:
        analyses = [self.analyze(payload) for payload in payloads[:8]]
        rows = []
        for analysis in analyses:
            dashboard = analysis["dashboard"]
            mass = analysis["massEngine"]
            mission = analysis["missionEngine"]
            rows.append({
                "id": analysis["layout"]["id"], "name": analysis["layout"]["name"], "decision": analysis["decision"],
                "mass": dashboard["totalPropulsionMass"], "cg": mass["vehicleCg"], "inertia": mass["propulsionPointMassInertia"],
                "drag": dashboard["propulsionDragNewtons"], "thermal": dashboard["totalThermalOutputWatts"],
                "controlAuthority": analysis["controlAllocationEngine"]["positive"], "energyConsumption": mission["totalEnergyWh"],
                "endurance": mission["targetEnduranceSeconds"] if mission["status"] == "PASS" else None,
                "failureTolerance": dashboard["redundancyScore"], "safety": dashboard["safetyIndex"],
            })
        return {"layouts": rows, "analyses": analyses, "note": "No single best layout is declared; compare trade-offs and evidence."}

    def auto_layout(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = normalize_layout(payload.get("layout"))
        template = normalize_unit(payload.get("unitTemplate"), 0)
        count = max(1, min(6, int(payload.get("numberOfUnits") or 1)))
        allowed = [zone for zone in payload.get("allowedZones", []) if zone in CANDIDATE_ZONES and zone not in base["forbiddenZones"]]
        if len(allowed) < count:
            return {"status": "INSUFFICIENT_ALLOWED_ZONES", "layouts": []}
        validation_layout = copy.deepcopy(base)
        validation_unit = copy.deepcopy(template)
        validation_zone = CANDIDATE_ZONES[allowed[0]]
        validation_unit["mountZone"] = allowed[0]
        validation_unit["positionX"], validation_unit["positionY"], validation_unit["positionZ"] = validation_zone["position"].values()
        validation_layout["units"] = [validation_unit]
        missing = data_requirements(validation_layout)
        if missing:
            return {
                "status": "INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT",
                "layouts": [],
                "missingData": missing,
                "note": "Complete the vehicle, mission and abstract unit template data before optimization.",
            }
        candidates = []
        for index, combination in enumerate(itertools.islice(itertools.combinations(allowed, count), 120)):
            layout = copy.deepcopy(base)
            layout["id"] = f"auto-{index + 1:03d}"
            layout["name"] = f"AUTO LAYOUT {index + 1:03d}"
            layout["units"] = []
            for unit_index, zone_id in enumerate(combination):
                zone = CANDIDATE_ZONES[zone_id]
                unit = copy.deepcopy(template)
                unit["id"] = f"auto-unit-{unit_index + 1:02d}"
                unit["name"] = f"Abstract unit {unit_index + 1:02d}"
                unit["mountZone"] = zone_id
                unit["positionX"], unit["positionY"], unit["positionZ"] = zone["position"].values()
                layout["units"].append(unit)
            analysis = self.analyze(layout)
            candidates.append(analysis)
        viable = [item for item in candidates if item["decision"] != "REJECTED"]
        viable.sort(key=lambda item: (
            item["dashboard"]["safetyIndex"] if item["dashboard"]["safetyIndex"] is not None else -1,
            item["dashboard"]["redundancyScore"] if item["dashboard"]["redundancyScore"] is not None else -1,
        ), reverse=True)
        return {
            "status": "INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT" if not viable or any(item["missingData"] for item in viable) else "PARETO_CANDIDATES",
            "layouts": [item["layout"] for item in viable[:12]],
            "summaries": [item["dashboard"] for item in viable[:12]],
            "note": "Candidates are retained as trade-offs; appearance is never an objective.",
        }
