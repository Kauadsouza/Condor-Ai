"""
O cérebro — roteia OpenAI, Claude ou modelo local e roda o loop de ferramentas.

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
import re
import time
import unicodedata
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from openai import AsyncOpenAI

from condor.brain import tools as ferramentas
from condor.brain.anthropic import AnthropicAPIError, AnthropicMessagesClient
from condor.brain.offline import responder_offline
from condor.brain.persona import montar_prompt
from condor.memory.extractor import extrair_fatos_locais
from condor.media import LocalImageGenerator
from condor.knowledge import EngineeringKnowledgeBase
from condor.vision.local import VisaoLocal

log = logging.getLogger("condor.cerebro")


def _texto_local_normalizado(texto: str) -> str:
    value = "".join(
        char for char in unicodedata.normalize("NFKD", str(texto or ""))
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _selecionar_esquemas_locais(historico: list[dict]) -> list[dict]:
    """Entrega ao modelo local apenas capacidades relacionadas à fala atual.

    Um simples cumprimento não precisa carregar dezenas de contratos de PC,
    dispositivos e laboratório. A guarda continua avaliando toda ferramenta
    selecionada; isto reduz contexto, não reduz segurança.
    """
    fala = ""
    for mensagem in reversed(historico):
        if mensagem.get("role") == "user" and isinstance(mensagem.get("content"), str):
            fala = mensagem["content"]
            break
    texto = _texto_local_normalizado(fala)
    nomes = {"buscar_memoria"}

    def contem(*termos: str) -> bool:
        return any(termo in texto for termo in termos)

    if contem("cpu", "memoria ram", "uso da ram", "estado do pc", "estado do computador",
              "espaco em disco", "armazenamento", "bateria do pc", "info do sistema"):
        nomes.add("info_sistema")

    contexto_arquivo = contem("arquivo", "pasta", "diretorio", "diretório", ".pdf", "downloads", "documentos")
    if contexto_arquivo:
        if contem("listar", "liste", "mostrar a pasta", "mostre a pasta", "conteudo da pasta", "conteúdo da pasta"):
            nomes.add("listar_pasta")
        if contem("buscar", "procurar", "encontrar", "localizar"):
            nomes.add("buscar_arquivos")
        if contem("ler", "leia", "conteudo do arquivo", "conteúdo do arquivo", "resumir", "abra o arquivo"):
            nomes.update({"ler_arquivo", "ler_pdf"})
        if contem("abrir", "abra"):
            nomes.add("abrir")
        if contem("escrever", "criar arquivo", "salvar arquivo", "edite o arquivo", "editar o arquivo"):
            nomes.add("escrever_arquivo")
        if contem("deletar", "excluir", "apagar"):
            nomes.add("deletar")
        if contem("mover"):
            nomes.add("mover")
        if contem("copiar"):
            nomes.add("copiar")
        if re.search(r"\b(?:baixar|baixe|download)\b", texto):
            nomes.add("baixar")

    if contem("janela", "aplicativo", "programa", "navegador", "chrome", "edge"):
        nomes.add("listar_janelas")
        if contem("abrir", "iniciar"):
            nomes.add("abrir")
        if contem("fechar", "encerre"):
            nomes.add("fechar_app")
        if contem("focar", "trazer para frente", "mudar para"):
            nomes.add("focar_janela")

    if contem("captura de tela", "screenshot", "print da tela"):
        nomes.add("screenshot")
    if contem("clique", "clicar"):
        nomes.add("clicar")
    if contem("digite", "digitar"):
        nomes.add("digitar")
    if contem("atalho de teclado", "pressione as teclas"):
        nomes.add("atalho")
    if contem("clipboard", "area de transferencia", "área de transferência"):
        nomes.add("ler_clipboard")
        if contem("copie", "copiar", "escreva"):
            nomes.add("escrever_clipboard")

    if contem("projeto", "condor x", "regiao", "região", "peca", "peça"):
        nomes.update({"condor_estado", "condor_abrir_projeto", "condor_selecionar_regiao"})
        if contem("rascunho", "nova peca", "nova peça", "criar peca", "criar peça"):
            nomes.add("condor_criar_rascunho")
    if contem("codigo", "código", "programacao", "programação", "revisao", "revisão"):
        nomes.update({"condor_estado", "condor_salvar_codigo", "condor_historico_codigo"})
        if contem("restaurar", "voltar revisao", "voltar revisão"):
            nomes.add("condor_restaurar_codigo")
    if contem("laboratorio", "laboratório", "experimento"):
        nomes.update({"condor_estado", "condor_criar_experimento", "condor_atualizar_experimento"})
    if contem("dispositivo", "arduino", "serial", "porta usb"):
        nomes.update({
            "condor_estado", "condor_buscar_dispositivos", "condor_conectar_dispositivo",
            "condor_desconectar_dispositivo",
        })

    return [
        schema for schema in ferramentas.ESQUEMAS
        if schema["function"]["name"] in nomes
    ]

# Preço por 1 milhão de tokens (USD). Serve pro contador da interface —
# se a OpenAI mudar a tabela, é só ajustar aqui.
PRECOS = {
    "gpt-5.6-sol":         (5.00, 30.00),
    "gpt-5.6":             (5.00, 30.00),
    "gpt-5.6-terra":       (2.00, 12.00),
    "gpt-5.6-luna":        (0.20,  1.20),
    "text-embedding-3-small": (0.02, 0.0),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def calcular_custo(modelo: str, entrada: int, saida: int) -> float:
    base = modelo.split(":")[0]
    if base.startswith("claude-haiku-4-5"):
        base = "claude-haiku-4-5"
    price = PRECOS.get(base)
    # Modelo novo ainda sem tabela confirmada: melhor mostrar custo pendente
    # que inventar o preço de outro modelo.
    if price is None:
        return 0.0
    p_in, p_out = price
    return (entrada * p_in + saida * p_out) / 1_000_000


class Cerebro:
    def __init__(self, config, memoria, guarda, recall) -> None:
        self._cfg = config
        self._memoria = memoria
        self._guarda = guarda
        self._recall = recall
        self._cliente: AsyncOpenAI | None = None
        self._audio_cliente: AsyncOpenAI | None = None
        self._anthropic: AnthropicMessagesClient | None = None
        self._visao = VisaoLocal(config)
        self._imagem = LocalImageGenerator(config)
        self._engineering = EngineeringKnowledgeBase()
        self._image_prompt_client: AsyncOpenAI | None = None
        self._orchestrator = None
        self._provider_tests: dict[str, dict[str, Any]] = {
            name: {"verified": None, "detail": "ainda não testado", "tested_at": None}
            for name in ("openai", "claude", "local")
        }
        self.ultimas_fontes: list[dict[str, str]] = []
        self.ultimo_erro: str = ""

    def ligar_orquestrador(self, orchestrator) -> None:
        """Conecta as ferramentas internas somente depois que o Core terminou o boot."""
        self._orchestrator = orchestrator

    # ── Conexão ────────────────────────────────────────────────────────────

    @property
    def cliente(self) -> AsyncOpenAI:
        if self._cliente is None:
            if self.provedor == "local":
                self._cliente = AsyncOpenAI(
                    api_key="condor-local",
                    base_url=self._cfg.cerebro.endpoint_local,
                    timeout=120.0,
                    max_retries=0,
                )
            elif self.provedor == "openai":
                self._cliente = AsyncOpenAI(api_key=self._cfg.chave_openai, timeout=90.0,
                                            max_retries=2)
            else:
                raise RuntimeError(
                    "Sem modelo local ou chave externa — o Condor esta em modo deterministico.")
        return self._cliente

    @property
    def anthropic(self) -> AnthropicMessagesClient:
        if self._anthropic is None:
            self._anthropic = AnthropicMessagesClient(self._cfg.chave_anthropic, timeout=90.0)
        return self._anthropic

    @property
    def provedor(self) -> str:
        preferred = self._cfg.cerebro.provedor_preferido
        if preferred == "openai" and self._cfg.chave_openai:
            return "openai"
        if preferred == "claude" and self._cfg.chave_anthropic:
            return "claude"
        if preferred == "local" and self._cfg.cerebro.modelo_local.strip():
            return "local"
        if preferred in {"openai", "claude", "local"}:
            return "offline"
        if self._cfg.cerebro.modelo_local.strip():
            return "local"
        if self._cfg.chave_openai:
            return "openai"
        if self._cfg.chave_anthropic:
            return "claude"
        return "offline"

    @property
    def connector_state(self) -> dict[str, Any]:
        web_research = {
            "openai": "hosted_with_sources",
            "local": "public_fallback",
            "claude": "public_fallback",
        }.get(self.provedor, "unavailable")
        selected = self.provedor if self.provedor != "offline" else self._cfg.cerebro.provedor_preferido
        providers = {
            "openai": {
                "configured": bool(self._cfg.chave_openai),
                "model": self._cfg.cerebro.modelo,
                **self._provider_tests["openai"],
            },
            "claude": {
                "configured": bool(self._cfg.chave_anthropic),
                "model": self._cfg.cerebro.modelo_claude,
                **self._provider_tests["claude"],
            },
            "local": {
                "configured": bool(self._cfg.cerebro.modelo_local.strip()),
                "model": self._cfg.cerebro.modelo_local.strip(),
                "endpoint": self._cfg.cerebro.endpoint_local,
                **self._provider_tests["local"],
            },
        }
        selected_test = providers.get(selected, {})
        return {
            "preferred": self._cfg.cerebro.provedor_preferido,
            "selected": selected,
            "external_model": self._cfg.cerebro.modelo,
            "external_key_configured": bool(self._cfg.chave_openai),
            "claude_model": self._cfg.cerebro.modelo_claude,
            "claude_key_configured": bool(self._cfg.chave_anthropic),
            "local_model_configured": bool(self._cfg.cerebro.modelo_local.strip()),
            "picovoice_key_configured": bool(self._cfg.chave_picovoice),
            "memory_sharing": bool(self._cfg.cerebro.compartilhar_memoria_com_conector),
            "automatic_learning": bool(self._cfg.cerebro.aprendizado_automatico_por_conector),
            "orchestrator_ready": self._orchestrator is not None,
            "verified": selected_test.get("verified"),
            "detail": selected_test.get("detail", "provedor não configurado"),
            "providers": providers,
            "web_research": web_research,
        }

    @property
    def modelo_ativo(self) -> str:
        if self.provedor == "local":
            return self._cfg.cerebro.modelo_local.strip()
        if self.provedor == "openai":
            return self._cfg.cerebro.modelo
        if self.provedor == "claude":
            return self._cfg.cerebro.modelo_claude
        return "offline-deterministico"

    def reset_connection(self) -> None:
        self._cliente = None
        self._audio_cliente = None
        self._anthropic = None
        self._provider_tests = {
            name: {"verified": None, "detail": "ainda não testado", "tested_at": None}
            for name in ("openai", "claude", "local")
        }

    def mark_connection_test(self, ok: bool, detail: str, provider: str | None = None) -> tuple[bool, str]:
        """Mantém o status visual alinhado ao último teste real do conector."""
        selected = provider or self.provedor
        if selected in self._provider_tests:
            self._provider_tests[selected] = {
                "verified": bool(ok), "detail": str(detail)[:180], "tested_at": time.time(),
            }
        if not ok:
            self.ultimo_erro = str(detail)[:500]
        return bool(ok), str(detail)[:180]

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
        provider = self.provedor
        if provider == "offline":
            return False
        # Depois de uma falha real, nao repete a mesma tentativa em todo turno.
        # O local ganha uma nova tentativa após um intervalo curto: reiniciar o
        # Ollama não pode exigir reiniciar também o Condor inteiro.
        teste = self._provider_tests[provider]
        if teste.get("verified") is False:
            ultima = float(teste.get("tested_at") or 0.0)
            return provider == "local" and time.time() - ultima >= 20.0
        return True

    @property
    def memoria(self):
        """A voz e os ouvidos também registram custo — precisam do banco."""
        return self._memoria

    @property
    def modelo_visao(self) -> str:
        return self._visao.modelo

    async def visao_pronta(self) -> bool:
        return await self._visao.pronto()

    async def analisar_imagem(self, imagem_b64: str, pedido: str = "") -> str:
        """Analisa um quadro no modelo multimodal local configurado."""
        return await self._visao.analisar(imagem_b64, pedido)

    async def gerar_imagem(self, prompt: str, *, size: str = "1024x1024",
                           quality: str = "medium") -> dict[str, Any]:
        """Melhora o prompt e gera no PC sem enviar texto ou imagem a nuvem."""
        enhanced = await self._melhorar_prompt_imagem_local(prompt)
        result = await self._imagem.generate(enhanced, size=size, quality=quality)
        result["prompt_enhanced_locally"] = enhanced != " ".join(str(prompt or "").split())
        return result

    async def _melhorar_prompt_imagem_local(self, prompt: str) -> str:
        """Traduz/estrutura pedidos em portugues usando somente o Ollama local.

        O endpoint e validado novamente aqui: mesmo que um conector externo
        esteja selecionado para o chat, prompts de imagem nunca usam esse
        conector. Se o modelo local estiver desligado, a geracao continua com
        um enriquecimento deterministico.
        """
        clean = " ".join(str(prompt or "").split()).strip()
        fallback = (
            f"{clean}. coherent composition, precise anatomy and geometry, detailed materials, "
            "natural lighting, sharp focus, high visual fidelity, no text, no watermark"
        )
        endpoint = str(self._cfg.cerebro.endpoint_local or "").strip()
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1", "localhost", "::1"
        } or not self._cfg.cerebro.modelo_local.strip():
            return fallback
        try:
            if self._image_prompt_client is None:
                self._image_prompt_client = AsyncOpenAI(
                    api_key="condor-local-image-prompt",
                    base_url=endpoint,
                    timeout=35.0,
                    max_retries=0,
                )
            response = await self._image_prompt_client.chat.completions.create(
                model=self._cfg.cerebro.modelo_local.strip(),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a local image prompt editor. Rewrite the user's request as one "
                            "concise English diffusion prompt. Preserve subject and intent; add concrete "
                            "composition, camera/framing, lighting, materials, environment and style only "
                            "when compatible. Do not add brands, prose, explanations or quotation marks."
                        ),
                    },
                    {"role": "user", "content": clean},
                ],
                temperature=0.25,
                max_tokens=220,
            )
            candidate = " ".join((response.choices[0].message.content or "").split()).strip()
            if 20 <= len(candidate) <= 1800:
                return candidate
        except Exception as exc:
            log.info("Editor local de prompt indisponivel; usando fallback: %s", exc)
        return fallback

    @property
    def image_generator_state(self) -> dict[str, Any]:
        return self._imagem.status()

    @property
    def engineering_knowledge_state(self) -> dict[str, Any]:
        return self._engineering.status()

    async def testar_chave(self, provider: str | None = None) -> tuple[bool, str]:
        """Valida um conector real sem trocar o provedor ativo do Condor."""
        target = provider or self.provedor
        models = {
            "openai": self._cfg.cerebro.modelo,
            "claude": self._cfg.cerebro.modelo_claude,
            "local": self._cfg.cerebro.modelo_local.strip(),
        }
        configured = {
            "openai": bool(self._cfg.chave_openai),
            "claude": bool(self._cfg.chave_anthropic),
            "local": bool(models["local"]),
        }
        if target not in configured or not configured[target]:
            selected = target if target in configured else self._cfg.cerebro.provedor_preferido
            return self.mark_connection_test(
                False, f"{selected}: credencial ou modelo não configurado", selected
            )
        model = models[target]
        try:
            if target == "claude":
                client = AnthropicMessagesClient(self._cfg.chave_anthropic, timeout=90.0)
                response = await client.create(
                    model=model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "Responda apenas OK."}],
                )
                if response.get("type") != "message" or not isinstance(response.get("content"), list):
                    raise AnthropicAPIError("Resposta incompatível da Anthropic")
            else:
                client = AsyncOpenAI(
                    api_key=self._cfg.chave_openai if target == "openai" else "condor-local",
                    base_url=(self._cfg.cerebro.endpoint_local if target == "local" else None),
                    timeout=90.0,
                    max_retries=2 if target == "openai" else 1,
                )
                await client.models.retrieve(model)
            self.ultimo_erro = ""
            return self.mark_connection_test(True, f"{target}:{model}", target)
        except Exception as exc:
            msg = str(exc)
            status = getattr(exc, "status", 0) or getattr(exc, "status_code", 0)
            if status == 401 or "401" in msg or "invalid_api_key" in msg:
                return self.mark_connection_test(False, f"{target}: chave inválida (401)", target)
            if "model_not_found" in msg or "404" in msg:
                return self.mark_connection_test(
                    False, f"{target}: conta sem acesso ao {model}", target
                )
            if "insufficient_quota" in msg or status == 429 or "429" in msg:
                return self.mark_connection_test(False, f"{target}: limite ou crédito indisponível", target)
            return self.mark_connection_test(False, f"{target}: {msg[:150]}", target)

    async def testar_conectores(self) -> dict[str, dict[str, Any]]:
        """Testa todos os conectores configurados sem tratar ausência opcional como erro."""
        results: dict[str, dict[str, Any]] = {}
        for provider, configured in (
            ("openai", bool(self._cfg.chave_openai)),
            ("claude", bool(self._cfg.chave_anthropic)),
            ("local", bool(self._cfg.cerebro.modelo_local.strip())),
        ):
            if not configured:
                results[provider] = {
                    "configured": False, "verified": None, "detail": "não configurado"
                }
                continue
            ok, detail = await self.testar_chave(provider)
            results[provider] = {"configured": True, "verified": ok, "detail": detail}
        return results

    # ── Uso e custo ────────────────────────────────────────────────────────

    def _contabilizar(self, modelo: str, uso) -> None:
        if not uso:
            return
        if isinstance(uso, dict):
            entrada = int(uso.get("input_tokens") or uso.get("prompt_tokens") or 0)
            saida = int(uso.get("output_tokens") or uso.get("completion_tokens") or 0)
        else:
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
        self.ultimas_fontes = []
        pedido_atual = ""
        for mensagem in reversed(historico):
            if mensagem.get("role") == "user" and isinstance(mensagem.get("content"), str):
                pedido_atual = mensagem["content"]
                break
        sistema = montar_prompt(
            self._cfg.nome_dono,
            memoria_relevante,
            modo_voz,
            mensagem_atual=pedido_atual,
            contexto_estruturado=memoria_relevante,
            conhecimento_tecnico=self._engineering.context(pedido_atual),
        )
        if self.provedor == "claude":
            return await self._responder_claude(
                historico, sistema, on_token=on_token, on_evento=on_evento
            )
        resposta_final = ""
        input_items = _historico_para_responses(historico)
        schemas = (
            _selecionar_esquemas_locais(historico)
            if self.provedor == "local" else ferramentas.ESQUEMAS
        )
        response_tools = [_response_tool(schema) for schema in schemas]
        # A pesquisa hospedada devolve fontes e citacoes no proprio Responses
        # API. O conector local continua usando buscar_web/ler_site, pois
        # servidores locais compativeis normalmente nao implementam web_search.
        if self.provedor == "openai":
            response_tools.append({"type": "web_search"})
        safety_id = self._cfg.safety_identifier

        async def _evento(tipo: str, **dados) -> None:
            if on_evento:
                await on_evento({"tipo": tipo, **dados})

        # Modelos locais pequenos nem sempre obedecem ao uso de ferramentas e
        # podem responder de memoria mesmo diante de "pesquise na internet".
        # Quando o pedido e explicito, o nucleo faz a busca antes da geracao e
        # entrega o resultado real ao modelo. A decisao de verificar deixa de
        # depender da boa vontade do modelo.
        consulta_web = _consulta_web_explicita(historico) if self.provedor == "local" else ""
        if consulta_web:
            call_id = f"web-preflight-{int(time.time() * 1000)}"
            await _evento(
                "ferramenta.inicio", id=call_id, ferramenta="buscar_web",
                rotulo="pesquisando na internet", argumentos=consulta_web[:180],
            )
            resultado_web = await self._executar_com_guarda(
                "buscar_web", {"consulta": consulta_web, "limite": 4}
            )
            saida_web = str(resultado_web.get("saida", ""))
            if resultado_web.get("ok"):
                self.ultimas_fontes = _mesclar_fontes(
                    self.ultimas_fontes, _extrair_fontes_texto(saida_web)
                )
            await _evento(
                "ferramenta.fim", id=call_id, ferramenta="buscar_web",
                rotulo="pesquisando na internet", ok=bool(resultado_web.get("ok")),
                saida=saida_web[:400],
            )
            if resultado_web.get("ok"):
                pedido_original = ""
                for mensagem in reversed(historico):
                    if mensagem.get("role") == "user" and isinstance(
                        mensagem.get("content"), str
                    ):
                        pedido_original = mensagem["content"]
                        break
                resposta_pesquisa = await self.completar(
                    sistema + (
                        "\n\nTAREFA DE PESQUISA ATUAL\n"
                        "Use somente os resultados publicos atuais fornecidos. Nao use uma "
                        "lembranca antiga quando ela contradizer a pesquisa. Nao invente. "
                        "Os links aparecerao como fontes clicaveis na interface, entao cite "
                        "os nomes das fontes sem copiar URLs longas no texto."
                    ),
                    f"PEDIDO:\n{pedido_original[:1200]}\n\nRESULTADOS ATUAIS:\n{saida_web[:5200]}",
                    max_tokens=320,
                )
                if resposta_pesquisa:
                    self.mark_connection_test(
                        True, f"{self.provedor}:{self.modelo_ativo}", self.provedor
                    )
                    if on_token:
                        await on_token(resposta_pesquisa)
                    historico.append({"role": "assistant", "content": resposta_pesquisa})
                    return resposta_pesquisa
                # A internet respondeu, mas a redacao local falhou. Ainda
                # entregamos evidencias reais em vez de inventar uma resposta.
                fallback = (
                    "A pesquisa na internet funcionou e as fontes atuais estao abaixo, "
                    "mas o modelo local demorou demais para redigir a resposta."
                )
                if on_token:
                    await on_token(fallback)
                historico.append({"role": "assistant", "content": fallback})
                return fallback
            input_items.append({
                "role": "user",
                "content": (
                    "[PESQUISA PUBLICA EXECUTADA AGORA PELO NUCLEO DO CONDOR]\n"
                    + (("RESULTADO VERIFICAVEL:\n" + saida_web) if resultado_web.get("ok")
                       else ("A PESQUISA FALHOU:\n" + saida_web))
                    + "\n[Responda ao pedido original usando este resultado atual. "
                      "Nao repita conhecimento antigo que contradiga as fontes.]"
                )[:9000],
            })
            # A busca ja terminou. Nao reenviar dezenas de esquemas de
            # ferramentas ao modelo local reduz muito o contexto e impede que
            # ele repita a mesma pesquisa em outro loop.
            response_tools = []

        for _ in range(cfg.max_iteracoes):
            try:
                request: dict[str, Any] = {
                    "model": self.modelo_ativo,
                    "instructions": sistema,
                    "input": input_items,
                    "tools": response_tools,
                    "max_output_tokens": min(cfg.max_tokens, 650) if consulta_web else cfg.max_tokens,
                }
                if self.provedor == "openai":
                    request.update({
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                        "store": False,
                        "reasoning": {"effort": "medium"},
                        "text": {"verbosity": "medium"},
                        "safety_identifier": safety_id,
                        "include": ["web_search_call.action.sources"],
                    })
                response = await self.cliente.responses.create(**request)
            except Exception as exc:
                self.ultimo_erro = str(exc)
                self.mark_connection_test(
                    False, f"{self.provedor}: {str(exc)[:150]}", self.provedor
                )
                log.error("Erro na chamada ao conector de IA: %s", exc)
                if self.provedor == "local":
                    pedido = ""
                    for mensagem in reversed(historico):
                        if (mensagem.get("role") == "user"
                                and isinstance(mensagem.get("content"), str)):
                            pedido = mensagem["content"]
                            break
                    fatos = extrair_fatos_locais(pedido)
                    fallback = await responder_offline(
                        pedido, self._memoria, self._guarda,
                        aprendizado={"saved": fatos} if fatos else None,
                    )
                    if on_token and fallback:
                        await on_token(fallback)
                    historico.append({"role": "assistant", "content": fallback})
                    return fallback
                return _erro_amigavel(exc)

            self.mark_connection_test(
                True, f"{self.provedor}:{self.modelo_ativo}", self.provedor
            )
            self._contabilizar(self.modelo_ativo, response.usage)
            self.ultimas_fontes = _mesclar_fontes(
                self.ultimas_fontes, _extrair_fontes_web(response)
            )
            for item in response.output:
                if getattr(item, "type", "") == "web_search_call":
                    call_id = str(getattr(item, "id", "web-search"))
                    await _evento(
                        "ferramenta.inicio", id=call_id, ferramenta="web_search",
                        rotulo="pesquisando na internet", argumentos="fontes publicas",
                    )
                    await _evento(
                        "ferramenta.fim", id=call_id, ferramenta="web_search",
                        rotulo="pesquisando na internet", ok=True,
                        saida=f"{len(self.ultimas_fontes)} fonte(s)",
                    )
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
                if resultado.get("ok") and nome in {"buscar_web", "ler_site"}:
                    self.ultimas_fontes = _mesclar_fontes(
                        self.ultimas_fontes, _extrair_fontes_texto(saida)
                    )
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

    async def _responder_claude(
        self,
        historico: list[dict],
        sistema: str,
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_evento: Callable[[dict], Awaitable[None]] | None = None,
    ) -> str:
        """Loop de ferramentas nativo da Messages API da Anthropic."""
        messages = _historico_para_anthropic(historico)
        schemas = ferramentas.ESQUEMAS
        tools = [_anthropic_tool(schema) for schema in schemas]

        async def _evento(tipo: str, **dados) -> None:
            if on_evento:
                await on_evento({"tipo": tipo, **dados})

        for _ in range(self._cfg.cerebro.max_iteracoes):
            try:
                response = await self.anthropic.create(
                    model=self.modelo_ativo,
                    max_tokens=self._cfg.cerebro.max_tokens,
                    system=sistema,
                    messages=messages,
                    tools=tools,
                )
            except Exception as exc:
                self.ultimo_erro = str(exc)[:500]
                self.mark_connection_test(False, f"claude: {str(exc)[:150]}", "claude")
                log.error("Erro na chamada ao Claude: %s", exc)
                return _erro_amigavel(exc)

            self._contabilizar(self.modelo_ativo, response.get("usage"))
            blocks = response.get("content") or []
            if not isinstance(blocks, list):
                self.mark_connection_test(False, "claude: resposta sem blocos de conteúdo", "claude")
                return "O Claude respondeu em um formato incompatível; registrei no Diagnóstico."
            tool_calls = [item for item in blocks if isinstance(item, dict) and item.get("type") == "tool_use"]
            texts = [
                str(item.get("text") or "") for item in blocks
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if not tool_calls:
                final = "\n".join(text for text in texts if text).strip()
                self.mark_connection_test(True, f"claude:{self.modelo_ativo}", "claude")
                if on_token and final:
                    await on_token(final)
                historico.append({"role": "assistant", "content": final})
                return final or "O Claude não devolveu texto; registrei a resposta no Diagnóstico."

            messages.append({"role": "assistant", "content": blocks})
            results = []
            for call in tool_calls:
                name = str(call.get("name") or "")
                args = call.get("input") if isinstance(call.get("input"), dict) else {}
                call_id = str(call.get("id") or "tool")
                label = ferramentas.ROTULOS.get(name, name)
                await _evento(
                    "ferramenta.inicio", id=call_id, ferramenta=name,
                    rotulo=label, argumentos=_resumir_args(args),
                )
                result = await self._executar_com_guarda(name, args)
                output = str(result.get("saida", ""))
                await _evento(
                    "ferramenta.fim", id=call_id, ferramenta=name, rotulo=label,
                    ok=bool(result.get("ok")), saida=output[:400],
                )
                content: list[dict[str, Any]] = [{"type": "text", "text": output[:8000]}]
                image_b64 = result.get("imagem_b64")
                if image_b64:
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                    })
                results.append({
                    "type": "tool_result", "tool_use_id": call_id,
                    "content": content, "is_error": not bool(result.get("ok")),
                })
            messages.append({"role": "user", "content": results})

        final = "Parei no limite seguro de ferramentas antes de concluir."
        historico.append({"role": "assistant", "content": final})
        return final

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
            nome, args, contexto={"recall": self._recall, "orchestrator": self._orchestrator})
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
        modelo = self.modelo_ativo if self.provedor in {"local", "claude"} else (
            modelo or self._cfg.cerebro.modelo_rapido
        )
        try:
            if self.provedor == "claude":
                if json_mode:
                    sistema += "\nRetorne somente JSON válido, sem bloco Markdown."
                response = await self.anthropic.create(
                    model=modelo, system=sistema, max_tokens=max_tokens,
                    messages=[{"role": "user", "content": usuario}],
                )
                self._contabilizar(modelo, response.get("usage"))
                return "\n".join(
                    str(item.get("text") or "") for item in response.get("content", [])
                    if isinstance(item, dict) and item.get("type") == "text"
                ).strip()
            if self.provedor == "local" and json_mode:
                sistema += (
                    "\nRetorne somente um objeto JSON valido. "
                    "Nao use bloco Markdown, comentario ou texto antes/depois do JSON."
                )
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
            self.mark_connection_test(
                False, f"{self.provedor}: {str(exc)[:150]}", self.provedor
            )
            return ""

    async def embedding(self, texto: str) -> list[float] | None:
        # Ollama/Claude nao compartilham automaticamente o modelo de embeddings
        # configurado para OpenAI. Evita uma requisicao fadada a falhar em cada
        # turno; o recall textual local continua funcionando normalmente.
        if self.provedor in {"local", "claude"}:
            return None
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


def _anthropic_tool(schema: dict) -> dict:
    function = schema["function"]
    return {
        "name": function["name"],
        "description": function["description"],
        "input_schema": function["parameters"],
    }


def _como_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            result = dump(exclude_none=True)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return {}


def _extrair_fontes_web(response: Any) -> list[dict[str, str]]:
    """Extrai URLs citadas/consultadas sem depender da classe exata do SDK."""
    payload = _como_dict(response)
    fontes: list[dict[str, str]] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations") or []:
                if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
                    fontes.append({
                        "url": str(annotation.get("url") or ""),
                        "title": str(annotation.get("title") or ""),
                    })
        action = item.get("action") or {}
        if isinstance(action, dict):
            for source in action.get("sources") or []:
                if isinstance(source, dict):
                    fontes.append({
                        "url": str(source.get("url") or ""),
                        "title": str(source.get("title") or ""),
                    })
    return _mesclar_fontes([], fontes)


def _extrair_fontes_texto(saida: str) -> list[dict[str, str]]:
    """Transforma a saida de buscar_web/ler_site em fontes clicaveis na UI."""
    import re

    fontes: list[dict[str, str]] = []
    titulo = ""
    for linha in str(saida or "").splitlines():
        match_titulo = re.match(r"\s*\d+\.\s+(.+?)\s*$", linha)
        if match_titulo:
            titulo = match_titulo.group(1).strip()
            continue
        page_title = re.match(r"\s*TITULO:\s*(.+?)\s*$", linha, re.I)
        if page_title:
            titulo = page_title.group(1).strip()
            continue
        match_url = re.match(
            r"\s*(?:URL(?:\s+FINAL)?:\s*)?(https?://\S+)", linha, re.I
        )
        if match_url:
            fontes.append({
                "url": match_url.group(1).rstrip(".,);]"),
                "title": titulo,
            })
            titulo = ""
    return _mesclar_fontes([], fontes)


def _consulta_web_explicita(historico: list[dict]) -> str:
    """Retorna uma consulta curta somente quando o dono pediu pesquisa explicitamente."""
    texto = ""
    for mensagem in reversed(historico):
        if mensagem.get("role") == "user" and isinstance(mensagem.get("content"), str):
            texto = mensagem["content"].strip()
            break
    if not texto or not re.search(
        r"\b(pesquis\w*|procure|buscar?|busque)\b.*\b(internet|web|online|fonte\w*)\b",
        texto, re.I | re.S,
    ):
        return ""
    consulta = re.sub(
        r"^\s*(?:pesquise|pesquisar|procure|buscar|busque)\s*"
        r"(?:na|no|pela|a)?\s*(?:internet|web|online)?\s*",
        "", texto, flags=re.I,
    )
    consulta = re.split(
        r"\b(?:responda|mostre|cite|traga)\b", consulta, maxsplit=1, flags=re.I
    )[0]
    consulta = re.sub(r"^\s*(?:a|o|as|os)\s+", "", consulta, flags=re.I)
    consulta = re.sub(r"\s+(?:e|com)\s*$", "", consulta, flags=re.I)
    return (consulta.strip(" .,:;?!") or texto)[:500]


def _mesclar_fontes(
    atuais: list[dict[str, str]], novas: list[dict[str, str]], limite: int = 12
) -> list[dict[str, str]]:
    from urllib.parse import urlsplit

    resultado: list[dict[str, str]] = []
    vistas: set[str] = set()
    for source in [*atuais, *novas]:
        url = str(source.get("url") or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or url in vistas:
            continue
        vistas.add(url)
        resultado.append({
            "url": url[:2000],
            "title": str(source.get("title") or parsed.hostname)[:240],
        })
        if len(resultado) >= limite:
            break
    return resultado


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


def _historico_para_anthropic(historico: list[dict]) -> list[dict]:
    messages: list[dict] = []
    for message in historico:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or content is None:
            continue
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        converted: list[dict] = []
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                converted.append({"type": "text", "text": str(part.get("text") or "")})
            elif part.get("type") == "image_url":
                image = part.get("image_url") or {}
                url = str(image.get("url") or "")
                if url.startswith("data:image/") and ";base64," in url:
                    header, data = url.split(",", 1)
                    media_type = header[5:].split(";", 1)[0]
                    converted.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    })
                elif url.startswith("https://"):
                    converted.append({"type": "image", "source": {"type": "url", "url": url}})
        if converted:
            messages.append({"role": role, "content": converted})
    return messages

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
    elif nome.startswith("condor_"):
        alvo = (
            args.get("project_id")
            or args.get("region_id")
            or args.get("device_id")
            or args.get("title")
            or args.get("name")
            or args.get("query")
            or args.get("revision")
            or "estado atual"
        )
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
    msg_lower = msg.lower()
    if (
        "exceeds the available context size" in msg_lower
        or "exceeds available context size" in msg_lower
        or "exceed_context_size_error" in msg_lower
        or "context length exceeded" in msg_lower
    ):
        return (
            "O modelo local abriu com contexto insuficiente. "
            "Feche o Condor e abra novamente pelo atalho para corrigir."
        )
    if "insufficient_quota" in msg:
        return "A conta do provedor está sem crédito disponível."
    if "invalid_api_key" in msg or "401" in msg:
        return "A credencial guardada no cofre nao foi aceita pelo conector de IA."
    if "rate_limit" in msg or "429" in msg:
        return "O conector de IA limitou as chamadas. Tente de novo em instantes."
    if "model_not_found" in msg:
        return "O conector nao tem acesso a esse modelo. Troque em ~/.condor/config.yaml."
    if "timeout" in msg_lower or "connection" in msg_lower:
        return "Nao consegui falar com o conector de IA. Verifique o servidor local ou a internet."
    return "O conector de IA falhou e eu nao consegui responder."
