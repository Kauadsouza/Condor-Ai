"""Baixa uma vez os modelos abertos de voz; depois o Condor roda offline."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from huggingface_hub import snapshot_download

from condor.paths import state_root


VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
VOSK_SHA256 = "6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7"


def instalar_vosk(destino: Path) -> None:
    """Detector da palavra "Condor" sem chave (usado quando não há Picovoice)."""
    if (destino / "vosk-model-small-pt-0.3").is_dir():
        return
    destino.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        arquivo = Path(tmp) / "vosk.zip"
        with urllib.request.urlopen(VOSK_URL, timeout=120) as resposta, arquivo.open("wb") as saida:
            shutil.copyfileobj(resposta, saida)
        if hashlib.sha256(arquivo.read_bytes()).hexdigest() != VOSK_SHA256:
            raise RuntimeError("modelo Vosk baixado não confere com o SHA-256 esperado")
        with zipfile.ZipFile(arquivo) as pacote:
            pacote.extractall(destino)


def main() -> int:
    models = state_root() / "models"
    stt = models / "stt" / "faster-whisper-small"
    tts = models / "tts"
    stt.mkdir(parents=True, exist_ok=True)
    tts.mkdir(parents=True, exist_ok=True)

    print("[1/3] Faster Whisper small")
    snapshot_download("Systran/faster-whisper-small", local_dir=stt)
    print("[2/3] Piper pt_BR-faber-medium")
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", "--data-dir", str(tts),
         "pt_BR-faber-medium"],
        check=True,
    )
    print("[3/3] Vosk pt (palavra Condor sem chave)")
    instalar_vosk(models / "wake")
    print(f"Voz local pronta em {models}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
