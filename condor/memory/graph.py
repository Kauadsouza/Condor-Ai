"""
Grafo de conhecimento — entidades e relações sobre o usuário.
Fornece contexto relevante para as respostas do LLM.
"""

from __future__ import annotations

import logging
import re

from condor.memory.db import MemoryDB

log = logging.getLogger("condor.memory.graph")


class KnowledgeGraph:
    def __init__(self, db: MemoryDB) -> None:
        self._db = db

    def get_stats(self) -> dict:
        stats = self._db.get_stats()
        return {
            "nodes": stats["nodes"],
            "edges": stats["edges"],
            "turns": stats["turns"],
            "learning": True,
        }

    def get_all_entities(self) -> list[dict]:
        return self._db.get_entities()

    def get_relations(self) -> list[dict]:
        return self._db.get_relations()

    def get_relevant_context(self, query: str, max_items: int = 6) -> str:
        """
        Retorna string de contexto com entidades, preferências e conversas recentes
        relevantes para a query. Injeta memória no prompt do LLM.
        """
        entities = self._db.get_entities()
        prefs    = self._db.get_all_preferences()

        query_lower = query.lower()
        scored: list[tuple[float, str]] = []

        # Entidades do grafo
        for ent in entities:
            if ent.get("type") in ("emocao", "conceito", "area_vida"):
                # Conhecimento geral — só inclui se muito relevante
                score = _keyword_overlap(query_lower, ent["name"].lower()) * 0.5
            else:
                score = _keyword_overlap(query_lower, ent["name"].lower())
            if score > 0:
                scored.append((score, f"[{ent['cluster']}] {ent['name']} ({ent['type']})"))

        # Preferências do usuário (exclui conhecimento base genérico da busca direta)
        _GENERIC_PREFIXES = (
            # prefixos legados
            "emocao_", "psico_", "relac_", "vida_", "filo_", "condor_",
            # mega_seeder (formato "dominio:subtopico")
            "psicologia:", "emocao:", "relacionamento:", "filosofia:",
            "saude_mental:", "neurociencia:", "carreira:", "financas:",
            "saude:", "identidade:", "comportamento:", "brasil:",
            "crescimento:", "espiritualidade:", "comunicacao:", "genero:",
            "ciencia:", "tecnologia:", "self:", "economia:",
            # tech_seeder
            "cyber:", "redes:", "hacking:", "tech:", "so:", "cloud:",
            "programacao:",
            # lang_seeder
            "lang:",
        )
        for key, val in prefs.items():
            if any(key.startswith(p) for p in _GENERIC_PREFIXES):
                # Conhecimento geral — inclui apenas se query bate bem
                score = _keyword_overlap(query_lower, f"{key} {val}".lower()) * 1.5
                if score >= 0.25:
                    # Trunca pra não explodir o contexto
                    short_val = val[:300] + "…" if len(val) > 300 else val
                    scored.append((score, f"Contexto: {short_val}"))
            else:
                # Preferência específica do usuário — prioridade alta
                score = _keyword_overlap(query_lower, f"{key} {val}".lower()) * 2.0
                if score > 0:
                    scored.append((score, f"Sobre você: {key} → {val}"))

        # Conversas recentes relevantes (busca por sobreposição de palavras)
        recent_turns = self._db.get_recent_conversations(limit=40)
        for turn in recent_turns:
            score = _keyword_overlap(query_lower, turn["content"].lower())
            if score >= 0.3:
                prefix = "Você disse" if turn["role"] == "user" else "Eu disse"
                short  = turn["content"][:150].strip()
                scored.append((score * 0.8, f"{prefix}: {short}"))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Deduplica por prefixo de conteúdo
        seen, items = set(), []
        for _, text in scored:
            key = text[:60]
            if key not in seen:
                seen.add(key)
                items.append(text)
            if len(items) >= max_items:
                break

        if not items:
            return ""
        return "\n".join(f"- {i}" for i in items)

    def get_graph_data_for_ui(self) -> dict:
        """Serializa grafo para renderização no frontend."""
        entities  = self._db.get_entities()
        relations = self._db.get_relations()

        nodes = [
            {
                "id": e["id"],
                "name": e["name"],
                "type": e["type"],
                "cluster": e["cluster"],
            }
            for e in entities[:80]  # limite para não sobrecarregar o SVG
        ]
        edges = [
            {
                "from": r["from_name"],
                "to":   r["to_name"],
                "type": r["rel_type"],
            }
            for r in relations[:120]
        ]
        return {"nodes": nodes, "edges": edges}

    def add_entity(self, name: str, type: str, cluster: str = "GERAL", data: dict | None = None) -> int:
        return self._db.upsert_entity(name, type, cluster, data)

    def add_relation(self, from_name: str, to_name: str, rel_type: str) -> None:
        self._db.add_relation(from_name, to_name, rel_type)

    def get_projects(self) -> list[dict]:
        """Retorna entidades do tipo 'project' para a tela de Projetos."""
        entities = self._db.get_entities()
        return [
            {"name": e["name"], "cluster": e["cluster"], "updated": e["updated"]}
            for e in entities
            if e.get("type") == "project"
        ]

    # Tipos de entidade que só vêm do seed — não aparecem na UI como "aprendidos"
    _SEED_TYPES = {"emocao", "conceito", "area_vida"}

    def get_recent_stream(self, limit: int = 10) -> list[dict]:
        """Stream recente para a sidebar — só entidades aprendidas de conversas."""
        entities = self._db.get_entities()
        user_entities = [
            e for e in entities
            if e.get("type") not in self._SEED_TYPES
        ]
        return [
            {"name": e["name"], "cluster": e["cluster"], "updated": e["updated"]}
            for e in user_entities[:limit]
        ]


def _keyword_overlap(query: str, text: str) -> float:
    words = set(re.findall(r"\w+", query))
    target = set(re.findall(r"\w+", text))
    common = words & target
    if not common:
        return 0.0
    return len(common) / max(len(words), 1)
