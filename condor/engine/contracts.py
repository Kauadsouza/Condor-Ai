"""Contratos e normalização do Propulsion Placement Lab do Condor X."""

from __future__ import annotations

import copy
import math
import re
from typing import Any


MODEL_SCHEMA = "condor-x-propulsion-layout-v1"
ANALYSIS_SCHEMA = "condor-x-propulsion-analysis-v1"
MODEL_LEVEL = "L2"
SOURCE_TYPE = "SIMULATION"

# Eixos usados em todo o laboratório: X=direita, Y=superior, Z=frente.
# As coordenadas são uma referência digital abstrata em metros e não medidas
# corporais, recomendações de instalação ou geometria certificada.
_ZONE_DATA = (
    ("PZ-DORSAL-CENTER", 0.00, 0.92, -0.28, "dorsal"),
    ("PZ-DORSAL-LEFT", -0.24, 0.92, -0.25, "dorsal"),
    ("PZ-DORSAL-RIGHT", 0.24, 0.92, -0.25, "dorsal"),
    ("PZ-SHOULDER-LEFT", -0.42, 1.20, -0.05, "shoulder"),
    ("PZ-SHOULDER-RIGHT", 0.42, 1.20, -0.05, "shoulder"),
    ("PZ-TORSO-LATERAL-LEFT", -0.36, 0.78, -0.02, "lateral"),
    ("PZ-TORSO-LATERAL-RIGHT", 0.36, 0.78, -0.02, "lateral"),
    ("PZ-PELVIS-LEFT", -0.24, 0.35, -0.06, "pelvis"),
    ("PZ-PELVIS-RIGHT", 0.24, 0.35, -0.06, "pelvis"),
    ("PZ-UPPER-LEG-LEFT", -0.19, -0.12, -0.01, "upper-leg"),
    ("PZ-UPPER-LEG-RIGHT", 0.19, -0.12, -0.01, "upper-leg"),
    ("PZ-LOWER-LEG-LEFT", -0.17, -0.70, 0.00, "lower-leg"),
    ("PZ-LOWER-LEG-RIGHT", 0.17, -0.70, 0.00, "lower-leg"),
    ("PZ-FOOT-LEFT", -0.17, -1.10, 0.16, "foot"),
    ("PZ-FOOT-RIGHT", 0.17, -1.10, 0.16, "foot"),
    ("PZ-WING-ROOT-LEFT", -0.52, 1.00, -0.18, "wing-root"),
    ("PZ-WING-ROOT-RIGHT", 0.52, 1.00, -0.18, "wing-root"),
    ("PZ-WING-MID-LEFT", -1.05, 0.96, -0.12, "wing-mid"),
    ("PZ-WING-MID-RIGHT", 1.05, 0.96, -0.12, "wing-mid"),
)

CANDIDATE_ZONES = {
    zone_id: {
        "id": zone_id,
        "position": {"x": x, "y": y, "z": z},
        "family": family,
        "status": "NOT_EVALUATED",
        "source": "ABSTRACT_DIGITAL_REFERENCE",
        "confidence": "LOW",
    }
    for zone_id, x, y, z, family in _ZONE_DATA
}

PROPULSION_GROUPS = {"PRIMARY", "SECONDARY", "CONTROL", "CRUISE", "TRANSITION", "EMERGENCY"}
UNIT_STATUSES = {"ACTIVE", "INACTIVE", "FAILED"}
CONFIDENCE_LEVELS = {"LOW", "MEDIUM", "HIGH", "DATA_REQUIRED"}
OPTIMIZATION_OBJECTIVES = {
    "MINIMUM_MASS", "MINIMUM_DRAG", "MINIMUM_PILOT_HEAT", "MINIMUM_ENERGY",
    "MAXIMUM_CONTROL", "MAXIMUM_REDUNDANCY", "MAXIMUM_ENDURANCE", "BALANCED",
}
DESIGN_STUDIO_MODES = {"DESIGN", "AERO", "STRUCTURE", "MASS_CG", "ENERGY", "PROPULSION", "THERMAL", "SAFETY", "MISSION"}
DESIGN_PROPULSION_CONCEPTS = {"A", "B", "C"}

_SAFE_ID = re.compile(r"[^a-zA-Z0-9_-]+")


def finite(value: Any, default: float | None = None, *, minimum: float | None = None,
           maximum: float | None = None) -> float | None:
    """Retorna apenas números JSON finitos, preservando DATA REQUIRED como None."""
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def safe_id(value: Any, fallback: str) -> str:
    cleaned = _SAFE_ID.sub("-", str(value or "").strip())[:80].strip("-")
    return cleaned or fallback


def _vector(raw: Any, fallback: dict[str, float] | None = None) -> dict[str, float]:
    source = raw if isinstance(raw, dict) else {}
    base = fallback or {"x": 0.0, "y": 0.0, "z": 0.0}
    return {
        axis: finite(source.get(axis), base[axis], minimum=-20.0, maximum=20.0) or 0.0
        for axis in ("x", "y", "z")
    }


def _curve(raw: Any, output_key: str) -> list[dict[str, float]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, float]] = []
    for item in raw[:32]:
        if not isinstance(item, dict):
            continue
        command = finite(item.get("powerCommand"), None, minimum=0.0, maximum=1.0)
        output = finite(item.get(output_key), None, minimum=0.0)
        if command is not None and output is not None:
            result.append({"powerCommand": command, output_key: output})
    return sorted(result, key=lambda item: item["powerCommand"])


def _design_position(raw: Any, fallback: dict[str, float]) -> dict[str, float]:
    source = raw if isinstance(raw, dict) else {}
    return {
        axis: finite(source.get(axis), fallback[axis], minimum=-2.5, maximum=2.5) or 0.0
        for axis in ("x", "y", "z")
    }


def normalize_design_studio(raw: Any) -> dict[str, Any]:
    """Normaliza somente hipóteses visuais; estes valores não são engenharia validada."""
    source = raw if isinstance(raw, dict) else {}
    wing = source.get("wing") if isinstance(source.get("wing"), dict) else {}
    energy_source = source.get("energyVolumes") if isinstance(source.get("energyVolumes"), list) else []
    pod_source = source.get("propulsionPods") if isinstance(source.get("propulsionPods"), list) else []
    energy_defaults = (
        ("CX-M01-ENERGY-CENTER", {"x": 0.0, "y": 0.56, "z": -0.12}),
        ("CX-M01-ENERGY-L", {"x": -0.26, "y": 0.52, "z": -0.10}),
        ("CX-M01-ENERGY-R", {"x": 0.26, "y": 0.52, "z": -0.10}),
    )
    pod_defaults = (
        ("CX-M01-PROP-DORSAL-L", {"x": -0.16, "y": 0.91, "z": -0.30}, "DORSAL"),
        ("CX-M01-PROP-DORSAL-R", {"x": 0.16, "y": 0.91, "z": -0.30}, "DORSAL"),
        ("CX-M01-PROP-WROOT-L", {"x": -0.48, "y": 0.99, "z": -0.22}, "WING_ROOT"),
        ("CX-M01-PROP-WROOT-R", {"x": 0.48, "y": 0.99, "z": -0.22}, "WING_ROOT"),
    )
    energy_by_id = {str(item.get("id")): item for item in energy_source[:8] if isinstance(item, dict)}
    pods_by_id = {str(item.get("id")): item for item in pod_source[:12] if isinstance(item, dict)}
    concept = str(source.get("propulsionConcept") or "A").upper()
    mode = str(source.get("mode") or "DESIGN").upper().replace("/", "_").replace(" ", "_")
    fold = str(wing.get("fold") or "DEPLOYED").upper()
    return {
        "schema": "condor-x-design-studio-v1",
        "concept": "A",
        "hypothesis": "UNVALIDATED",
        "mode": mode if mode in DESIGN_STUDIO_MODES else "DESIGN",
        "flightPoseDegrees": finite(source.get("flightPoseDegrees"), 0.0, minimum=0.0, maximum=90.0) or 0.0,
        "pilotVisible": bool(source.get("pilotVisible", False)),
        "propulsionConcept": concept if concept in DESIGN_PROPULSION_CONCEPTS else "A",
        "wing": {
            "linked": bool(wing.get("linked", True)),
            "spanScale": finite(wing.get("spanScale"), 1.0, minimum=0.65, maximum=1.65) or 1.0,
            "rootChordScale": finite(wing.get("rootChordScale"), 1.0, minimum=0.65, maximum=1.5) or 1.0,
            "tipChordScale": finite(wing.get("tipChordScale"), 1.0, minimum=0.55, maximum=1.5) or 1.0,
            "sweepDegrees": finite(wing.get("sweepDegrees"), 24.0, minimum=5.0, maximum=55.0) or 24.0,
            "dihedralDegrees": finite(wing.get("dihedralDegrees"), 4.0, minimum=-12.0, maximum=22.0) or 4.0,
            "twistDegrees": finite(wing.get("twistDegrees"), -2.0, minimum=-15.0, maximum=15.0) or -2.0,
            "fold": fold if fold in {"DEPLOYED", "PARTIAL", "STOWED"} else "DEPLOYED",
        },
        "energyVolumes": [
            {
                "id": item_id,
                "position": _design_position(energy_by_id.get(item_id, {}).get("position"), fallback),
                "mass": finite(energy_by_id.get(item_id, {}).get("mass"), None, minimum=0.0),
                "capacityWh": finite(energy_by_id.get(item_id, {}).get("capacityWh"), None, minimum=0.0),
                "status": "DATA_REQUIRED",
            }
            for item_id, fallback in energy_defaults
        ],
        "propulsionPods": [
            {
                "id": item_id,
                "position": _design_position(pods_by_id.get(item_id, {}).get("position"), fallback),
                "role": role,
                "status": "DESIGN_CANDIDATE",
            }
            for item_id, fallback, role in pod_defaults
        ],
        "assumptions": [
            "Visual geometry uses relative digital reference coordinates.",
            "Propulsion concepts A, B and C do not select a physical technology.",
            "M01 two-hour endurance is a mission target, not a predicted result.",
        ],
    }


def normalize_unit(raw: Any, index: int = 0) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    unit_id = safe_id(source.get("id"), f"unit-{index + 1:02d}")
    mount_zone = str(source.get("mountZone") or "").upper()
    zone = CANDIDATE_ZONES.get(mount_zone)
    zone_position = zone["position"] if zone else {"x": 0.0, "y": 0.0, "z": 0.0}
    groups = source.get("controlGroup")
    if isinstance(groups, str):
        groups = [groups]
    normalized_groups = []
    for group in groups if isinstance(groups, list) else []:
        value = str(group).upper()
        if value in PROPULSION_GROUPS and value not in normalized_groups:
            normalized_groups.append(value)
    envelope = source.get("installationEnvelope") if isinstance(source.get("installationEnvelope"), dict) else {}
    service = source.get("serviceEnvelope") if isinstance(source.get("serviceEnvelope"), dict) else {}
    position = {
        "x": finite(source.get("positionX"), zone_position["x"], minimum=-20.0, maximum=20.0) or 0.0,
        "y": finite(source.get("positionY"), zone_position["y"], minimum=-20.0, maximum=20.0) or 0.0,
        "z": finite(source.get("positionZ"), zone_position["z"], minimum=-20.0, maximum=20.0) or 0.0,
    }
    return {
        "id": unit_id,
        "name": str(source.get("name") or unit_id).strip()[:120],
        "propulsionType": "ABSTRACT_THRUST_SOURCE",
        "mass": finite(source.get("mass"), None, minimum=0.0),
        "positionX": position["x"], "positionY": position["y"], "positionZ": position["z"],
        "orientationPitch": finite(source.get("orientationPitch"), 0.0, minimum=-180.0, maximum=180.0) or 0.0,
        "orientationYaw": finite(source.get("orientationYaw"), 0.0, minimum=-180.0, maximum=180.0) or 0.0,
        "orientationRoll": finite(source.get("orientationRoll"), 0.0, minimum=-180.0, maximum=180.0) or 0.0,
        "maxThrust": finite(source.get("maxThrust"), None, minimum=0.0),
        "continuousThrust": finite(source.get("continuousThrust"), None, minimum=0.0),
        "minimumStableOutput": finite(source.get("minimumStableOutput"), None, minimum=0.0, maximum=1.0),
        "responseTime": finite(source.get("responseTime"), None, minimum=0.0),
        "efficiencyCurve": _curve(source.get("efficiencyCurve"), "efficiency"),
        "energyConsumptionCurve": _curve(source.get("energyConsumptionCurve"), "watts"),
        "thermalOutput": finite(source.get("thermalOutput"), None, minimum=0.0),
        "surfaceTemperatureEstimate": finite(source.get("surfaceTemperatureEstimate"), None),
        "thermalRadiusEstimate": finite(source.get("thermalRadiusEstimate"), None, minimum=0.0),
        "thermalResistance": finite(source.get("thermalResistance"), None, minimum=0.0),
        "thermalTimeConstant": finite(source.get("thermalTimeConstant"), None, minimum=0.0),
        "coolingEffectiveness": finite(source.get("coolingEffectiveness"), None, minimum=0.0, maximum=1.0),
        "airMassFlowReference": finite(source.get("airMassFlowReference"), None, minimum=0.0),
        "operationalLimit": finite(source.get("operationalLimit"), None, minimum=0.0, maximum=1.0),
        "failureProbabilityPlaceholder": finite(source.get("failureProbabilityPlaceholder"), None, minimum=0.0, maximum=1.0),
        "mountZone": mount_zone if zone or mount_zone == "UNPLACED" else "FREE_POSITION",
        "controlGroup": normalized_groups,
        "redundancyGroup": safe_id(source.get("redundancyGroup"), "unassigned")[:50],
        "status": str(source.get("status") or "ACTIVE").upper() if str(source.get("status") or "ACTIVE").upper() in UNIT_STATUSES else "INACTIVE",
        "confidenceLevel": str(source.get("confidenceLevel") or "DATA_REQUIRED").upper() if str(source.get("confidenceLevel") or "DATA_REQUIRED").upper() in CONFIDENCE_LEVELS else "DATA_REQUIRED",
        "powerCommand": finite(source.get("powerCommand"), None, minimum=0.0, maximum=1.0),
        "frontalArea": finite(source.get("frontalArea"), None, minimum=0.0),
        "dragCoefficient": finite(source.get("dragCoefficient"), None, minimum=0.0),
        "structuralSupportScore": finite(source.get("structuralSupportScore"), None, minimum=0.0, maximum=100.0),
        "maintenanceAccessScore": finite(source.get("maintenanceAccessScore"), None, minimum=0.0, maximum=100.0),
        "installationEnvelope": {
            axis: finite(envelope.get(axis), None, minimum=0.0, maximum=10.0)
            for axis in ("length", "width", "height")
        },
        "serviceEnvelope": {
            axis: finite(service.get(axis), None, minimum=0.0, maximum=10.0)
            for axis in ("length", "width", "height")
        },
    }


def normalize_layout(raw: Any) -> dict[str, Any]:
    source = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    layout_id = safe_id(source.get("id"), "layout")
    vehicle = source.get("vehicle") if isinstance(source.get("vehicle"), dict) else {}
    energy_zone = vehicle.get("energyStorageZone") if isinstance(vehicle.get("energyStorageZone"), dict) else {}
    mission = source.get("mission") if isinstance(source.get("mission"), dict) else {}
    raw_dry_cg = vehicle.get("dryCg") if isinstance(vehicle.get("dryCg"), dict) else {}
    dry_cg = _vector(raw_dry_cg)
    raw_dry_cg_provided = vehicle.get("dryCgProvided") if isinstance(vehicle.get("dryCgProvided"), dict) else None
    if raw_dry_cg_provided is not None:
        dry_cg_provided = {axis: bool(raw_dry_cg_provided.get(axis)) for axis in ("x", "y", "z")}
    else:
        # Compatibilidade com configurações antigas: só consideramos o vetor
        # deliberado quando a massa seca e cada componente vieram no payload.
        dry_cg_provided = {
            axis: vehicle.get("dryMass") is not None and finite(raw_dry_cg.get(axis), None, minimum=-20.0, maximum=20.0) is not None
            for axis in ("x", "y", "z")
        }
    phases = mission.get("phases") if isinstance(mission.get("phases"), dict) else {}
    normalized_phases = {
        name: finite(phases.get(name), None, minimum=0.0, maximum=7200.0)
        for name in ("TAKEOFF", "TRANSITION", "CRUISE", "LANDING")
    }
    units_source = source.get("units") if isinstance(source.get("units"), list) else []
    units = [normalize_unit(unit, index) for index, unit in enumerate(units_source[:32])]
    seen: set[str] = set()
    for index, unit in enumerate(units):
        original = unit["id"]
        if original in seen:
            unit["id"] = f"{original}-{index + 1}"
        seen.add(unit["id"])
    return {
        "schema": MODEL_SCHEMA,
        "id": layout_id,
        "name": str(source.get("name") or layout_id).strip()[:120],
        "preset": str(source.get("preset") or "HYBRID").upper()[:40],
        "objective": str(source.get("objective") or "BALANCED").upper() if str(source.get("objective") or "BALANCED").upper() in OPTIMIZATION_OBJECTIVES else "BALANCED",
        "selectedUnitId": safe_id(source.get("selectedUnitId"), "") if source.get("selectedUnitId") else None,
        "vehicle": {
            "dryMass": finite(vehicle.get("dryMass"), None, minimum=0.0),
            "dryCg": dry_cg,
            "dryCgProvided": dry_cg_provided,
            "energyCapacityWh": finite(vehicle.get("energyCapacityWh"), None, minimum=0.0),
            "energyReservePercent": finite(vehicle.get("energyReservePercent"), None, minimum=0.0, maximum=100.0),
            "wingArea": finite(vehicle.get("wingArea"), None, minimum=0.0),
            "liftCoefficient": finite(vehicle.get("liftCoefficient"), None),
            "bodyDragArea": finite(vehicle.get("bodyDragArea"), None, minimum=0.0),
            "airDensity": finite(vehicle.get("airDensity"), None, minimum=0.0),
            "cruiseSpeed": finite(vehicle.get("cruiseSpeed"), None, minimum=0.0),
            "cgEnvelopeRadius": finite(vehicle.get("cgEnvelopeRadius"), None, minimum=0.0),
            "energyStorageZone": {
                "x": finite(energy_zone.get("x"), None, minimum=-20.0, maximum=20.0),
                "y": finite(energy_zone.get("y"), None, minimum=-20.0, maximum=20.0),
                "z": finite(energy_zone.get("z"), None, minimum=-20.0, maximum=20.0),
                "radius": finite(energy_zone.get("radius"), None, minimum=0.0, maximum=10.0),
            },
        },
        "mission": {
            "id": "M01",
            "targetEnduranceSeconds": finite(mission.get("targetEnduranceSeconds"), 7200.0, minimum=1.0, maximum=86400.0),
            "phases": normalized_phases,
        },
        "designStudio": normalize_design_studio(source.get("designStudio")),
        "units": units,
        "forbiddenZones": [str(value).upper() for value in source.get("forbiddenZones", [])[:32] if str(value).upper() in CANDIDATE_ZONES] if isinstance(source.get("forbiddenZones"), list) else [],
        "notes": str(source.get("notes") or "")[:4000],
    }


def blank_layout(layout_id: str, name: str) -> dict[str, Any]:
    return normalize_layout({
        "id": layout_id,
        "name": name,
        "preset": "HYBRID",
        "objective": "BALANCED",
        "vehicle": {},
        "mission": {"id": "M01", "targetEnduranceSeconds": 7200, "phases": {}},
        "units": [],
    })


def data_requirements(layout: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    vehicle = layout["vehicle"]
    for key, label in (
        ("dryMass", "VEHICLE DRY MASS"), ("energyCapacityWh", "ENERGY CAPACITY"),
        ("energyReservePercent", "ENERGY RESERVE"),
        ("wingArea", "WING AREA"), ("liftCoefficient", "LIFT COEFFICIENT"),
        ("bodyDragArea", "BODY DRAG AREA"), ("airDensity", "AIR DENSITY"),
        ("cruiseSpeed", "CRUISE SPEED"), ("cgEnvelopeRadius", "CG ENVELOPE RADIUS"),
    ):
        if vehicle.get(key) is None:
            missing.append(label)
    for axis in ("x", "y", "z"):
        if not vehicle.get("dryCgProvided", {}).get(axis):
            missing.append(f"DRY CG {axis.upper()}")
    for phase, duration in layout["mission"]["phases"].items():
        if duration is None:
            missing.append(f"M01 {phase} DURATION")
    phase_values = list(layout["mission"]["phases"].values())
    if phase_values and all(value is not None for value in phase_values):
        if abs(sum(float(value) for value in phase_values) - float(layout["mission"]["targetEnduranceSeconds"])) > 1e-6:
            missing.append("M01 PHASE DURATIONS MUST SUM TO TARGET")
    if any(layout["vehicle"]["energyStorageZone"].get(key) is None for key in ("x", "y", "z", "radius")):
        missing.append("ENERGY STORAGE ZONE")
    if not layout["units"]:
        missing.append("AT LEAST ONE ABSTRACT PROPULSION UNIT")
    for unit in layout["units"]:
        if unit.get("mountZone") == "UNPLACED":
            missing.append(f"{unit['id']} PLACEMENT")
        for key, label in (
            ("mass", "MASS"), ("maxThrust", "MAX THRUST"),
            ("continuousThrust", "CONTINUOUS THRUST"), ("powerCommand", "POWER COMMAND"),
            ("minimumStableOutput", "MINIMUM STABLE OUTPUT"), ("responseTime", "RESPONSE TIME"),
            ("thermalOutput", "THERMAL OUTPUT"), ("thermalRadiusEstimate", "THERMAL RADIUS"),
            ("thermalResistance", "THERMAL RESISTANCE"), ("thermalTimeConstant", "THERMAL TIME CONSTANT"),
            ("coolingEffectiveness", "COOLING EFFECTIVENESS"), ("operationalLimit", "OPERATIONAL LIMIT"),
            ("frontalArea", "FRONTAL AREA"), ("dragCoefficient", "DRAG COEFFICIENT"),
            ("structuralSupportScore", "STRUCTURAL SUPPORT"), ("maintenanceAccessScore", "MAINTENANCE ACCESS"),
        ):
            if unit.get(key) is None:
                missing.append(f"{unit['id']} {label}")
        if not unit.get("energyConsumptionCurve"):
            missing.append(f"{unit['id']} ENERGY CONSUMPTION CURVE")
        if any(unit["installationEnvelope"].get(axis) is None for axis in ("length", "width", "height")):
            missing.append(f"{unit['id']} INSTALLATION ENVELOPE")
        if any(unit["serviceEnvelope"].get(axis) is None for axis in ("length", "width", "height")):
            missing.append(f"{unit['id']} SERVICE ENVELOPE")
        if not unit.get("controlGroup"):
            missing.append(f"{unit['id']} CONTROL GROUP")
        if unit.get("redundancyGroup") == "unassigned":
            missing.append(f"{unit['id']} REDUNDANCY GROUP")
        if unit.get("confidenceLevel") == "DATA_REQUIRED":
            missing.append(f"{unit['id']} CONFIDENCE")
    return missing


def evidence(method: str, assumptions: list[str], confidence: str = "LOW") -> dict[str, Any]:
    return {
        "source": "Simplified Condor X abstract model",
        "sourceType": SOURCE_TYPE,
        "method": method,
        "assumptions": assumptions,
        "confidence": confidence,
        "modelLevel": MODEL_LEVEL,
    }
