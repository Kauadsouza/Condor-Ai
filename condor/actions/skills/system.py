"""
Skills de sistema: executar comandos, screenshot, digitar texto.
shell_command exige confirmação explícita do usuário.
"""

from __future__ import annotations

import logging
import subprocess
import time

from condor.actions.base import SkillRegistry, make_skill

log = logging.getLogger("condor.actions.skills.system")


def shell_command(cmd: str) -> str:
    log.warning("Executando shell: %s", cmd)
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    out = result.stdout.strip() or result.stderr.strip() or "(sem saída)"
    return out[:2000]


def screenshot() -> str:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        path = f"data/screenshot_{int(time.time())}.png"
        img.save(path)
        return f"Screenshot salvo em {path}"
    except ImportError:
        return "Pillow não instalado. Instale: pip install pillow"
    except Exception as exc:
        return f"Erro no screenshot: {exc}"


def type_text(text: str) -> str:
    try:
        import pyautogui
        pyautogui.write(text, interval=0.02)
        return f"Texto digitado: {text[:50]}..."
    except ImportError:
        return "pyautogui não instalado. Instale: pip install pyautogui"
    except Exception as exc:
        return f"Erro ao digitar: {exc}"


def get_system_info() -> str:
    import psutil
    cpu    = psutil.cpu_percent(interval=0.5)
    mem    = psutil.virtual_memory()
    disk   = psutil.disk_usage("/")
    return (
        f"CPU: {cpu:.0f}%\n"
        f"RAM: {mem.used / 1e9:.1f} GB / {mem.total / 1e9:.1f} GB ({mem.percent:.0f}%)\n"
        f"Disco: {disk.used / 1e9:.0f} GB / {disk.total / 1e9:.0f} GB ({disk.percent:.0f}%)"
    )


def register(registry: SkillRegistry) -> None:
    registry.register(make_skill(
        name="shell_command",
        description="Executa um comando no terminal (requer confirmação)",
        handler=shell_command,
        params_schema={"cmd": "string"},
        resources=["process", "filesystem", "network"],
        requires_confirm=True,
    ))
    registry.register(make_skill(
        name="screenshot",
        description="Tira um print da tela e salva em data/",
        handler=screenshot,
        params_schema={},
        resources=["display", "filesystem"],
    ))
    registry.register(make_skill(
        name="type_text",
        description="Digita texto na janela ativa",
        handler=type_text,
        params_schema={"text": "string"},
        resources=["display"],
    ))
    registry.register(make_skill(
        name="get_system_info",
        description="Retorna uso atual de CPU, RAM e disco",
        handler=get_system_info,
        params_schema={},
        resources=[],
    ))
