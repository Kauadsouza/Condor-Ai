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
        conversas = self._memoria.buscar_conversas(texto, limite=4)

        vistos: set[int] = set()
        linhas: list[str] = []
        for fato in essenciais + relevantes:
            if fato["id"] in vistos:
                continue
            vistos.add(fato["id"])
            linhas.append(f"- [{fato['categoria']}] {fato['valor']}")

        blocos: list[str] = []
        if linhas:
            blocos.append("FATOS PESSOAIS CONFIRMADOS:\n" + "\n".join(linhas[:max_fatos + 8]))
        if conversas:
            blocos.append(
                "TRECHOS DE CONVERSAS ANTERIORES (contexto, nao prova externa):\n"
                + "\n".join(
                    f"- ({c['papel']}) {c['conteudo'][:260]}" for c in conversas
                )
            )
        if not blocos:
            return ""
        return "\n\n".join(blocos)

    async def buscar_para_ferramenta(self, consulta: str) -> dict:
        """Atende a ferramenta buscar_memoria quando o modelo chama."""
        if not consulta.strip():
            return {"ok": False, "saida": "Preciso saber o que procurar."}

        embedding = None
        if self._cerebro is not None:
            embedding = await self._cerebro.embedding(consulta)

        fatos = self._memoria.buscar_fatos(consulta, limite=10, embedding=embedding)
        conversas = self._memoria.buscar_conversas(consulta, limite=4)

        blocos: list[str] = []
        if fatos:
            blocos.append("O que eu sei:\n" + "\n".join(
                f"- [{f['categoria']}] {f['valor']}" for f in fatos))
        if conversas:
            blocos.append("Conversas passadas:\n" + "\n".join(
                f"- ({c['papel']}) {c['conteudo'][:180]}" for c in conversas))

        if not blocos:
            return {"ok": True, "saida": f"Não tenho nada guardado sobre '{consulta}'."}
        return {"ok": True, "saida": "\n\n".join(blocos)}
