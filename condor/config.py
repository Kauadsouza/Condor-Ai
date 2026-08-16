"""
Configuração do CONDOR.

Duas fontes:
  cofre cifrado       → segredos do dono e chaves externas
  ~/.condor/config.yaml → comportamento portavel

O yaml é criado com os padrões no primeiro boot. Pode editar à vontade —
o que não estiver lá cai no padrão.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, PrivateAttr, field_validator

from condor.paths import CODE_ROOT, state_path, state_root

ROOT = CODE_ROOT
DATA = state_root()
CONFIG_PATH = state_path("config.yaml")


def _config_path() -> Path:
    """Resolve a cada chamada para testes/instancias com CONDOR_HOME isolado."""
    return state_path("config.yaml")

class CerebroConfig(BaseModel):
    """Modelos da OpenAI. O principal é quem conversa e usa as ferramentas."""

    modelo: str = "gpt-5.6-terra"
    modelo_rapido: str = "gpt-5.6-luna"          # extrair memória, classificar
    modelo_embedding: str = "text-embedding-3-small"
    endpoint_local: str = "http://127.0.0.1:11434/v1"
    modelo_local: str = ""
    modelo_visao_local: str = "qwen3-vl:2b"
    temperatura: float = 0.75
    max_tokens: int = 1500
    # Teto de iterações do loop de ferramentas: cobre tarefa de vários passos
    # sem deixar ele girar pra sempre se der ruim.
    max_iteracoes: int = 12
    # Privacidade por padrao: fatos antigos nao saem do PC. Ative conscientemente
    # apenas se aceitar enviar esses trechos ao conector generativo configurado.
    compartilhar_memoria_com_conector: bool = False
    aprendizado_automatico_por_conector: bool = False

    @field_validator("endpoint_local")
    @classmethod
    def _endpoint_local_seguro(cls, value: str) -> str:
        parsed = urlsplit(value.rstrip("/"))
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("O conector local precisa usar HTTP no loopback do proprio PC.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Endpoint local invalido.")
        return value.rstrip("/")


class VozConfig(BaseModel):
    """Ouvir e falar com modelos instalados localmente."""

    ativa: bool = True
    modelo_stt: str = "faster-whisper-small"
    modelo_tts: str = "pt_BR-faber-medium"
    voz: str = "faber"
    velocidade: float = 1.0
    idioma: str = "pt"
    # Captura da fala depois da wake word
    silencio_para_parar: float = 1.3   # segundos de silêncio que encerram a fala
    fala_maxima: float = 20.0          # corta em 20s pra não gravar o dia todo
    limiar_silencio: int = 380         # RMS abaixo disso = silêncio


class EscutaConfig(BaseModel):
    """Wake word — o detector que fica sempre ligado esperando 'Condor'."""

    ativa: bool = True
    # Palavra "Condor" treinada por você (arquivo condor*.ppn).
    # Coloque em ~/.condor/wake/. Nao existe palavra alternativa.
    sensibilidade: float = 0.6         # 0..1 — mais alto dispara mais fácil
    indice_microfone: int = -1         # -1 = microfone padrao do sistema


class SessaoConfig(BaseModel):
    """Ciclo dormindo → acordado → dormindo."""

    # Sem chamar o Condor por este tempo, ele dorme e fecha a janela.
    timeout_segundos: int = 120
    abrir_janela_ao_acordar: bool = True
    fechar_janela_ao_dormir: bool = True
    saudacao_ao_acordar: bool = True


class SegurancaConfig(BaseModel):
    """Politica local, independente de fornecedor e sistema operacional."""

    perfil: str = "admin"              # o dono autenticado recebe o perfil completo
    simulacao: bool = False
    timeout_aprovacao: int = 90
    auditoria: bool = True
    pastas_permitidas: list[str] = Field(default_factory=list)

    @field_validator("perfil")
    @classmethod
    def _perfil_valido(cls, value: str) -> str:
        allowed = {"observer", "assistant", "operator", "admin"}
        if value not in allowed:
            raise ValueError(f"perfil precisa ser um de {sorted(allowed)}")
        return value


class ServidorConfig(BaseModel):
    host: str = "127.0.0.1"
    porta: int = 7777

    @field_validator("host")
    @classmethod
    def _somente_loopback(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("O servidor local do Condor so pode escutar no loopback.")
        return value


class VisualizacaoMovelConfig(BaseModel):
    """Espelho sanitizado para o navegador de outro aparelho na rede privada."""

    ativa: bool = True
    porta: int = 7778

    @field_validator("porta")
    @classmethod
    def _porta_valida(cls, value: int) -> int:
        if value < 1024 or value > 65535:
            raise ValueError("A porta da visualizacao movel precisa estar entre 1024 e 65535.")
        return value


class Config(BaseModel):
    cerebro: CerebroConfig = Field(default_factory=CerebroConfig)
    voz: VozConfig = Field(default_factory=VozConfig)
    escuta: EscutaConfig = Field(default_factory=EscutaConfig)
    sessao: SessaoConfig = Field(default_factory=SessaoConfig)
    seguranca: SegurancaConfig = Field(default_factory=SegurancaConfig)
    servidor: ServidorConfig = Field(default_factory=ServidorConfig)
    visualizacao_movel: VisualizacaoMovelConfig = Field(
        default_factory=VisualizacaoMovelConfig
    )
    _vault: Any = PrivateAttr(default=None)

    def ligar_cofre(self, vault: Any) -> None:
        self._vault = vault

    def _segredo(self, name: str) -> str:
        if self._vault is not None and getattr(self._vault, "unlocked", False):
            value = self._vault.get(name, "")
            if value:
                return str(value).strip()
        return (os.getenv(name) or "").strip()

    # O cofre e a fonte normal. Variaveis de ambiente existem somente para
    # execucoes efemeras e automacao; nenhum arquivo de segredo e carregado.
    @property
    def chave_openai(self) -> str:
        return self._segredo("OPENAI_API_KEY")

    @property
    def chave_picovoice(self) -> str:
        return self._segredo("PICOVOICE_ACCESS_KEY")

    @property
    def nome_dono(self) -> str:
        return self._segredo("CONDOR_DONO") or "Kaua"

    @property
    def safety_identifier(self) -> str:
        configured = self._segredo("CONDOR_SAFETY_ID")
        if configured:
            return configured
        # Execucao efemera sem cofre: identificador estavel sem usar nome pessoal.
        import hashlib
        seed = self.chave_openai or "condor-local-sem-chave"
        return hashlib.sha256(("condor:" + seed).encode("utf-8")).hexdigest()[:32]


def carregar_config() -> Config:
    DATA.mkdir(parents=True, exist_ok=True)
    path = _config_path()

    if not path.exists():
        padrao = Config()
        _salvar(padrao)
        return padrao

    with open(path, encoding="utf-8") as f:
        bruto = yaml.safe_load(f) or {}
    cfg = Config(**bruto)
    # Regrava pra incorporar chaves novas que apareceram em versões futuras.
    _salvar(cfg)
    return cfg


def _salvar(cfg: Config) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".yaml.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        yaml.dump(cfg.model_dump(), f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def salvar_config(cfg: Config) -> None:
    """Persiste apenas preferencias nao secretas do Condor."""
    _salvar(cfg)
