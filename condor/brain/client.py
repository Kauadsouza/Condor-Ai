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
from condor.vision.local import VisaoLocal

log = logging.getLogger("condor.cerebro")

# Preço por 1 milhão de tokens (USD). Serve pro contador da interface —
# se a OpenAI mudar a tabela, é só ajustar aqui.
PRECOS = {
    "gpt-5.6-sol":         (5.00, 30.00),
    "gpt-5.6":             (5.00, 30.00),
    "gpt-5.6-terra":       (2.00, 12.00),
    "gpt-5.6-luna":        (0.20,  1.20),
    "text-embedding-3-small": (0.02, 0.0),
}


def calcular_custo(modelo: str, entrada: int, saida: int) -> float:
    base = modelo.split(":")[0]
    p_in, p_out = PRECOS.get(base, PRECOS["gpt-5.6-terra"])
    return (entrada * p_in + saida * p_out) / 1_000_000


class Cerebro:
    def __init__(self, config, memoria, guarda, recall) -> None:
        self._cfg = config
        self._memoria = memoria
        self._guarda = guarda
        self._recall = recall
        self._cliente: AsyncOpenAI | None = None
        self._audio_cliente: AsyncOpenAI | None = None
        self._visao = VisaoLocal(config)
        self.ultimo_erro: str = ""

    # ── Conexão ────────────────────────────────────────────────────────────

    @property
    def cliente(self) -> AsyncOpenAI:
        if self._cliente is None:
            if self.provedor == "local":
                self._cliente = AsyncOpenAI(
                    api_key="condor-local",
                    base_url=self._cfg.cerebro.endpoint_local,
                    timeout=90.0,
                    max_retries=1,
                )
            elif self.provedor == "openai":
                self._cliente = AsyncOpenAI(api_key=self._cfg.chave_openai, timeout=90.0,
                                            max_retries=2)
            else:
                raise RuntimeError(
                    "Sem modelo local ou chave externa — o Condor esta em modo deterministico.")
        return self._cliente

    @property
    def provedor(self) -> str:
        if self._cfg.cerebro.modelo_local.strip():
            return "local"
        if self._cfg.chave_openai:
            return "openai"
        return "offline"

    @property
    def modelo_ativo(self) -> str:
        if self.provedor == "local":
            return self._cfg.cerebro.modelo_local.strip()
        if self.provedor == "openai":
            return self._cfg.cerebro.modelo
        return "offline-deterministico"

    def reset_connection(self) -> None:
        self._cliente = None
        self._audio_cliente = None

    @property
    def audio_cliente(self) -> AsyncOpenAI:
        """Voz pode usar chave externa opcional mesmo com cerebro generativo local."""
        if self._audio_cliente is None:
            if self._cfg.chave_openai:
                self._audio_cliente = AsyncOpenAI(
                    api_key=self._cfg.chave_openai, timeout=90.0, max_retries=2
                )
            else:
                self._audio_cliente = self.cliente
        return self._audio_cliente

    @property
    def pronto(self) -> bool:
        return self.provedor != "offline"

    @property
    def memoria(self):
        """A voz e os ouvidos também registram custo — precisam do banco."""
        return self._memoria

    @property
    def modelo_visao(self) -> str:
        return self._visao.modelo

    async def visao_pronta(self) -> bool:
        return await self._visao.pronto()

    async def testar_chave(self) -> tuple[bool, str]:
        """Bate na API pra saber se a chave presta — chamado no boot."""
        if not self.pronto:
            return False, "Nenhum modelo local ou chave externa configurado"
        try:
            await self.cliente.models.retrieve(self.modelo_ativo)
            return True, f"{self.provedor}:{self.modelo_ativo}"
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
        entrada = (getattr(uso, "input_tokens", None)
                   or getattr(uso, "prompt_tokens", 0) or 0)
        saida = (getattr(uso, "output_tokens", None)
                 or getattr(uso, "completion_tokens", 0) or 0)
        try:
            custo = 0.0 if self.provedor == "local" else calcular_custo(modelo, entrada, saida)
            self._memoria.registrar_uso(modelo, entrada, saida,
                                        custo)
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
        """Loop de ferramentas pela Responses API; externo usa ``store=False``."""
        cfg = self._cfg.cerebro
        sistema = montar_prompt(self._cfg.nome_dono, memoria_relevante, modo_voz)
        resposta_final = ""
        input_items = _historico_para_responses(historico)
        schemas = ferramentas.ESQUEMAS
        if not self._cfg.cerebro.compartilhar_memoria_com_conector:
            schemas = [
                schema for schema in schemas
                if schema["function"]["name"] != "buscar_memoria"
            ]
        response_tools = [_response_tool(schema) for schema in schemas]
        safety_id = self._cfg.safety_identifier

        async def _evento(tipo: str, **dados) -> None:
            if on_evento:
                await on_evento({"tipo": tipo, **dados})

        for _ in range(cfg.max_iteracoes):
            try:
                request: dict[str, Any] = {
                    "model": self.modelo_ativo,
                    "instructions": sistema,
                    "input": input_items,
                    "tools": response_tools,
                    "max_output_tokens": cfg.max_tokens,
                }
                if self.provedor == "openai":
                    request.update({
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                        "store": False,
                        "reasoning": {"effort": "medium"},
                        "text": {"verbosity": "medium"},
                        "safety_identifier": safety_id,
                    })
                response = await self.cliente.responses.create(**request)
            except Exception as exc:
                self.ultimo_erro = str(exc)
                log.error("Erro na chamada ao conector de IA: %s", exc)
                await _evento("erro", mensagem=_erro_amigavel(exc))
                return _erro_amigavel(exc)

            self._contabilizar(self.modelo_ativo, response.usage)
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                resposta_final = (response.output_text or "").strip()
                if on_token and resposta_final:
                    await on_token(resposta_final)
                historico.append({"role": "assistant", "content": resposta_final})
                break

            input_items.extend(
                item.model_dump(exclude_none=True) for item in response.output
            )
            for call in calls:
                nome = call.name
                try:
                    args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                rotulo = ferramentas.ROTULOS.get(nome, nome)
                await _evento("ferramenta.inicio", id=call.call_id,
                              ferramenta=nome, rotulo=rotulo,
                              argumentos=_resumir_args(args))

                resultado = await self._executar_com_guarda(nome, args)
                saida = str(resultado.get("saida", ""))
                await _evento("ferramenta.fim", id=call.call_id,
                              ferramenta=nome, rotulo=rotulo,
                              ok=bool(resultado.get("ok")), saida=saida[:400])
                input_items.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": (("OK\n" if resultado.get("ok") else "FALHOU\n") + saida)[:8000],
                })
                if resultado.get("imagem_b64"):
                    if self.provedor == "local":
                        try:
                            descricao = await self._visao.analisar(
                                resultado["imagem_b64"],
                                "Analise esta captura para ajudar a concluir o pedido atual. "
                                "Transcreva textos relevantes, identifique controles e relate erros visíveis.",
                            )
                            input_items.append({
                                "role": "user",
                                "content": (
                                    "[Análise feita pelo módulo de visão local "
                                    f"{self._visao.modelo}; nenhum pixel saiu do PC]\n{descricao}"
                                ),
                            })
                        except Exception as exc:
                            log.error("Visão local falhou: %s", exc)
                            input_items.append({
                                "role": "user",
                                "content": f"[A visão local não conseguiu analisar a captura: {exc}]",
                            })
                    else:
                        input_items.append({
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "[print da tela solicitado pelo dono]"},
                                {"type": "input_image", "image_url":
                                 f"data:image/jpeg;base64,{resultado['imagem_b64']}", "detail": "high"},
                            ],
                        })

        else:
            resposta_final = "Parei no limite seguro de ferramentas antes de concluir."
            historico.append({"role": "assistant", "content": resposta_final})

        return resposta_final or "Me perdi aqui, não consegui fechar essa."

    # ── Execução com a trava ───────────────────────────────────────────────

    async def _executar_com_guarda(self, nome: str, args: dict) -> dict:
        decisao = self._guarda.avaliar(nome, args)
        exigiu_senha = decisao.requires_approval

        if not decisao.allowed or decisao.simulated:
            return {
                "ok": False,
                "saida": f"BARRADO pela politica local do Condor: {decisao.reason}",
            }
        if decisao.requires_approval:
            descricao = _descrever(nome, args)
            liberado = await self._guarda.autorizar(decisao, descricao, nome)
            if not liberado:
                return {
                    "ok": False,
                    "saida": "BARRADO: a aprovacao local exata nao foi confirmada. "
                             "Nao execute de novo; informe o dono.",
                }

        inicio = time.time()
        resultado = await ferramentas.executar(
            nome, args, contexto={"recall": self._recall})
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
            request = {
                "model": self.modelo_ativo,
                "instructions": sistema,
                "input": _historico_para_responses(historico),
                "max_output_tokens": 400,
            }
            if self.provedor == "openai":
                request["store"] = False
            resposta = await self.cliente.responses.create(**request)
            self._contabilizar(self.modelo_ativo, resposta.usage)
            texto = (resposta.output_text or "").strip()
            historico.append({"role": "assistant", "content": texto})
            return texto
        except Exception as exc:
            log.error("Falha no fecho: %s", exc)
            return "Fiz o que deu, mas travei antes de terminar."

    # ── Chamada simples, sem ferramenta (extrator, resumo) ─────────────────

    async def completar(self, sistema: str, usuario: str, modelo: str | None = None,
                        json_mode: bool = False, max_tokens: int = 800) -> str:
        modelo = self.modelo_ativo if self.provedor == "local" else (
            modelo or self._cfg.cerebro.modelo_rapido
        )
        try:
            request = {
                "model": modelo,
                "instructions": sistema,
                "input": usuario,
                "max_output_tokens": max_tokens,
            }
            if self.provedor == "openai":
                request["store"] = False
                if json_mode:
                    request["text"] = {"format": {"type": "json_object"}}
            resposta = await self.cliente.responses.create(**request)
            self._contabilizar(modelo, resposta.usage)
            return (resposta.output_text or "").strip()
        except Exception as exc:
            log.error("Falha em completar(): %s", exc)
            return ""

    async def embedding(self, texto: str) -> list[float] | None:
        try:
            r = await self.cliente.embeddings.create(
                model=self._cfg.cerebro.modelo_embedding,
                input=texto[:8000])
            tokens = getattr(r.usage, "total_tokens", 0) or 0
            custo = 0.0 if self.provedor == "local" else calcular_custo(
                self._cfg.cerebro.modelo_embedding, tokens, 0
            )
            self._memoria.registrar_uso(self._cfg.cerebro.modelo_embedding, tokens, 0,
                                        custo)
            return r.data[0].embedding
        except Exception as exc:
            log.debug("Embedding falhou: %s", exc)
            return None


# ── Auxiliares ───────────────────────────────────────────────────────────────

def _response_tool(schema: dict) -> dict:
    function = schema["function"]
    return {
        "type": "function",
        "name": function["name"],
        "description": function["description"],
        "parameters": function["parameters"],
        "strict": True,
    }


def _historico_para_responses(historico: list[dict]) -> list[dict]:
    items: list[dict] = []
    for message in historico:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or content is None:
            continue
        if isinstance(content, str):
            items.append({"role": role, "content": content})
            continue
        converted = []
        for part in content:
            if part.get("type") == "text":
                converted.append({"type": "input_text", "text": part.get("text", "")})
            elif part.get("type") == "image_url":
                image = part.get("image_url") or {}
                converted.append({
                    "type": "input_image",
                    "image_url": image.get("url", ""),
                    "detail": image.get("detail", "auto"),
                })
        if converted:
            items.append({"role": role, "content": converted})
    return items

def _resumir_args(args: dict) -> str:
    partes = []
    for k, v in args.items():
        texto = str(v).replace("\n", " ")
        partes.append(f"{k}={texto[:70]}")
    return ", ".join(partes)[:180]


def _descrever(nome: str, args: dict) -> str:
    """Resume a acao pro pedido de aprovacao.

    Precisa mostrar o alvo de verdade: aprovar 'mover' sem ver origem e destino
    nao e aprovacao, e adivinhacao.
    """
    if nome in {"mover", "copiar"}:
        alvo = f"{args.get('origem', '')} -> {args.get('destino', '')}"
    elif nome == "baixar":
        alvo = f"{args.get('url', '')} -> {args.get('destino', '')}"
    else:
        alvo = (
            args.get("caminho")
            or args.get("nome")
            or args.get("alvo")
            or args.get("url")
            or args.get("teclas")
            or args.get("titulo")
            or ""
        )
    return f"{nome}: {str(alvo)[:150]}"


def _erro_amigavel(exc: Exception) -> str:
    msg = str(exc)
    if "insufficient_quota" in msg:
        return "Sua conta da OpenAI está sem crédito. Põe uns dólares lá que eu volto."
    if "invalid_api_key" in msg or "401" in msg:
        return "A credencial guardada no cofre nao foi aceita pelo conector de IA."
    if "rate_limit" in msg or "429" in msg:
        return "O conector de IA limitou as chamadas. Tente de novo em instantes."
    if "model_not_found" in msg:
        return "O conector nao tem acesso a esse modelo. Troque em ~/.condor/config.yaml."
    if "timeout" in msg.lower() or "connection" in msg.lower():
        return "Nao consegui falar com o conector de IA. Verifique o servidor local ou a internet."
    return "O conector de IA falhou e eu nao consegui responder."
