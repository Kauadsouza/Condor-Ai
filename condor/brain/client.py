"""
O cérebro — conversa com a API da OpenAI e roda o loop de ferramentas.

Ciclo de cada pedido:
    modelo responde  →  pediu ferramenta?
                        sim → guarda avalia → (senha se catastrófico) → executa
                              → devolve o resultado real pro modelo → repete
                        não → é a resposta final, sai do loop

Nada de resultado inventado: o modelo só vê o que a ferramenta realmente
devolveu, e o texto que ele escreve antes de chamar a ferramenta não vira
resposta.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from condor.brain import tools as ferramentas
from condor.brain.persona import montar_prompt

log = logging.getLogger("condor.cerebro")

# Preço por 1 milhão de tokens (USD). Serve pro contador da interface —
# se a OpenAI mudar a tabela, é só ajustar aqui.
PRECOS = {
    "gpt-4o":              (2.50, 10.00),
    "gpt-4o-mini":         (0.15,  0.60),
    "gpt-4.1":             (2.00,  8.00),
    "gpt-4.1-mini":        (0.40,  1.60),
    "text-embedding-3-small": (0.02, 0.0),
}


def calcular_custo(modelo: str, entrada: int, saida: int) -> float:
    base = modelo.split(":")[0]
    p_in, p_out = PRECOS.get(base, PRECOS["gpt-4o"])
    return (entrada * p_in + saida * p_out) / 1_000_000


class Cerebro:
    def __init__(self, config, memoria, guarda, recall) -> None:
        self._cfg = config
        self._memoria = memoria
        self._guarda = guarda
        self._recall = recall
        self._cliente: AsyncOpenAI | None = None
        self.ultimo_erro: str = ""

    # ── Conexão ────────────────────────────────────────────────────────────

    @property
    def cliente(self) -> AsyncOpenAI:
        if self._cliente is None:
            if not self._cfg.chave_openai:
                raise RuntimeError(
                    "Sem OPENAI_API_KEY no .env — o Condor não tem como pensar.")
            self._cliente = AsyncOpenAI(api_key=self._cfg.chave_openai, timeout=90.0,
                                        max_retries=2)
        return self._cliente

    @property
    def pronto(self) -> bool:
        return bool(self._cfg.chave_openai)

    async def testar_chave(self) -> tuple[bool, str]:
        """Bate na API pra saber se a chave presta — chamado no boot."""
        if not self._cfg.chave_openai:
            return False, "Nenhuma chave configurada no .env"
        try:
            await self.cliente.models.retrieve(self._cfg.cerebro.modelo)
            return True, self._cfg.cerebro.modelo
        except Exception as exc:
            msg = str(exc)
            if "401" in msg or "invalid_api_key" in msg:
                return False, "Chave inválida (401)"
            if "model_not_found" in msg or "404" in msg:
                return False, f"Sua conta não tem acesso ao {self._cfg.cerebro.modelo}"
            if "insufficient_quota" in msg or "429" in msg:
                return False, "Conta sem crédito na OpenAI"
            return False, msg[:180]

    # ── Uso e custo ────────────────────────────────────────────────────────

    def _contabilizar(self, modelo: str, uso) -> None:
        if not uso:
            return
        entrada = getattr(uso, "prompt_tokens", 0) or 0
        saida = getattr(uso, "completion_tokens", 0) or 0
        try:
            self._memoria.registrar_uso(modelo, entrada, saida,
                                        calcular_custo(modelo, entrada, saida))
        except Exception:
            pass

    # ── O loop principal ───────────────────────────────────────────────────

    async def responder(
        self,
        historico: list[dict],
        memoria_relevante: str = "",
        modo_voz: bool = True,
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_evento: Callable[[dict], Awaitable[None]] | None = None,
    ) -> str:
        """Roda até ter uma resposta final. `historico` é modificado no caminho,
        acumulando as chamadas de ferramenta — é assim que o modelo lembra o que
        já tentou dentro do mesmo pedido."""
        cfg = self._cfg.cerebro
        sistema = montar_prompt(self._cfg.nome_dono, memoria_relevante, modo_voz)
        resposta_final = ""

        async def _evento(tipo: str, **dados) -> None:
            if on_evento:
                await on_evento({"tipo": tipo, **dados})

        for iteracao in range(cfg.max_iteracoes):
            mensagens = [{"role": "system", "content": sistema}] + historico

            texto = ""
            chamadas: dict[int, dict] = {}
            uso = None

            try:
                fluxo = await self.cliente.chat.completions.create(
                    model=cfg.modelo,
                    messages=mensagens,
                    tools=ferramentas.ESQUEMAS,
                    tool_choice="auto",
                    parallel_tool_calls=True,
                    temperature=cfg.temperatura,
                    max_tokens=cfg.max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )

                async for pedaco in fluxo:
                    if getattr(pedaco, "usage", None):
                        uso = pedaco.usage
                    if not pedaco.choices:
                        continue
                    delta = pedaco.choices[0].delta

                    if delta.content:
                        texto += delta.content
                        if on_token:
                            await on_token(delta.content)

                    for tc in (delta.tool_calls or []):
                        alvo = chamadas.setdefault(
                            tc.index, {"id": "", "nome": "", "args": ""})
                        if tc.id:
                            alvo["id"] = tc.id
                        if tc.function and tc.function.name:
                            alvo["nome"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            alvo["args"] += tc.function.arguments

            except Exception as exc:
                self.ultimo_erro = str(exc)
                log.error("Erro na chamada à OpenAI: %s", exc)
                await _evento("erro", mensagem=_erro_amigavel(exc))
                return _erro_amigavel(exc)

            self._contabilizar(cfg.modelo, uso)

            # ── Sem ferramenta: é a resposta final ─────────────────────────
            if not chamadas:
                resposta_final = texto.strip()
                historico.append({"role": "assistant", "content": resposta_final})
                break

            # ── Com ferramenta: o texto desta rodada é só raciocínio ───────
            historico.append({
                "role": "assistant",
                "content": texto or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["nome"], "arguments": c["args"] or "{}"}}
                    for c in chamadas.values()
                ],
            })

            imagens_pendentes: list[str] = []

            for chamada in chamadas.values():
                nome = chamada["nome"]
                try:
                    args = json.loads(chamada["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                rotulo = ferramentas.ROTULOS.get(nome, nome)
                await _evento("ferramenta.inicio", ferramenta=nome, rotulo=rotulo,
                              argumentos=_resumir_args(args))

                resultado = await self._executar_com_guarda(nome, args)
                saida = str(resultado.get("saida", ""))

                if resultado.get("imagem_b64"):
                    imagens_pendentes.append(resultado["imagem_b64"])

                await _evento("ferramenta.fim", ferramenta=nome, rotulo=rotulo,
                              ok=bool(resultado.get("ok")), saida=saida[:400])

                historico.append({
                    "role": "tool",
                    "tool_call_id": chamada["id"],
                    "content": (("OK\n" if resultado.get("ok") else "FALHOU\n") + saida)[:8000],
                })

            # Print da tela: entra como imagem de verdade pro modelo enxergar.
            for b64 in imagens_pendentes:
                historico.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "[print da tela que você acabou de tirar]"},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                    ],
                })

        else:
            # Estourou o limite de iterações — pede o fecho sem mais ferramentas.
            resposta_final = await self._fechar_sem_ferramentas(historico, sistema)

        return resposta_final or "Me perdi aqui, não consegui fechar essa."

    # ── Execução com a trava ───────────────────────────────────────────────

    async def _executar_com_guarda(self, nome: str, args: dict) -> dict:
        categoria = self._guarda.avaliar(nome, args)
        exigiu_senha = False

        if categoria:
            exigiu_senha = True
            descricao = _descrever(nome, args)
            liberado = await self._guarda.autorizar(categoria, descricao)
            if not liberado:
                return {"ok": False,
                        "saida": "BARRADO pela trava de segurança: a senha não foi "
                                 "confirmada. Não execute de novo, avise o dono."}

        inicio = time.time()
        resultado = await ferramentas.executar(
            nome, args, contexto={"recall": self._recall,
                                  "python_extra": {"memoria": self._memoria}})
        duracao = time.time() - inicio

        try:
            self._guarda.auditar(nome, json.dumps(args, ensure_ascii=False)[:500],
                                 f"{'ok' if resultado.get('ok') else 'falhou'} "
                                 f"em {duracao:.1f}s",
                                 bool(resultado.get("ok")), exigiu_senha)
        except Exception:
            pass
        return resultado

    async def _fechar_sem_ferramentas(self, historico: list[dict], sistema: str) -> str:
        historico.append({
            "role": "user",
            "content": "[Sistema: você já usou muitas ferramentas nesse pedido. "
                       "Pare de executar e responda agora, em uma ou duas frases, "
                       "o que você conseguiu fazer e o que ficou faltando.]",
        })
        try:
            resposta = await self.cliente.chat.completions.create(
                model=self._cfg.cerebro.modelo,
                messages=[{"role": "system", "content": sistema}] + historico,
                temperature=0.5, max_tokens=400,
            )
            self._contabilizar(self._cfg.cerebro.modelo, resposta.usage)
            texto = (resposta.choices[0].message.content or "").strip()
            historico.append({"role": "assistant", "content": texto})
            return texto
        except Exception as exc:
            log.error("Falha no fecho: %s", exc)
            return "Fiz o que deu, mas travei antes de terminar."

    # ── Chamada simples, sem ferramenta (extrator, resumo) ─────────────────

    async def completar(self, sistema: str, usuario: str, modelo: str | None = None,
                        json_mode: bool = False, max_tokens: int = 800) -> str:
        modelo = modelo or self._cfg.cerebro.modelo_rapido
        extras = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            resposta = await self.cliente.chat.completions.create(
                model=modelo,
                messages=[{"role": "system", "content": sistema},
                          {"role": "user", "content": usuario}],
                temperature=0.2,
                max_tokens=max_tokens,
                **extras,
            )
            self._contabilizar(modelo, resposta.usage)
            return (resposta.choices[0].message.content or "").strip()
        except Exception as exc:
            log.error("Falha em completar(): %s", exc)
            return ""

    async def embedding(self, texto: str) -> list[float] | None:
        try:
            r = await self.cliente.embeddings.create(
                model=self._cfg.cerebro.modelo_embedding,
                input=texto[:8000])
            tokens = getattr(r.usage, "total_tokens", 0) or 0
            self._memoria.registrar_uso(self._cfg.cerebro.modelo_embedding, tokens, 0,
                                        calcular_custo(self._cfg.cerebro.modelo_embedding,
                                                       tokens, 0))
            return r.data[0].embedding
        except Exception as exc:
            log.debug("Embedding falhou: %s", exc)
            return None


# ── Auxiliares ───────────────────────────────────────────────────────────────

def _resumir_args(args: dict) -> str:
    partes = []
    for k, v in args.items():
        texto = str(v).replace("\n", " ")
        partes.append(f"{k}={texto[:70]}")
    return ", ".join(partes)[:180]


def _descrever(nome: str, args: dict) -> str:
    alvo = (args.get("comando") or args.get("codigo") or args.get("caminho") or "")
    return f"{nome}: {str(alvo)[:150]}"


def _erro_amigavel(exc: Exception) -> str:
    msg = str(exc)
    if "insufficient_quota" in msg:
        return "Sua conta da OpenAI está sem crédito. Põe uns dólares lá que eu volto."
    if "invalid_api_key" in msg or "401" in msg:
        return "A chave da OpenAI no .env não está valendo. Confere ela pra mim."
    if "rate_limit" in msg or "429" in msg:
        return "A OpenAI está me segurando por excesso de chamada. Tenta de novo em instantes."
    if "model_not_found" in msg:
        return "Sua conta não tem acesso a esse modelo. Dá pra trocar no data/config.yaml."
    if "timeout" in msg.lower() or "connection" in msg.lower():
        return "Não consegui falar com a OpenAI. Deve ser a internet."
    return "Deu erro do lado da OpenAI e eu não consegui responder."
