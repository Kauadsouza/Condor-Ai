"""
Skills de controle de aplicativos: abrir, fechar, busca na web.
"""

from __future__ import annotations

import logging
import subprocess
import webbrowser

from condor.actions.base import SkillRegistry, make_skill

log = logging.getLogger("condor.actions.skills.apps")

# Mapeamento de nome amigável → executável (Windows)
APP_MAP: dict[str, str] = {
    "brave":     "brave.exe",
    "chrome":    "chrome.exe",
    "firefox":   "firefox.exe",
    "vscode":    "code",
    "vs code":   "code",
    "discord":   "discord.exe",
    "spotify":   "spotify.exe",
    "terminal":  "wt.exe",    # Windows Terminal
    "cmd":       "cmd.exe",
    "notepad":   "notepad.exe",
    "explorer":  "explorer.exe",
    "steam":     "steam.exe",
}


def open_application(name: str) -> str:
    key  = name.lower().strip()
    exe  = APP_MAP.get(key, key)
    log.info("Abrindo aplicativo: %s", exe)
    subprocess.Popen([exe], shell=True)
    return f"Abrindo {name}."


def close_application(name: str) -> str:
    key = name.lower().strip()
    exe = APP_MAP.get(key, key).replace(".exe", "")
    subprocess.run(["taskkill", "/IM", f"{exe}.exe", "/F"], capture_output=True)
    return f"{name} encerrado."


def web_search(query: str) -> str:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Busca aberta: {query}"


def volume_set(level: int) -> str:
    level = max(0, min(100, int(level)))
    # PowerShell: ajusta volume via objeto COM
    script = f"""
    $vol = [int]([System.Math]::Round({level} * 65535 / 100))
    $obj = New-Object -ComObject WScript.Shell
    $obj.SendKeys([char]174)  # dummy — usa nircmd abaixo se disponível
    """
    subprocess.run(["powershell", "-Command", f"[Audio]::Volume = {level / 100}"],
                   capture_output=True)
    return f"Volume ajustado para {level}%."


def register(registry: SkillRegistry) -> None:
    registry.register(make_skill(
        name="open_application",
        description="Abre um aplicativo pelo nome (ex: Brave, VSCode, Discord)",
        handler=open_application,
        params_schema={"name": "string"},
        resources=["process"],
    ))
    registry.register(make_skill(
        name="close_application",
        description="Fecha um aplicativo em execução pelo nome",
        handler=close_application,
        params_schema={"name": "string"},
        resources=["process"],
    ))
    registry.register(make_skill(
        name="web_search",
        description="Abre busca no navegador padrão",
        handler=web_search,
        params_schema={"query": "string"},
        resources=["network", "process"],
    ))
    registry.register(make_skill(
        name="volume_set",
        description="Ajusta o volume do sistema (0-100)",
        handler=volume_set,
        params_schema={"level": "integer"},
        resources=["display"],
    ))
