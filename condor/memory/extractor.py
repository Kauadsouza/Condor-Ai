"""
Extrator — como o Condor aprende.

Depois de cada troca, o modelo rapido configurado rele a conversa e decide
o que vale guardar pra sempre. Roda em segundo plano: você nunca espera por ela.

Isso substitui o regex da versão antiga, que enchia o banco de lixo tipo
'objetivo_q_vc_me_fale'. Agora quem julga o que é fato é um modelo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

log = logging.getLogger("condor.extrator")

INSTRUCAO = """Você lê um pedaço de conversa entre o dono de um PC e o assistente dele, e extrai APENAS o que vale a pena lembrar pra sempre.

GUARDE (fato durável sobre a pessoa):
- quem ela é: nome, idade, cidade, profissão, formação, família
- o que ela faz: projetos, empresa, clientes, estudos, metas
- preferências fortes: gosta/odeia, ferramenta que usa, jeito que prefere trabalhar
- rotina: horários, hábitos, compromissos que se repetem
- decisões e combinados: "vamos fazer X assim", "sempre me chame de Y"
- configuração do próprio PC dela que valha lembrar (caminho de pasta, programa que usa)

NÃO GUARDE:
- o que foi só daquele momento ("abre o chrome", "que horas são")
- resultado de comando, conteúdo de arquivo, saída técnica
- o que o assistente disse ou fez
- suposição sua: se a pessoa não afirmou, não é fato
- noticia, resultado de pesquisa ou outro conteudo da internet; isso e fonte,
  nao memoria pessoal, a menos que o dono confirme uma decisao sobre si mesmo
- senha, chave de API, token, segredo, credencial ou codigo de autenticacao
- repetição do que já está na lista "JÁ SEI" abaixo, a não ser pra CORRIGIR

Responda só um JSON assim:
{
  "fatos": [
    {"categoria": "pessoal|trabalho|preferencia|rotina|projeto|tecnico",
     "chave": "identificador_curto_em_snake_case",
     "valor": "o fato escrito por extenso, em uma frase clara",
     "confianca": 0.0 a 1.0}
  ],
  "entidades": [
    {"nome": "Nome Próprio", "tipo": "pessoa|projeto|lugar|empresa|ferramenta",
     "cluster": "TRABALHO|PESSOAL|ESTUDOS|HABITOS|GERAL", "resumo": "uma linha"}
  ],
  "relacoes": [{"de": "Nome A", "para": "Nome B", "tipo": "trabalha_em|usa|mora_em|conhece"}]
}

Se não houver nada que valha guardar — o caso mais comum — devolva listas vazias.
Prefira guardar pouco e certo a guardar muito e errado.
A chave deve ser estável: o mesmo assunto tem que gerar a mesma chave sempre,
pra atualizar o fato em vez de duplicar."""

CATEGORIAS_VALIDAS = {"pessoal", "trabalho", "preferencia", "rotina", "projeto", "tecnico"}
TIPOS_VALIDOS = {"pessoa", "projeto", "lugar", "empresa", "ferramenta"}


def _parece_segredo(texto: str) -> bool:
    return any(re.search(pattern, texto, re.I) for pattern in (
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"\b(?:api[_ -]?key|senha|password|token|secret|chave)\s*[:=]\s*\S+",
        r"\b[A-Za-z0-9_-]{48,}\b",
    ))


def _parse_json_payload(bruto: str) -> dict | None:
    """Aceita JSON puro e tambem a cerca Markdown que modelos locais insistem em usar."""
    texto = str(bruto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.I)
        texto = re.sub(r"\s*```$", "", texto)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        return None
    try:
        dados = json.loads(texto[inicio: fim + 1])
    except json.JSONDecodeError:
        return None
    return dados if isinstance(dados, dict) else None


class Extrator:
    def __init__(self, memoria, cerebro, config, events=None) -> None:
        self._memoria = memoria
        self._cerebro = cerebro
        self._cfg = config
        self._events = events
        self._fila: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._tarefa: asyncio.Task | None = None

    def iniciar(self) -> None:
        if self._tarefa is None or self._tarefa.done():
            self._tarefa = asyncio.create_task(self._trabalhar())

    def enfileirar(self, fala_dono: str, fala_condor: str) -> None:
        """Chamado no fim de cada turno. Não bloqueia nada."""
        try:
            self._fila.put_nowait((fala_dono, fala_condor))
        except Exception:
            pass

    async def _trabalhar(self) -> None:
        while True:
            try:
                dono, condor = await self._fila.get()
                await self._processar(dono, condor)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Extrator falhou: %s", exc)

    async def _processar(self, fala_dono: str, fala_condor: str) -> None:
        if len(fala_dono.strip()) < 8:
            return   # "sim", "ok", "valeu" — não tem o que aprender

        ja_sei = self._memoria.fatos_recentes(limite=25)
        conhecido = "\n".join(f"- [{f['categoria']}] {f['chave']}: {f['valor']}"
                              for f in ja_sei) or "(nada ainda)"

        entrada = (f"JÁ SEI:\n{conhecido}\n\n"
                   f"CONVERSA DE AGORA:\n"
                   f"Dono: {fala_dono[:2500]}\n"
                   f"Assistente: {fala_condor[:1500]}")

        bruto = await self._cerebro.completar(
            INSTRUCAO, entrada,
            modelo=self._cfg.cerebro.modelo_rapido,
            json_mode=True, max_tokens=900)

        if not bruto:
            return
        dados = _parse_json_payload(bruto)
        if dados is None:
            log.debug("Extrator devolveu JSON inválido.")
            return

        await self._salvar(dados)

    async def _salvar(self, dados: dict) -> None:
        novos = 0
        entidades = 0
        relacoes = 0

        for fato in (dados.get("fatos") or [])[:8]:
            categoria = str(fato.get("categoria", "pessoal")).lower()
            chave = str(fato.get("chave", "")).strip()[:80]
            valor = str(fato.get("valor", "")).strip()[:500]
            if not chave or len(valor) < 4 or _parece_segredo(valor):
                continue
            if categoria not in CATEGORIAS_VALIDAS:
                categoria = "pessoal"
            try:
                confianca = float(fato.get("confianca", 0.8))
            except (TypeError, ValueError):
                confianca = 0.8

            embedding = await self._cerebro.embedding(valor)
            self._memoria.salvar_fato(categoria, chave, valor,
                                      max(0.1, min(1.0, confianca)),
                                      "conversa", embedding)
            novos += 1

        for ent in (dados.get("entidades") or [])[:6]:
            nome = str(ent.get("nome", "")).strip()[:80]
            tipo = str(ent.get("tipo", "")).lower()
            if not nome or tipo not in TIPOS_VALIDOS:
                continue
            self._memoria.salvar_entidade(
                nome, tipo,
                str(ent.get("cluster", "GERAL")).upper()[:20],
                str(ent.get("resumo", ""))[:200])
            entidades += 1

        for rel in (dados.get("relacoes") or [])[:6]:
            de, para = str(rel.get("de", "")).strip(), str(rel.get("para", "")).strip()
            if de and para:
                self._memoria.salvar_relacao(de, para, str(rel.get("tipo", "ligado_a"))[:40])
                relacoes += 1

        if novos or entidades or relacoes:
            log.info(
                "Memoria atualizada: %d fato(s), %d entidade(s), %d relacao(oes).",
                novos, entidades, relacoes,
            )
            if self._events is not None:
                await self._events.publish(
                    "MEMORY_LEARNED",
                    {
                        "facts": novos,
                        "entities": entidades,
                        "relations": relacoes,
                        "stats": self._memoria.estatisticas(),
                    },
                    source="memory_extractor",
                )
