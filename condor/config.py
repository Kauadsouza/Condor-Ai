"""
Carregamento e validação de configuração.
Arquivo gerado em: ~/.condor/config.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    path: str = "data/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    n_ctx: int = 4096
    n_gpu_layers: int = -1      # -1 = auto (offload tudo pra GPU se disponível)
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 512
    repeat_penalty: float = 1.1


class VoiceConfig(BaseModel):
    wake_word: str = "condor"
    stt_model: str = "small"    # tiny, base, small, medium, large-v3
    stt_device: str = "auto"    # auto, cpu, cuda
    tts_voice: str = "pt_BR-faber-medium"
    tts_speed: float = 1.0
    enabled: bool = True


class MemoryConfig(BaseModel):
    db_path: str = "data/memory.db"
    vector_path: str = "data/vectors"
    learning: bool = True
    retention_days: int = 365
    max_context_memories: int = 12


class ActionsConfig(BaseModel):
    whitelist_paths: list[str] = Field(default_factory=lambda: [
        str(Path.home() / "condor_workspace"),
    ])
    require_confirmation: list[str] = Field(default_factory=lambda: [
        "shell_command",
        "file_delete",
    ])


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7777
    open_browser: bool = True


class Config(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    actions: ActionsConfig = Field(default_factory=ActionsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)


def load_config() -> Config:
    config_path = Path.home() / ".condor" / "config.yaml"

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default = Config()
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(default.model_dump(), f, allow_unicode=True, default_flow_style=False)
        print(f"  Configuração padrão criada em: {config_path}")
        return default

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return Config(**raw)
