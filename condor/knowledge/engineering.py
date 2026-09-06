"""Base técnica local, enxuta e rastreável para raciocínio de engenharia.

Não tenta transformar um modelo pequeno em autoridade infalível. Entrega ao
modelo princípios, equações, processos de validação e fontes primárias para que
ele raciocine com unidades, hipóteses e limites explícitos mesmo sem internet.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineeringReference:
    domain: str
    keywords: tuple[str, ...]
    principles: tuple[str, ...]
    source: str
    url: str


REFERENCES = (
    EngineeringReference(
        "aerodynamics",
        ("aerodinamica", "asa", "arrasto", "sustentacao", "lift", "drag", "fluxo", "cfd", "mach", "reynolds"),
        (
            "Use q = 0.5*rho*V^2; lift L = Cl*q*A; drag D = Cd*q*A. Declare rho, V, reference area and coefficient source.",
            "Cl and Cd depend on geometry, angle of attack, Reynolds number and Mach number; do not transfer coefficients between regimes without validation.",
            "L/D = Cl/Cd only when the same reference area and dynamic pressure convention are used.",
            "Analytical estimates establish bounds; CFD needs mesh-independence and turbulence-model sensitivity; final coefficients need experimental correlation.",
        ),
        "NASA Glenn Beginner's Guide to Aeronautics",
        "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/drag-equation/",
    ),
    EngineeringReference(
        "flight_dynamics",
        ("estabilidade", "voo", "aeronave", "centro de pressao", "centro de gravidade", "controle de voo"),
        (
            "Resolve forces and moments in a declared coordinate frame; never mix body, wind and inertial axes silently.",
            "Static stability, dynamic stability and controllability are different claims and require different evidence.",
            "Mass, center of gravity and inertia tensor are mandatory inputs for credible rigid-body simulation.",
        ),
        "NASA Glenn Aerodynamic Forces",
        "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/aerodynamic-forces/",
    ),
    EngineeringReference(
        "systems_engineering",
        ("sistema", "requisito", "arquitetura", "mbse", "interface", "verificacao", "validacao", "trade study"),
        (
            "Trace stakeholder needs to verifiable requirements, architecture, interfaces, implementation and evidence.",
            "Verification asks whether the product meets requirements; validation asks whether it solves the intended need in its operational context.",
            "Maintain configuration, assumptions, risks, decisions and interface contracts across the full life cycle.",
            "A trade study must state criteria, weights, alternatives, uncertainty and sensitivity; a score alone is not engineering evidence.",
        ),
        "NASA Systems Engineering Handbook",
        "https://www.nasa.gov/reference/systems-engineering-handbook/",
    ),
    EngineeringReference(
        "mechanical_structures",
        ("mecanica", "estrutura", "tensao", "deformacao", "fadiga", "flambagem", "torque", "rolamento", "engrenagem"),
        (
            "Start from a free-body diagram, load cases and boundary conditions; then check stress, deformation, stability, fatigue and failure modes.",
            "A factor of safety is meaningful only with a named failure mode, material allowables, load uncertainty and applicable standard.",
            "Finite-element results require convergence, contact/boundary review and a hand-calculation or test correlation.",
        ),
        "NASA Systems Engineering Handbook - Product Realization",
        "https://www.nasa.gov/reference/5-0-product-realization/",
    ),
    EngineeringReference(
        "thermal_fluids",
        ("termica", "calor", "temperatura", "conveccao", "conducao", "radiacao", "fluido", "pressao", "bomba"),
        (
            "Close mass, momentum and energy balances before selecting correlations or simulation settings.",
            "Separate conduction, convection and radiation paths; state material properties, geometry, boundary temperatures and uncertainty.",
            "Check regime and dimensionless groups before using a heat-transfer or pressure-loss correlation outside its validity range.",
        ),
        "NASA Glenn Conservation of Energy",
        "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/first-law-thermodynamics/",
    ),
    EngineeringReference(
        "controls_robotics",
        ("controle", "pid", "estado", "sensor", "atuador", "robotica", "robo", "telemetria", "kalman"),
        (
            "Define plant, states, inputs, outputs, disturbances, sample time, saturation and failure state before tuning a controller.",
            "Test stability margins, delay, sensor noise, actuator limits and degraded modes; nominal tracking alone is insufficient.",
            "Physical actuation needs an independent safety layer, bounded commands, watchdog, emergency stop and human authorization.",
        ),
        "NIST Measurement Science for Manufacturing Robotics",
        "https://nvlpubs.nist.gov/nistpubs/gcr/2024/NIST.GCR.24-054.pdf",
    ),
    EngineeringReference(
        "electrical_embedded",
        ("eletrica", "eletronica", "circuito", "pcb", "microcontrolador", "arduino", "motor", "bateria", "potencia", "emi"),
        (
            "Build a power budget with nominal, peak, transient and fault currents; include conversion losses, thermal limits and protection coordination.",
            "Separate signal integrity, power integrity, grounding, isolation and EMC assumptions; prototype wiring is not production evidence.",
            "Firmware controlling hardware must fail safe on reset, timeout, invalid sensor data and communication loss.",
        ),
        "NASA Electrical, Electronic, Electromechanical and Electro-Optical Parts",
        "https://nepp.nasa.gov/",
    ),
    EngineeringReference(
        "materials_manufacturing",
        ("material", "liga", "composito", "carbono", "impressao 3d", "manufatura", "solda", "usinagem", "corrosao"),
        (
            "Select material and process together using environment, load spectrum, geometry, inspectability, joining, variability and life-cycle constraints.",
            "Datasheet typical values are not design allowables; preserve heat treatment, orientation, batch and test-condition provenance.",
            "Additive parts require process qualification, orientation/porosity control, post-processing and representative coupons.",
        ),
        "NIST Materials Data and Informatics",
        "https://www.nist.gov/programs-projects/materials-data-and-informatics",
    ),
    EngineeringReference(
        "software_security",
        ("software", "codigo", "arquitetura de software", "seguranca", "cyber", "api", "firmware", "vulnerabilidade"),
        (
            "Define trust boundaries, assets, identities, least privilege, update/recovery paths and audit evidence before implementation.",
            "Secure development includes preparing the organization, protecting software, producing well-secured releases and responding to vulnerabilities.",
            "Tests should cover abuse cases, failure recovery and supply-chain integrity, not only expected functionality.",
        ),
        "NIST SP 800-218 Secure Software Development Framework",
        "https://csrc.nist.gov/pubs/sp/800/218/final",
    ),
    EngineeringReference(
        "human_safety",
        ("seguranca humana", "ergonomia", "risco", "hazard", "fmea", "fta", "exoesqueleto", "vestivel"),
        (
            "Identify hazards before optimizing performance; severity and controllability can dominate probability.",
            "Use independent protection for hazardous energy and never rely on an AI response as the sole safety control.",
            "Human-contact systems require conservative force, temperature, electrical and entrapment limits backed by applicable standards and physical tests.",
        ),
        "NASA System Safety Handbook",
        "https://ntrs.nasa.gov/citations/20120003291",
    ),
)


def _normalize(text: str) -> str:
    value = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or ""))
        if not unicodedata.combining(char)
    ).casefold()
    return " ".join(re.findall(r"[a-z0-9_+.-]+", value))


class EngineeringKnowledgeBase:
    VERSION = "engineering-core-2026-08-24"

    def retrieve(self, query: str, limit: int = 4) -> list[EngineeringReference]:
        normalized = _normalize(query)
        if not normalized:
            return []
        words = set(normalized.split())
        ranked = []
        for item in REFERENCES:
            score = 0
            for keyword in item.keywords:
                key = _normalize(keyword)
                if key in normalized:
                    score += 4 if " " in key else 2
                score += len(words & set(key.split()))
            if score:
                ranked.append((score, item.domain, item))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        return [item for _, _, item in ranked[: max(1, min(limit, 6))]]

    def context(self, query: str, limit: int = 4) -> str:
        selected = self.retrieve(query, limit)
        if not selected:
            return ""
        lines = [
            f"LOCAL ENGINEERING REFERENCE {self.VERSION}",
            "Protocol: distinguish fact/calculation/estimate/assumption; use SI units; "
            "state inputs and uncertainty; never invent coefficients or test results; "
            "for current specifications request verification; human safety outranks performance.",
        ]
        for item in selected:
            lines.append(f"\n[{item.domain}] Source: {item.source} | {item.url}")
            lines.extend(f"- {principle}" for principle in item.principles)
        return "\n".join(lines)

    def status(self) -> dict:
        return {
            "version": self.VERSION,
            "domains": sorted(item.domain for item in REFERENCES),
            "references": len(REFERENCES),
            "offline": True,
            "source_grounded": True,
        }
