"""Diagnóstico portátil, sem ler nem imprimir segredos do dono."""

from __future__ import annotations

import json
import os
import platform
import sys
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
        nomes = {str(model.get("name", "")) for model in data.get("models", [])}
        # "embeddinggemma" e "embeddinggemma:latest" são o mesmo modelo.
        return nomes | {nome.removesuffix(":latest") for nome in nomes}
    except Exception:
        return set()


def _test_local_brain(model: str, context: int = 8192) -> tuple[bool, int]:
    """Gera uma resposta real e confirma o contexto efetivo do processo."""
    if not model:
        return False, 0
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Responda somente OK."}],
        "options": {"num_predict": 8, "num_ctx": context},
        "stream": False,
    }).encode("utf-8")
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        generated = bool(result.get("done") and result.get("message", {}).get("content"))

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
    brain_response, brain_context = _test_local_brain(cfg.cerebro.modelo_local, cfg.cerebro.contexto_local)
    image_status = LocalImageGenerator(cfg).status()
    checks = {
        "platform": platform.platform(),
        "loopback_only": cfg.servidor.host in {"127.0.0.1", "localhost", "::1"},
        "mobile_view_safe": (
            cfg.visualizacao_movel.ativa
            and cfg.visualizacao_movel.porta != cfg.servidor.porta
            and (CODE_ROOT / "condor" / "mobile" / "index.html").is_file()
        ),
        "state_root": str(state_root()),
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
        "memory_embedding": cfg.cerebro.modelo_embedding_local in models,
        "wake_word": bool(list((state_root() / "models" / "wake").glob("vosk-model*"))
                          or list((state_root() / "wake").glob("condor*.ppn"))),
        "vault_configured": (state_root() / "security" / "vault.json").is_file(),
    }
    for key, value in checks.items():
        print(f"{key:20} {'OK' if value is True else 'PENDENTE' if value is False else value}")
    # Uma copia limpa deste repositorio precisa conseguir instalar,
    # diagnosticar e executar o Condor sem nenhum outro projeto.
    required = ["loopback_only", "mobile_view_safe", "ollama_online", "brain_model",
                "brain_response", "brain_context_safe", "vision_model", "stt_model",
                "tts_model", "memory_embedding", "wake_word"]
    # Criação de imagem é opcional na instalação (~7 GB): --sem-imagem.
    if "--sem-imagem" not in sys.argv:
        required.append("image_local")
    return 0 if all(checks[item] is True for item in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
