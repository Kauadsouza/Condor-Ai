"""Contrato biomecânico do corpo digital, independente da malha visual."""

from __future__ import annotations


MOVEMENTS = {
    "neck": ["flexion", "extension", "lateral_inclination", "rotation"],
    "shoulder": ["flexion", "extension", "abduction", "adduction", "internal_rotation", "external_rotation"],
    "elbow": ["flexion", "extension", "pronation", "supination"],
    "wrist": ["flexion", "extension", "radial_deviation", "ulnar_deviation"],
    "finger": ["flexion", "extension", "abduction", "adduction"],
    "thumb": ["flexion", "extension", "abduction", "adduction", "opposition"],
    "hip": ["flexion", "extension", "abduction", "adduction", "internal_rotation", "external_rotation"],
    "knee": ["flexion", "extension"],
    "ankle": ["dorsiflexion", "plantar_flexion", "inversion", "eversion"],
}


def _finger(name: str, thumb: bool = False) -> dict:
    bones = ["proximal_phalanx", "distal_phalanx"] if thumb else ["proximal_phalanx", "middle_phalanx", "distal_phalanx"]
    joints = ["metacarpophalangeal", "interphalangeal"] if thumb else ["metacarpophalangeal", "proximal_interphalangeal", "distal_interphalangeal"]
    return {"id": name, "bones": bones, "joints": joints, "movements": MOVEMENTS["thumb" if thumb else "finger"]}


def _hand(side: str) -> dict:
    return {
        "id": f"{side}-hand",
        "regions": ["wrist", "palm", "thumb", "index", "middle", "ring", "little"],
        "bones": ["radius", "ulna", "carpals", "metacarpals", "phalanges"],
        "joints": ["wrist", "carpometacarpal", "metacarpophalangeal", "interphalangeal"],
        "movements": MOVEMENTS["wrist"],
        "digits": [
            _finger("thumb", True), _finger("index"), _finger("middle"),
            _finger("ring"), _finger("little"),
        ],
    }


def human_model_contract() -> dict:
    """Dados técnicos; não afirma medidas ou capacidades não registradas."""
    return {
        "version": "1.0",
        "default_layer": "silhouette",
        "layers": [
            {"id": "silhouette", "name": "Silhueta", "purpose": "selection_navigation"},
            {"id": "structure", "name": "Estrutura corporal", "purpose": "regions"},
            {"id": "bones", "name": "Ossos", "purpose": "skeletal_reference"},
            {"id": "joints", "name": "Articulações", "purpose": "movement_points"},
            {"id": "axes", "name": "Eixos de movimento", "purpose": "movement_visualization"},
            {"id": "technical_points", "name": "Pontos técnicos", "purpose": "future_anchors"},
        ],
        "regions": {
            "head": {"bones": ["skull", "mandible"], "joints": ["jaw"]},
            "neck": {"bones": ["cervical_spine"], "joints": ["neck"], "movements": MOVEMENTS["neck"]},
            "torso": {"bones": ["clavicle", "scapula", "spine", "ribs", "sternum"]},
            "pelvis": {"bones": ["pelvis", "sacrum"], "joints": ["hip"]},
            "left-arm": {"bones": ["humerus", "radius", "ulna"], "joints": ["shoulder", "elbow", "wrist"]},
            "right-arm": {"bones": ["humerus", "radius", "ulna"], "joints": ["shoulder", "elbow", "wrist"]},
            "left-leg": {"bones": ["femur", "patella", "tibia", "fibula", "tarsals", "metatarsals"], "joints": ["hip", "knee", "ankle"]},
            "right-leg": {"bones": ["femur", "patella", "tibia", "fibula", "tarsals", "metatarsals"], "joints": ["hip", "knee", "ankle"]},
        },
        "hands": {"left": _hand("left"), "right": _hand("right")},
        "joint_movements": MOVEMENTS,
        "technical_point_types": ["sensor", "motor", "actuator", "joint", "servo", "cable", "board", "mechanical_structure"],
        "measurements": {},
        "truth": "Measurements, ranges and capabilities remain undefined until recorded and validated.",
    }
