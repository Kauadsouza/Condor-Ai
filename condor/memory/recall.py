"""
Recall — decide o que da memória entra na conversa.

Duas camadas:
  essenciais → os fatos mais fortes, sempre presentes (quem ele é, o que faz)
  relevantes → o que casa com a mensagem de agora, por texto e por significado

Sem isso o Condor teria mil fatos guardados e nenhum na hora certa.
"""

from __future__ import annotations

import logging

log = logging.getLogger("condor.recall")


OWNER_MEMORY_CATEGORIES = frozenset({"pessoal", "preferencia", "rotina"})
PROJECT_MEMORY_CATEGORIES = frozenset({"projeto", "tecnico", "trabalho"})


def _formatar_camadas(fatos: list[dict], limite: int) -> str:
    """Separa personalidade aprendida de conhecimento de projeto no contexto."""
    grupos = {
        "OWNER MEMORY": [],
        "PROJECT MEMORY": [],
        "OTHER CONFIRMED MEMORY": [],
    }
    for fato in fatos[:limite]:
        categoria = str(fato.get("categoria") or "").lower()
        linha = f"- [{categoria or 'geral'}] {fato.get('valor', '')}"
        if categoria in OWNER_MEMORY_CATEGORIES:
            grupos["OWNER MEMORY"].append(linha)
        elif categoria in PROJECT_MEMORY_CATEGORIES:
            grupos["PROJECT MEMORY"].append(linha)
        else:
            grupos["OTHER CONFIRMED MEMORY"].append(linha)
    return "\n".join(
        f"{nome}:\n" + "\n".join(linhas)
        for nome, linhas in grupos.items() if linhas
    )


class Recall:
    def __init__(self, memoria) -> None:
        self._memoria = memoria
        self._cerebro = None

    def ligar_cerebro(self, cerebro) -> None:
        """O embedding vem da OpenAI, então o recall precisa do cérebro.
        Ligado depois pra não criar dependência circular no boot."""
        self._cerebro = cerebro

    async def contexto_para(self, texto: str, max_fatos: int = 10) -> str:
        """Monta o bloco REFERÊNCIA que vai no prompt do sistema."""
        essenciais = self._memoria.fatos_essenciais(limite=8)

        embedding = None
        if self._cerebro is not None and len(texto) > 12:
            embedding = await self._cerebro.embedding(texto)

        relevantes = self._memoria.buscar_fatos(texto, limite=max_fatos,
                                                embedding=embedding)
        vistos: set[int] = set()
        fatos_unicos: list[dict] = []
        for fato in essenciais + relevantes:
            if fato["id"] in vistos:
                continue
            vistos.add(fato["id"])
            fatos_unicos.append(fato)

        if fatos_unicos:
            return (
                "FATOS PESSOAIS CONFIRMADOS:\n"
                + _formatar_camadas(fatos_unicos, max_fatos + 8)
            )
        # Conversas recentes já entram como histórico com papéis user/assistant.
        # Não promovemos texto bruto antigo ao prompt de sistema: memória durável
        # nesse nível é composta somente por fatos confirmados.
        return ""

    async def buscar_para_ferramenta(self, consulta: str) -> dict:
        """Atende a ferramenta buscar_memoria quando o modelo chama."""
        if not consulta.strip():
            return {"ok": False, "saida": "Preciso saber o que procurar."}

        embedding = None
        if self._cerebro is not None:
            embedding = await self._cerebro.embedding(consulta)

        fatos = self._memoria.buscar_fatos(consulta, limite=10, embedding=embedding)
        if fatos:
            return {
                "ok": True,
                "saida": "O que eu sei:\n" + _formatar_camadas(fatos, 10),
            }
        return {"ok": True, "saida": f"Não tenho nada guardado sobre '{consulta}'."}
