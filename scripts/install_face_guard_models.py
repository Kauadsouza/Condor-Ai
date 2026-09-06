"""Instala modelos oficiais fixados do OpenCV Zoo na pasta privada do Condor."""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from condor.paths import state_path


MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def main() -> None:
    target = state_path("models", "face")
    target.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in MODELS.items():
        final = target / name
        if final.is_file() and digest(final) == expected:
            print(f"{name}: OK")
            continue
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".download", dir=target)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Condor-Local/2"})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            observed = digest(temporary)
            if observed != expected:
                raise RuntimeError(f"hash inesperado para {name}: {observed}")
            os.replace(temporary, final)
            print(f"{name}: INSTALADO")
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
