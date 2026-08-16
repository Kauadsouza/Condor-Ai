"""Diagnóstico portátil, sem ler nem imprimir segredos do dono."""

from __future__ import annotations

import json
import os
import platform
import urllib.request
from pathlib import Path

from condor.config import carregar_config
from condor.paths import CODE_ROOT, state_root
from condor.voice.stt import Ouvidos
from condor.voice.tts import Voz


def _ollama_models() -> set[str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            data = json.load(response)
        return {str(model.get("name", "")) for model in data.get("models", [])}
    except Exception:
        return set()


def main() -> int:
    cfg = carregar_config()
    dummy = object()
    models = _ollama_models()
    hub = Path(os.getenv("CONDOR_HUB_OUT") or (CODE_ROOT.parent.parent / "ARTX Hub" / "out"))
    checks = {
        "platform": platform.platform(),
        "loopback_only": cfg.servidor.host in {"127.0.0.1", "localhost", "::1"},
        "state_root": str(state_root()),
        "hub_static_build": (hub / "index.html").is_file(),
        "ollama_online": bool(models),
        "brain_model": cfg.cerebro.modelo_local in models,
        "vision_model": cfg.cerebro.modelo_visao_local in models,
        "stt_model": Ouvidos(cfg, dummy).pronto,
        "tts_model": Voz(cfg, dummy).pronto,
        "vault_configured": (state_root() / "security" / "vault.json").is_file(),
    }
    for key, value in checks.items():
        print(f"{key:20} {'OK' if value is True else 'PENDENTE' if value is False else value}")
    required = ("loopback_only", "hub_static_build", "ollama_online", "brain_model",
                "vision_model", "stt_model", "tts_model")
    return 0 if all(checks[item] is True for item in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
