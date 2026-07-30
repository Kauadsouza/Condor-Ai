"""
Configuração do CONDOR.

Duas fontes:
  .env             → segredos (chave da OpenAI, chave do Picovoice, senha)
  data/config.yaml → comportamento (modelo, voz, tempos, trava)

O yaml é criado com os padrões no primeiro boot. Pode editar à vontade —
o que não estiver lá cai no padrão.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
CONFIG_PATH = DATA / "config.yaml"

load_dotenv(ROOT / ".env")


class CerebroConfig(BaseModel):
    """Modelos da OpenAI. O principal é quem conversa e usa as ferramentas."""

    modelo: str = "gpt-4o"
    modelo_rapido: str = "gpt-4o-mini"          # extrair memória, classificar
    modelo_embedding: str = "text-embedding-3-small"
    temperatura: float = 0.75
    max_tokens: int = 1500
    # Teto de iterações do loop de ferramentas: cobre tarefa de vários passos
    # sem deixar ele girar pra sempre se der ruim.
    max_iteracoes: int = 12


class VozConfig(BaseModel):
    """Ouvir e falar. Tudo pela API da OpenAI."""

    ativa: bool = True
    modelo_stt: str = "whisper-1"
    modelo_tts: str = "tts-1"
    voz: str = "onyx"                # alloy, echo, fable, onyx, nova, shimmer
    velocidade: float = 1.0
    idioma: str = "pt"
    # Captura da fala depois da wake word
    silencio_para_parar: float = 1.3   # segundos de silêncio que encerram a fala
    fala_maxima: float = 20.0          # corta em 20s pra não gravar o dia todo
    limiar_silencio: int = 380         # RMS abaixo disso = silêncio


class EscutaConfig(BaseModel):
    """Wake word — o detector que fica sempre ligado esperando 'Condor'."""

    ativa: bool = True
    # Palavra treinada por você no console.picovoice.ai (arquivo .ppn).
    # Coloque em data/wake/. Enquanto não tiver, cai na palavra embutida abaixo.
    palavra_embutida: str = "jarvis"
    sensibilidade: float = 0.6         # 0..1 — mais alto dispara mais fácil
    indice_microfone: int = -1         # -1 = microfone padrão do Windows


class SessaoConfig(BaseModel):
    """Ciclo dormindo → acordado → dormindo."""

    # Sem chamar o Condor por este tempo, ele dorme e fecha a janela.
    timeout_segundos: int = 120
    abrir_janela_ao_acordar: bool = True
    fechar_janela_ao_dormir: bool = True
    saudacao_ao_acordar: bool = True


class SegurancaConfig(BaseModel):
    """Acesso total ao PC, com senha só no que é catastrófico."""

    # Categorias que exigem senha antes de rodar.
    exigir_senha: list[str] = Field(default_factory=lambda: [
        "destruir_sistema",     # format, diskpart, apagar registro, mkfs
        "apagar_massa",         # remoção recursiva de pasta grande / raiz de disco
        "desligar",             # shutdown, restart, logoff
        "rede_seguranca",       # firewall, antivírus, redes wifi
    ])
    timeout_senha: int = 30            # segundos pra responder a senha
    tentativas_senha: int = 2
    auditoria: bool = True             # grava toda ação em data/auditoria.log


class ServidorConfig(BaseModel):
    host: str = "127.0.0.1"
    porta: int = 7777


class Config(BaseModel):
    cerebro: CerebroConfig = Field(default_factory=CerebroConfig)
    voz: VozConfig = Field(default_factory=VozConfig)
    escuta: EscutaConfig = Field(default_factory=EscutaConfig)
    sessao: SessaoConfig = Field(default_factory=SessaoConfig)
    seguranca: SegurancaConfig = Field(default_factory=SegurancaConfig)
    servidor: ServidorConfig = Field(default_factory=ServidorConfig)

    # ── Segredos: vêm do .env, nunca do yaml ──────────────────────────────
    @property
    def chave_openai(self) -> str:
        return (os.getenv("OPENAI_API_KEY") or "").strip()

    @property
    def chave_picovoice(self) -> str:
        return (os.getenv("PICOVOICE_ACCESS_KEY") or "").strip()

    @property
    def senha(self) -> str:
        return (os.getenv("CONDOR_SENHA") or "teste").strip()

    @property
    def nome_dono(self) -> str:
        return (os.getenv("CONDOR_DONO") or "Kauã").strip()


def carregar_config() -> Config:
    DATA.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        padrao = Config()
        _salvar(padrao)
        return padrao

    with open(CONFIG_PATH, encoding="utf-8") as f:
        bruto = yaml.safe_load(f) or {}
    cfg = Config(**bruto)
    # Regrava pra incorporar chaves novas que apareceram em versões futuras.
    _salvar(cfg)
    return cfg


def _salvar(cfg: Config) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg.model_dump(), f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)
