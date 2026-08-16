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


class Extrator:
    def __init__(self, memoria, cerebro, config) -> None:
        self._memoria = memoria
        self._cerebro = cerebro
        self._cfg = config
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
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError:
            log.debug("Extrator devolveu JSON inválido.")
            return

        await self._salvar(dados)

    async def _salvar(self, dados: dict) -> None:
        novos = 0

        for fato in (dados.get("fatos") or [])[:8]:
            categoria = str(fato.get("categoria", "pessoal")).lower()
            chave = str(fato.get("chave", "")).strip()[:80]
            valor = str(fato.get("valor", "")).strip()[:500]
            if not chave or len(valor) < 4:
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

        for rel in (dados.get("relacoes") or [])[:6]:
            de, para = str(rel.get("de", "")).strip(), str(rel.get("para", "")).strip()
            if de and para:
                self._memoria.salvar_relacao(de, para, str(rel.get("tipo", "ligado_a"))[:40])

        if novos:
            log.info("Aprendi %d fato(s) novo(s).", novos)
