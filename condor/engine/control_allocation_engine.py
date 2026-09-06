"""Autoridade, mixer abstrato, saturação e falhas do Condor X."""

from __future__ import annotations

from typing import Any

from .contracts import evidence
from .vector import cross, from_dict, sub, thrust_direction


CONTROL_AXES = ("LIFT", "FORWARD", "ROLL", "PITCH", "YAW")


def _column(unit: dict[str, Any], cg: tuple[float, float, float], failed: set[str] | None = None) -> list[float]:
    if unit["status"] != "ACTIVE" or unit["id"] in (failed or set()) or unit.get("maxThrust") is None:
        return [0.0] * 5
    direction = thrust_direction(unit["orientationPitch"], unit["orientationYaw"])
    force = tuple(value * float(unit["maxThrust"]) for value in direction)
    position = (unit["positionX"], unit["positionY"], unit["positionZ"])
    mx, my, mz = cross(sub(position, cg), force)
    # Convencão do lab: roll em torno de Z (frente), pitch em torno de X
    # (direita) e yaw em torno de Y (superior).
    return [force[1], force[2], mz, mx, my]


def _level(value: float, maximum: float) -> str:
    if maximum <= 1e-9 or value <= maximum * 0.02:
        return "NONE"
    ratio = value / maximum
    if ratio < 0.25:
        return "LOW"
    if ratio < 0.6:
        return "MEDIUM"
    return "HIGH"


class ControlAllocationEngine:
    @staticmethod
    def authority(layout: dict[str, Any], mass_state: dict[str, Any], *, failed: set[str] | None = None) -> dict[str, Any]:
        cg = from_dict(mass_state.get("vehicleCg") or {})
        columns = {unit["id"]: _column(unit, cg, failed) for unit in layout["units"]}
        positive = {axis: 0.0 for axis in CONTROL_AXES}
        negative = {axis: 0.0 for axis in CONTROL_AXES}
        for column in columns.values():
            for index, axis in enumerate(CONTROL_AXES):
                positive[axis] += max(0.0, column[index])
                negative[axis] += max(0.0, -column[index])
        maximum = {axis: max(positive[axis], negative[axis], 1e-9) for axis in CONTROL_AXES}
        matrix = []
        for unit in layout["units"]:
            column = columns[unit["id"]]
            matrix.append({
                "unitId": unit["id"],
                "Lift": _level(abs(column[0]), maximum["LIFT"]),
                "Forward": _level(abs(column[1]), maximum["FORWARD"]),
                "Roll": _level(abs(column[2]), maximum["ROLL"]),
                "Pitch": _level(abs(column[3]), maximum["PITCH"]),
                "Yaw": _level(abs(column[4]), maximum["YAW"]),
                "Emergency": "HIGH" if "EMERGENCY" in unit["controlGroup"] else "NONE",
                "numeric": {axis: round(column[index], 6) for index, axis in enumerate(CONTROL_AXES)},
            })
        return {
            "axisConvention": {"roll": "MZ", "pitch": "MX", "yaw": "MY"},
            "positive": {axis: round(value, 6) for axis, value in positive.items()},
            "negative": {axis: round(value, 6) for axis, value in negative.items()},
            "controlMatrix": matrix,
            "columns": columns,
            "evidence": evidence(
                "Maximum signed wrench contribution from each abstract unit around calculated CG",
                ["Rigid body", "Static thrust direction", "No aerodynamic control-surface authority"],
                "MEDIUM" if mass_state.get("vehicleCg") else "LOW",
            ),
        }

    @staticmethod
    def allocate(layout: dict[str, Any], mass_state: dict[str, Any], demand: dict[str, Any],
                 *, failed: set[str] | None = None) -> dict[str, Any]:
        cg = from_dict(mass_state.get("vehicleCg") or {})
        units = [unit for unit in layout["units"] if unit["status"] == "ACTIVE" and unit["id"] not in (failed or set())]
        columns = [_column(unit, cg, failed) for unit in units]
        target = [float(demand.get(axis, 0.0) or 0.0) for axis in CONTROL_AXES]
        commands = [0.0] * len(units)
        # Descenso por coordenadas projetado. É determinístico, pequeno e
        # suficiente para o mixer conceitual sem acrescentar NumPy ao Condor.
        for _ in range(160):
            current = [sum(columns[j][i] * commands[j] for j in range(len(units))) for i in range(5)]
            residual = [target[i] - current[i] for i in range(5)]
            changed = 0.0
            for j, column in enumerate(columns):
                norm = sum(value * value for value in column)
                if norm <= 1e-12:
                    continue
                delta = sum(column[i] * residual[i] for i in range(5)) / norm
                limit = units[j].get("operationalLimit")
                upper = min(1.0, float(limit)) if limit is not None else 1.0
                updated = min(upper, max(0.0, commands[j] + delta))
                minimum = units[j].get("minimumStableOutput")
                if updated > 0 and minimum is not None:
                    updated = max(updated, min(upper, float(minimum)))
                changed = max(changed, abs(updated - commands[j]))
                commands[j] = updated
            if changed < 1e-8:
                break
        achieved = [sum(columns[j][i] * commands[j] for j in range(len(units))) for i in range(5)]
        residual = [target[i] - achieved[i] for i in range(5)]
        normalized_error = max(
            abs(residual[i]) / max(abs(target[i]), 1.0) for i in range(5)
        ) if target else 0.0
        command_map = {unit["id"]: round(commands[index], 8) for index, unit in enumerate(units)}
        saturated = []
        for index, unit in enumerate(units):
            limit = min(1.0, float(unit["operationalLimit"])) if unit.get("operationalLimit") is not None else 1.0
            if commands[index] >= limit - 1e-6:
                saturated.append(unit["id"])
        return {
            "demand": {axis: round(target[index], 6) for index, axis in enumerate(CONTROL_AXES)},
            "achieved": {axis: round(achieved[index], 6) for index, axis in enumerate(CONTROL_AXES)},
            "remainingError": {axis: round(residual[index], 6) for index, axis in enumerate(CONTROL_AXES)},
            "commands": command_map,
            "saturatedUnits": saturated,
            "controlAuthorityInsufficient": normalized_error > 0.05,
            "normalizedError": round(normalized_error, 6),
            "evidence": evidence(
                "Bounded projected coordinate-descent allocation over unit wrench columns",
                ["Static allocation", "No actuator dynamics", "5-axis abstract demand"],
                "LOW",
            ),
        }

    @staticmethod
    def failures(layout: dict[str, Any], mass_state: dict[str, Any]) -> dict[str, Any]:
        baseline = ControlAllocationEngine.authority(layout, mass_state)
        base_lift = baseline["positive"]["LIFT"]
        weight = (mass_state.get("totalMass") or 0.0) * 9.80665
        rows = []
        for unit in layout["units"]:
            failed = {unit["id"]}
            state = ControlAllocationEngine.authority(layout, mass_state, failed=failed)
            lift = state["positive"]["LIFT"]
            lift_ratio = lift / base_lift if base_lift > 1e-9 else 0.0
            axis_ratios = []
            for axis in ("ROLL", "PITCH", "YAW"):
                base_span = min(baseline["positive"][axis], baseline["negative"][axis])
                span = min(state["positive"][axis], state["negative"][axis])
                if base_span > 1e-9:
                    axis_ratios.append(min(1.0, span / base_span))
            control_ratio = min(axis_ratios) if axis_ratios else 0.0
            landing = bool(weight > 0 and lift >= weight)
            if landing and control_ratio >= 0.6:
                classification = "RECOVERABLE"
            elif lift_ratio >= 0.65 and control_ratio >= 0.3:
                classification = "DEGRADED"
            elif lift_ratio > 0.0:
                classification = "CRITICAL"
            else:
                classification = "UNRECOVERABLE"
            rows.append({
                "failedUnitId": unit["id"], "classification": classification,
                "thrustRemainingPercent": round(lift_ratio * 100.0, 3),
                "controlRemainingPercent": round(control_ratio * 100.0, 3),
                "landingCapability": landing if weight > 0 else None,
                "flightImpact": "VERTICAL_MARGIN_REDUCED" if lift_ratio < 1 else "NONE",
                "controlImpact": "ASYMMETRIC_AUTHORITY" if control_ratio < 0.99 else "NONE",
                "missionImpact": classification, "landingImpact": "POSSIBLE" if landing else "NOT_DEMONSTRATED",
            })

        common_groups: dict[str, set[str]] = {}
        for unit in layout["units"]:
            side = "LEFT_SIDE" if unit["positionX"] < 0 else "RIGHT_SIDE" if unit["positionX"] > 0 else "CENTER"
            common_groups.setdefault(side, set()).add(unit["id"])
            common_groups.setdefault(f"REDUNDANCY_{unit['redundancyGroup'].upper()}", set()).add(unit["id"])
            for group in unit["controlGroup"]:
                common_groups.setdefault(f"{group}_GROUP", set()).add(unit["id"])
        common = []
        for group, failed in sorted(common_groups.items()):
            if group == "CENTER" or not failed:
                continue
            state = ControlAllocationEngine.authority(layout, mass_state, failed=failed)
            lift_ratio = state["positive"]["LIFT"] / base_lift if base_lift > 1e-9 else 0.0
            common.append({"group": group, "failedUnits": sorted(failed), "liftRemainingPercent": round(lift_ratio * 100, 3)})

        grade = {"RECOVERABLE": 100.0, "DEGRADED": 65.0, "CRITICAL": 25.0, "UNRECOVERABLE": 0.0}
        redundancy_score = sum(grade[row["classification"]] for row in rows) / len(rows) if rows else 0.0
        return {
            "singleUnitFailure": rows,
            "commonModeFailure": common,
            "propulsionRedundancyScore": round(redundancy_score, 3) if rows and weight > 0 else None,
            "worstFailure": min(rows, key=lambda row: grade[row["classification"]]) if rows else None,
            "evidence": evidence(
                "Recalculate signed static authority with one unit or logical group removed",
                ["No transient dynamics", "Landing requires configured weight and positive vertical capacity"],
                "LOW",
            ),
        }
