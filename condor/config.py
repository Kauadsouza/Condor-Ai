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


def _config_path() -> Path:
    """Resolve a cada chamada para testes/instancias com CONDOR_HOME isolado."""
    return state_path("config.yaml")

class CerebroConfig(BaseModel):
    """Provedores selecionáveis; cada modelo continua independente."""

    modelo: str = "gpt-5.6-terra"
    modelo_rapido: str = "gpt-5.6-luna"          # extrair memória, classificar
    modelo_embedding: str = "text-embedding-3-small"
    provedor_preferido: str = "auto"
    modelo_claude: str = "claude-sonnet-5"
    endpoint_local: str = "http://127.0.0.1:11434/v1"
    modelo_local: str = ""
    modelo_visao_local: str = "qwen3-vl:2b"
    temperatura: float = 0.75
    max_tokens: int = 1500
    # Teto de iterações do loop de ferramentas: cobre tarefa de vários passos
    # sem deixar ele girar pra sempre se der ruim.
    max_iteracoes: int = 12
    # A memoria pertence ao Condor, nao ao fornecedor escolhido. Toda conversa
    # usa apenas o contexto relevante recuperado do banco cifrado local e todo
    # provedor alimenta o mesmo processo de aprendizado do Condor.
    compartilhar_memoria_com_conector: bool = True
    aprendizado_automatico_por_conector: bool = True

    @field_validator(
        "compartilhar_memoria_com_conector",
        "aprendizado_automatico_por_conector",
        mode="before",
    )
    @classmethod
    def _memoria_interna_obrigatoria(cls, _value: Any) -> bool:
        return True

    @field_validator("provedor_preferido")
    @classmethod
    def _provedor_valido(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "local", "openai", "claude"}:
            raise ValueError("provedor_preferido precisa ser openai, claude ou local")
        return normalized

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


class ImagemConfig(BaseModel):
    """Geracao criativa independente de nuvem."""

    ativa: bool = True
    provedor: str = "local"
    motor: str = "stable-diffusion.cpp"
    modelo: str = "sdxl-lightning-4step"
    passos: int = 20
    timeout_segundos: int = 900

    @field_validator("provedor")
    @classmethod
    def _provedor_local(cls, value: str) -> str:
        if value.strip().lower() != "local":
            raise ValueError("a geracao principal de imagens do Condor precisa ser local")
        return "local"

    @field_validator("passos")
    @classmethod
    def _passos_validos(cls, value: int) -> int:
        if value < 4 or value > 40:
            raise ValueError("passos de imagem precisa estar entre 4 e 40")
        return value

    @field_validator("timeout_segundos")
    @classmethod
    def _timeout_valido(cls, value: int) -> int:
        if value < 60 or value > 3600:
            raise ValueError("timeout de imagem precisa estar entre 60 e 3600 segundos")
        return value


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


class CondorCloudConfig(BaseModel):
    """Cliente privado da mente online; credenciais ficam somente no cofre."""

    ativa: bool = False
    api_url: str = ""
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    intervalo_sync_segundos: int = 30

    @field_validator("api_url", "supabase_url")
    @classmethod
    def _url_cloud_segura(cls, value: str) -> str:
        clean = value.strip().rstrip("/")
        if not clean:
            return ""
        parsed = urlsplit(clean)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != ("http" if local else "https"):
            raise ValueError("Condor Cloud exige HTTPS; HTTP e aceito apenas no localhost.")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("URL do Condor Cloud invalida.")
        return clean

    @field_validator("supabase_publishable_key")
    @classmethod
    def _chave_publica_limitada(cls, value: str) -> str:
        clean = value.strip()
        if clean and (len(clean) < 20 or len(clean) > 2048):
            raise ValueError("Chave publica do Supabase invalida.")
        return clean

    @field_validator("intervalo_sync_segundos")
    @classmethod
    def _intervalo_seguro(cls, value: int) -> int:
        if value < 15 or value > 900:
            raise ValueError("Intervalo do Condor Cloud precisa ficar entre 15 e 900 segundos.")
        return value


class Config(BaseModel):
    cerebro: CerebroConfig = Field(default_factory=CerebroConfig)
    voz: VozConfig = Field(default_factory=VozConfig)
    escuta: EscutaConfig = Field(default_factory=EscutaConfig)
    imagem: ImagemConfig = Field(default_factory=ImagemConfig)
    sessao: SessaoConfig = Field(default_factory=SessaoConfig)
    seguranca: SegurancaConfig = Field(default_factory=SegurancaConfig)
    servidor: ServidorConfig = Field(default_factory=ServidorConfig)
    visualizacao_movel: VisualizacaoMovelConfig = Field(
        default_factory=VisualizacaoMovelConfig
    )
    cloud: CondorCloudConfig = Field(default_factory=CondorCloudConfig)
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
    def chave_anthropic(self) -> str:
        return self._segredo("ANTHROPIC_API_KEY")

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
    # CONDOR_HOME pode mudar entre instancias e nos testes. Resolva o estado
    # apenas no momento do uso para nunca gravar no cofre de outra execucao.
    state_root().mkdir(parents=True, exist_ok=True)
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
