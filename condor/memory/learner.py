"""
Aprendizado contínuo em background.
Após cada turno, extrai entidades, relações e fatos sobre o usuário.
"""

from __future__ import annotations

import asyncio
import logging
import re

from condor.memory.db import MemoryDB
from condor.memory.graph import KnowledgeGraph

log = logging.getLogger("condor.memory.learner")

_CLUSTER_KEYWORDS = {
    "TRABALHO": ["projeto", "trabalho", "cliente", "empresa", "reunião", "sprint", "deploy",
                 "código", "bug", "feature", "api", "banco", "servidor", "chefe", "salário",
                 "freelance", "negócio", "startup"],
    "PESSOAL":  ["família", "amigo", "namorad", "viagem", "cidade", "mudar", "morar",
                 "relacionamento", "amor", "saudade", "solidão", "sentindo", "sinto"],
    "ESTUDOS":  ["estudar", "curso", "aula", "livro", "inglês", "certificado", "aprender",
                 "faculdade", "universidade", "concurso", "prova"],
    "HÁBITOS":  ["academia", "treino", "corrida", "dormir", "acordar", "rotina", "dieta",
                 "meditação", "leitura", "exercício", "alimentação"],
}


class MemoryLearner:
    def __init__(self, db: MemoryDB, graph: KnowledgeGraph, engine) -> None:
        self._db     = db
        self._graph  = graph
        self._engine = engine

    async def learn_from_turn(self, user_text: str, assistant_text: str) -> None:
        """Chamado em background após cada turno. Extrai fatos e salva."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._extract_and_save, user_text, assistant_text
            )
        except Exception as exc:
            log.error("Erro no aprendizado: %s", exc)

    def _extract_and_save(self, user_text: str, assistant_text: str) -> None:
        # Salva o turno no banco (histórico persistente)
        self._db.save_turn("user", user_text)
        self._db.save_turn("assistant", assistant_text)

        combined = f"{user_text} {assistant_text}"

        # Entidades (projetos, pessoas, lugares)
        entities = _extract_entities(combined)
        for name, etype, cluster in entities:
            self._graph.add_entity(name, etype, cluster)

        # Fatos sobre o usuário (preferências, gostos, hábitos, situações de vida)
        prefs = _extract_user_facts(user_text)
        for key, val in prefs.items():
            self._db.set_preference(key, val)
            log.debug("Aprendi sobre você: %s = %s", key, val[:60])

        if entities:
            log.debug("Entidades: %s", [e[0] for e in entities])


def _extract_entities(text: str) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    tl = text.lower()

    # Projetos / sistemas
    for m in re.finditer(
        r"\b(?:projeto|plataforma|sistema|app|aplicativo|site|software)\s+"
        r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀ][a-záéíóúâêîôûãõçà\w]*)",
        text
    ):
        found.append((m.group(1), "project", _classify_cluster(tl)))

    # Pessoas mencionadas
    for m in re.finditer(
        r"\b(?:meu|minha|o|a|do|da|com|pro|pra)\s+"
        r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀ][a-záéíóúâêîôûãõçà]{2,})\b",
        text
    ):
        name = m.group(1)
        if name not in {"Condor", "Você", "Isso", "Uma", "Isso", "Minha", "Meu"}:
            found.append((name, "person", "PESSOAL"))

    # Lugares / cidades
    for m in re.finditer(
        r"\b(?:em|de|para|pro|pra|na|no)\s+"
        r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇÀ][a-záéíóúâêîôûãõçà]{2,})\b",
        text
    ):
        found.append((m.group(1), "place", "PESSOAL"))

    return list({f[0]: f for f in found}.values())[:12]  # dedup por nome


def _classify_cluster(text: str) -> str:
    scores = {c: 0 for c in _CLUSTER_KEYWORDS}
    for cluster, keywords in _CLUSTER_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[cluster] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "GERAL"


def _extract_user_facts(text: str) -> dict[str, str]:
    """
    Extrai fatos específicos sobre o usuário da fala dele.
    Captura: gostos, hábitos, sentimentos, situações de vida, valores, opiniões.
    """
    facts: dict[str, str] = {}
    tl = text.lower().strip()

    def _add(key: str, val: str) -> None:
        val = val.strip().rstrip(".,!?").strip()
        if val and len(val) > 2:
            facts[key] = val[:120]

    # Gostos e preferências
    for m in re.finditer(r"eu (?:gosto|curto|adoro|amo) (?:muito |demais )?de\s+(.+?)(?:\.|,|$)", tl):
        _add(f"gosta_de_{m.group(1)[:25].replace(' ','_')}", m.group(1))

    for m in re.finditer(r"eu (?:não gosto|odeio|detesto|tenho raiva) de\s+(.+?)(?:\.|,|$)", tl):
        _add(f"nao_gosta_de_{m.group(1)[:25].replace(' ','_')}", m.group(1))

    # O que usa / tem
    for m in re.finditer(r"eu (?:uso|utilizo|tenho|possuo)\s+(.+?)(?:\.|,|$)", tl):
        _add(f"usa_{m.group(1)[:25].replace(' ','_')}", m.group(1))

    # Hábitos e rotina
    for m in re.finditer(r"eu (?:costumo|acordo|durmo|treino|estudo|trabalho|leio)\s+(.+?)(?:\.|,|$)", tl):
        _add(f"habito_{m.group(1)[:25].replace(' ','_')}", m.group(1))

    # Profissão / área
    for m in re.finditer(r"(?:sou|trabalho como|sou formado em|estudo)\s+(.+?)(?:\.|,|$)", tl):
        _add("profissao", m.group(1))

    # Sentimentos expressos
    for m in re.finditer(r"(?:estou|tô|me sinto|me sinto)\s+([\w\s]{3,30})(?:\.|,|porque|mas|$)", tl):
        sentiment = m.group(1).strip()
        if len(sentiment.split()) <= 4:
            _add(f"sentimento_recente", sentiment)

    # Objetivos e metas
    for m in re.finditer(r"(?:quero|preciso|meu objetivo é|minha meta é|vou)\s+(.+?)(?:\.|,|$)", tl):
        val = m.group(1).strip()
        if 5 <= len(val) <= 100:
            _add(f"objetivo_{val[:20].replace(' ','_')}", val)

    # Valores e opiniões fortes
    for m in re.finditer(r"(?:acredito que|pra mim|na minha opinião|acho que)\s+(.+?)(?:\.|,|$)", tl):
        val = m.group(1).strip()
        if 10 <= len(val) <= 150:
            _add(f"opiniao_{val[:20].replace(' ','_')}", val)

    # Situação de vida
    for m in re.finditer(r"(?:moro em|moro com|moro sozinho|tenho \d+ anos?|nasci em)\s*(.{0,60}?)(?:\.|,|$)", tl):
        _add("situacao_vida", m.group(0).strip())

    return facts
