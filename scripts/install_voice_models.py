"""Baixa uma vez os modelos abertos de voz; depois o Condor roda offline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

from condor.paths import state_root


def main() -> int:
    models = state_root() / "models"
    stt = models / "stt" / "faster-whisper-small"
    tts = models / "tts"
    stt.mkdir(parents=True, exist_ok=True)
    tts.mkdir(parents=True, exist_ok=True)

    print("[1/2] Faster Whisper small")
    snapshot_download("Systran/faster-whisper-small", local_dir=stt)
    print("[2/2] Piper pt_BR-faber-medium")
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", "--data-dir", str(tts),
         "pt_BR-faber-medium"],
        check=True,
    )
    print(f"Voz local pronta em {models}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
