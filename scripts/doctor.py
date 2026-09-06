"""Diagnóstico portátil, sem ler nem imprimir segredos do dono."""

from __future__ import annotations

import json
import os
import platform
import urllib.request
from pathlib import Path

from condor.config import carregar_config
from condor.media.local_image import LocalImageGenerator
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


def _test_local_brain(model: str) -> tuple[bool, int]:
    """Gera uma resposta real e confirma o contexto efetivo do processo."""
    if not model:
        return False, 0
    body = json.dumps({
        "model": model,
        "input": "Responda somente OK.",
        "max_output_tokens": 8,
        "stream": False,
    }).encode("utf-8")
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:11434/v1/responses",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        generated = bool(result.get("output"))

        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5) as response:
            running = json.load(response)
        context_length = 0
        for entry in running.get("models", []):
            if str(entry.get("name", "")) == model:
                context_length = int(entry.get("context_length") or 0)
                break
        return generated, context_length
    except Exception:
        return False, 0


def main() -> int:
    cfg = carregar_config()
    dummy = object()
    models = _ollama_models()
    brain_response, brain_context = _test_local_brain(cfg.cerebro.modelo_local)
    image_status = LocalImageGenerator(cfg).status()
    hub = Path(os.getenv("CONDOR_HUB_OUT") or (CODE_ROOT.parent.parent / "ARTX Hub" / "out"))
    checks = {
        "platform": platform.platform(),
        "loopback_only": cfg.servidor.host in {"127.0.0.1", "localhost", "::1"},
        "mobile_view_safe": (
            cfg.visualizacao_movel.ativa
            and cfg.visualizacao_movel.porta != cfg.servidor.porta
            and (CODE_ROOT / "condor" / "mobile" / "index.html").is_file()
        ),
        "state_root": str(state_root()),
        "hub_static_build": (hub / "index.html").is_file(),
        "ollama_online": bool(models),
        "brain_model": cfg.cerebro.modelo_local in models,
        "brain_response": brain_response,
        "brain_context": brain_context,
        "brain_context_safe": brain_context >= 8192,
        "vision_model": cfg.cerebro.modelo_visao_local in models,
        "image_local": (
            image_status["ready"] and image_status["provider"] == "local"
            and image_status["cloud_required"] is False
        ),
        "stt_model": Ouvidos(cfg, dummy).pronto,
        "tts_model": Voz(cfg, dummy).pronto,
        "vault_configured": (state_root() / "security" / "vault.json").is_file(),
    }
    for key, value in checks.items():
        print(f"{key:20} {'OK' if value is True else 'PENDENTE' if value is False else value}")
    # O ARTX Hub e um projeto separado e opcional. Uma copia limpa apenas deste
    # repositorio precisa conseguir instalar, diagnosticar e executar o Condor.
    required = ("loopback_only", "mobile_view_safe", "ollama_online", "brain_model",
                "brain_response", "brain_context_safe", "vision_model", "image_local", "stt_model",
                "tts_model")
    return 0 if all(checks[item] is True for item in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
