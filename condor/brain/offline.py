"""Modo offline deterministico do Condor.

Nao tenta imitar um modelo local. Resolve apenas intencoes claras e seguras,
sem enviar texto, arquivos ou telemetria para fora do computador.
"""

from __future__ import annotations

import re
from datetime import datetime

from condor.brain import tools


async def responder_offline(texto: str, memoria, guarda) -> str:
    normalized = texto.casefold().strip()
    if re.search(r"\b(horas?|que horas)\b", normalized):
        return f"Agora sao {datetime.now():%H:%M}. Estou em modo offline."
    if re.search(r"\b(data|que dia|dia de hoje)\b", normalized):
        return f"Hoje e {datetime.now():%d/%m/%Y}. Estou em modo offline."
    if any(term in normalized for term in ("estado do pc", "estado do computador", "cpu", "memoria ram")):
        result = await tools.executar("info_sistema", {})
        return result.get("saida", "Nao consegui consultar a maquina.")
    if any(term in normalized for term in ("status da memoria", "estatisticas da memoria")):
        stats = memoria.estatisticas()
        return (
            f"Memoria do Condor: {stats.get('fatos', 0)} fatos e "
            f"{stats.get('conversas', 0)} turnos registrados."
        )
    match = re.match(r"(?:listar|mostrar)\s+(?:a\s+)?pasta\s+(.+)$", texto, re.IGNORECASE)
    if match:
        args = {"caminho": match.group(1).strip()}
        decision = guarda.avaliar("listar_pasta", args)
        if not decision.allowed:
            return f"A politica local bloqueou: {decision.reason}"
        if decision.requires_approval and not await guarda.autorizar(
            decision, f"listar pasta: {args['caminho']}"
        ):
            return "A listagem foi cancelada porque a aprovacao local nao foi confirmada."
        result = await tools.executar("listar_pasta", args)
        return result.get("saida", "Nao consegui listar a pasta.")
    return (
        "Estou em modo offline. Consigo informar hora, data, estado da maquina, "
        "estatisticas da memoria e listar uma pasta. Para raciocinio livre, desbloqueie "
        "o cofre e configure uma API de inteligencia no Condor."
    )
