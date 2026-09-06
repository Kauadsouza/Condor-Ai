"""Geracao de imagens totalmente local usando stable-diffusion.cpp.

O executavel e os pesos ficam em ``~/.condor`` e nunca entram no Git. Nenhum
prompt ou bitmap sai do computador.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

from condor.paths import state_path

log = logging.getLogger("condor.imagem.local")


class LocalImageGenerator:
    """Escolhe o melhor perfil instalado sem prometer capacidade inexistente.

    SDXL-Lightning e o perfil principal: ele foi destilado para poucos passos e
    permite usar a resolucao nativa do SDXL em uma GPU pequena. O SD 1.5 antigo
    continua disponivel como fallback offline, em sua resolucao adequada.
    """

    REQUESTED_ASPECTS = {
        "auto": "square",
        "512x512": "square",
        "1024x1024": "square",
        "1024x1536": "portrait",
        "1536x1024": "landscape",
    }

    def __init__(self, config) -> None:
        self.config = config
        self._lock = asyncio.Lock()
        self._backend_cache: str | None | bool = False

    def _executables(self) -> list[Path]:
        root = state_path("tools", "stable-diffusion.cpp")
        if not root.exists():
            return []
        return sorted(root.glob("**/sd-cli.exe"), reverse=True)

    def _models(self) -> list[Path]:
        root = state_path("models", "image")
        if not root.exists():
            return []
        preferred = [
            root / "sdxl_lightning_4step.q4_0.gguf",
            root / "sdxl_lightning_4step.q5_0.gguf",
            root / "sdxl_lightning_4step.safetensors",
            root / "v1-5-pruned-emaonly.q8_0.gguf",
            root / "v1-5-pruned-emaonly.safetensors",
        ]
        found = [item for item in preferred if item.is_file()]
        found.extend(
            item for item in sorted((*root.glob("*.gguf"), *root.glob("*.safetensors")))
            if item not in found
        )
        return found

    @property
    def executable(self) -> Path | None:
        items = self._executables()
        return items[0] if items else None

    @property
    def model(self) -> Path | None:
        items = self._models()
        return items[0] if items else None

    @property
    def ready(self) -> bool:
        return bool(self.config.imagem.ativa and self.executable and self.model)

    @staticmethod
    def _profile(model: Path | None) -> str:
        return "sdxl_lightning_4step" if model and "sdxl_lightning_4step" in model.name.casefold() else "sd15"

    def _dimensions(self, model: Path, size: str) -> tuple[int, int]:
        aspect = self.REQUESTED_ASPECTS[size]
        if self._profile(model) == "sdxl_lightning_4step":
            return {
                "square": (1024, 1024),
                "portrait": (768, 1024),
                "landscape": (1024, 768),
            }[aspect]
        return {
            "square": (512, 512),
            "portrait": (512, 768),
            "landscape": (768, 512),
        }[aspect]

    def status(self) -> dict[str, Any]:
        executable = self.executable
        model = self.model
        return {
            "ready": self.ready,
            "provider": "local",
            "engine": "stable-diffusion.cpp",
            "model": model.stem if model else self.config.imagem.modelo,
            "profile": self._profile(model),
            "max_resolution": 1024 if self._profile(model) == "sdxl_lightning_4step" else 768,
            "executable_found": bool(executable),
            "model_found": bool(model),
            "private": True,
            "cloud_required": False,
        }

    def _preferred_backend(self, executable: Path) -> str | None:
        """Prefere uma GPU NVIDIA dedicada; evita cair na iGPU por ordem do driver."""
        if self._backend_cache is not False:
            return self._backend_cache or None
        try:
            result = subprocess.run(
                [str(executable), "--list-devices"], cwd=str(executable.parent),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=20, check=False,
                **({"creationflags": subprocess.CREATE_NO_WINDOW}
                   if hasattr(subprocess, "CREATE_NO_WINDOW") else {}),
            )
            devices = []
            for line in (result.stdout or "").splitlines():
                if "\t" not in line:
                    continue
                name, description = line.split("\t", 1)
                devices.append((name.strip(), description.casefold()))
            chosen = next((name for name, desc in devices if "nvidia" in desc), None)
            if chosen is None:
                chosen = next((name for name, _ in devices if name.casefold().startswith("vulkan")), None)
            if chosen is None:
                chosen = next((name for name, _ in devices if name.casefold() == "cpu"), None)
            self._backend_cache = chosen or None
        except (OSError, subprocess.SubprocessError):
            self._backend_cache = None
        return self._backend_cache or None

    @staticmethod
    def _tail(value: str, limit: int = 1200) -> str:
        text = str(value or "").strip()
        return text[-limit:]

    async def generate(self, prompt: str, *, size: str = "1024x1024", quality: str = "medium") -> dict[str, str | int | bool]:
        clean_prompt = " ".join(str(prompt or "").split()).strip()
        if not clean_prompt:
            raise ValueError("descreva a imagem que o Condor deve criar")
        if len(clean_prompt) > 4000:
            raise ValueError("o pedido da imagem excede 4000 caracteres")
        if size not in self.REQUESTED_ASPECTS:
            raise ValueError("tamanho de imagem invalido")
        if quality not in {"low", "medium", "high", "auto"}:
            raise ValueError("qualidade de imagem invalida")
        executable = self.executable
        model = self.model
        if executable is None or model is None:
            raise RuntimeError(
                "gerador local ainda nao instalado; execute scripts/install_local_image_generator.ps1"
            )

        profile = self._profile(model)
        width, height = self._dimensions(model, size)
        if profile == "sdxl_lightning_4step":
            # O checkpoint de quatro passos precisa exatamente desse sampler,
            # scheduler e baixa escala CFG para manter a qualidade da destilacao.
            steps = 4
            cfg_scale = "1.0"
            sampler = ["--sampling-method", "euler", "--scheduler", "sgm_uniform"]
        else:
            steps = {"low": 16, "medium": self.config.imagem.passos, "high": 32,
                     "auto": self.config.imagem.passos}[quality]
            steps = max(4, min(int(steps), 40))
            cfg_scale = "7.0"
            sampler = ["--sampling-method", "dpm++2m", "--scheduler", "karras"]
        output_dir = state_path("runtime", "generated-images")
        output_dir.mkdir(parents=True, exist_ok=True)
        output = (output_dir / f"condor-{int(time.time())}-{secrets.token_hex(6)}.png").resolve()
        if output_dir.resolve() not in output.parents:
            raise RuntimeError("destino de imagem local invalido")
        command = [
            str(executable), "-m", str(model), "-p", clean_prompt,
            "-n", "low quality, blurry, distorted, watermark, unreadable text",
            "-o", str(output), "-W", str(width), "-H", str(height),
            "--steps", str(steps), "--cfg-scale", cfg_scale, "--seed", "-1",
            "--fa", "--vae-tiling", "--rng", "cpu",
        ]
        command.extend(sampler)
        backend = self._preferred_backend(executable)
        if backend:
            command.extend(["--backend", backend])
        else:
            command.append("--auto-fit")

        def run() -> subprocess.CompletedProcess[str]:
            options: dict[str, Any] = {
                "cwd": str(executable.parent), "capture_output": True, "text": True,
                "encoding": "utf-8", "errors": "replace", "timeout": self.config.imagem.timeout_segundos,
                "check": False,
            }
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            return subprocess.run(command, **options)

        try:
            async with self._lock:
                result = await asyncio.to_thread(run)
            if result.returncode != 0 or not output.is_file():
                detail = self._tail(result.stderr or result.stdout)
                log.error("Gerador local falhou (%s): %s", result.returncode, detail)
                raise RuntimeError("o gerador local falhou; confira o modelo e o driver de video")
            data = output.read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("o gerador local devolveu um arquivo invalido")
            if len(data) > 30 * 1024 * 1024:
                raise RuntimeError("a imagem gerada excedeu o limite seguro")
            return {
                "image_b64": base64.b64encode(data).decode("ascii"),
                "mime_type": "image/png",
                "model": model.stem,
                "profile": profile,
                "provider": "local",
                "width": width,
                "height": height,
                "private": True,
            }
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("a geracao local excedeu o tempo limite") from exc
        finally:
            try:
                if output.is_file() and output_dir.resolve() in output.parents:
                    output.unlink()
            except OSError:
                pass
