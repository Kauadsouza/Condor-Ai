"""
As maos do Condor — capacidades especificas, limitadas pela politica local.

No Windows, processos auxiliares permitidos nascem sem uma janela de console.

Cada função devolve sempre o mesmo formato:
    {"ok": bool, "saida": str}
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import platform
import webbrowser
import ipaddress
import socket
import uuid
import json
from pathlib import Path

from condor.paths import CODE_ROOT, state_root

log = logging.getLogger("condor.maos")

ROOT = CODE_ROOT
DATA = state_root()

# A flag que impede a janela preta de aparecer.
SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0

# User-Agent completo de navegador. Com um UA curto ("Mozilla/5.0") o
# DuckDuckGo devolve uma página reduzida e a busca volta vazia.
_NAVEGADOR = "Condor/2.0 (assistente local; leitura publica)"


def _startupinfo():
    """Cinto e suspensório: além do CREATE_NO_WINDOW, manda a janela nascer
    escondida. Alguns executáveis ignoram a flag e obedecem só isto."""
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def _rodar(
    args: list[str],
    timeout: int = 60,
    entrada: str | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[int, str]:
    p = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, input=entrada,
        encoding="utf-8", errors="replace", cwd=str(ROOT),
        creationflags=SEM_JANELA, startupinfo=_startupinfo(),
        env=environment,
    )
    return p.returncode, (p.stdout + p.stderr).strip()


def _ok(saida: str) -> dict:
    return {"ok": True, "saida": saida}


def _erro(saida: str) -> dict:
    return {"ok": False, "saida": saida}


def _caminho(bruto: str) -> Path:
    """Aceita ~, variáveis do Windows (%USERPROFILE%) e caminho relativo."""
    texto = os.path.expandvars(str(bruto).strip().strip('"').strip("'"))
    p = Path(texto).expanduser()
    return p if p.is_absolute() else (ROOT / p)


# ── Arquivos ─────────────────────────────────────────────────────────────────

def ler_arquivo(caminho: str, max_chars: int = 12000) -> dict:
    try:
        p = _caminho(caminho)
        if not p.exists():
            return _erro(f"Não existe: {p}")
        if p.is_dir():
            return listar_pasta(str(p))
        dados = p.read_text(encoding="utf-8", errors="replace")
        corte = "" if len(dados) <= max_chars else f"\n\n[... cortado, {len(dados)} chars no total]"
        return _ok(dados[:max_chars] + corte)
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def escrever_arquivo(caminho: str, conteudo: str, anexar: bool = False) -> dict:
    try:
        p = _caminho(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not anexar:
            version_dir = DATA / "versions" / time.strftime("%Y-%m-%d")
            version_dir.mkdir(parents=True, exist_ok=True)
            backup = version_dir / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{p.name}"
            shutil.copy2(p, backup)
        with open(p, "a" if anexar else "w", encoding="utf-8") as f:
            f.write(conteudo)
        verbo = "Anexado a" if anexar else "Escrito em"
        return _ok(f"{verbo} {p} ({len(conteudo)} chars)")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def listar_pasta(caminho: str = ".", limite: int = 200) -> dict:
    try:
        p = _caminho(caminho)
        if not p.is_dir():
            return _erro(f"Não é pasta: {p}")
        itens = []
        for i, item in enumerate(sorted(p.iterdir(),
                                        key=lambda x: (x.is_file(), x.name.lower()))):
            if i >= limite:
                itens.append(f"... (mais itens em {p})")
                break
            if item.is_dir():
                itens.append(f"[pasta] {item.name}")
            else:
                try:
                    kb = item.stat().st_size / 1024
                    itens.append(f"        {item.name}  ({kb:.1f} KB)")
                except OSError:
                    itens.append(f"        {item.name}")
        return _ok(f"{p}\n" + "\n".join(itens) if itens else f"{p} (vazia)")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def buscar_arquivos(padrao: str, raiz: str = "", limite: int = 60) -> dict:
    """Procura por nome. Sem raiz, varre as pastas do usuário."""
    try:
        raizes = [_caminho(raiz)] if raiz else [
            Path.home() / "Desktop", Path.home() / "Documents",
            Path.home() / "Downloads", ROOT,
        ]
        achados: list[str] = []
        alvo = padrao if any(c in padrao for c in "*?") else f"*{padrao}*"
        for base in raizes:
            if not base.exists():
                continue
            try:
                for item in base.rglob(alvo):
                    achados.append(str(item))
                    if len(achados) >= limite:
                        break
            except (PermissionError, OSError):
                continue
            if len(achados) >= limite:
                break
        return _ok("\n".join(achados) if achados else f"Nada encontrado pra '{padrao}'.")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def deletar(caminho: str, recursivo: bool = False) -> dict:
    """Move para a lixeira administrada pelo Condor; nao destroi imediatamente."""
    try:
        p = _caminho(caminho)
        if not p.exists():
            return _erro(f"Não existe: {p}")
        if p.is_dir() and any(p.iterdir()) and not recursivo:
            return _erro("A pasta tem conteudo; confirme com recursivo=true.")
        trash = DATA / "trash" / time.strftime("%Y-%m-%d")
        trash.mkdir(parents=True, exist_ok=True)
        target = trash / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{p.name}"
        shutil.move(str(p), str(target))
        manifest = target.with_name(target.name + ".condor.json")
        manifest.write_text(json.dumps({
            "original": str(p), "trashed": str(target), "timestamp": time.time()
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return _ok(f"Movido para a lixeira do Condor: {p} -> {target}")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def mover(origem: str, destino: str) -> dict:
    try:
        o, d = _caminho(origem), _caminho(destino)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(o), str(d))
        return _ok(f"{o} → {d}")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def copiar(origem: str, destino: str) -> dict:
    try:
        o, d = _caminho(origem), _caminho(destino)
        d.parent.mkdir(parents=True, exist_ok=True)
        if o.is_dir():
            shutil.copytree(str(o), str(d), dirs_exist_ok=True)
        else:
            shutil.copy2(str(o), str(d))
        return _ok(f"Copiado: {o} → {d}")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def baixar(url: str, destino: str) -> dict:
    try:
        import urllib.request
        _validar_url_publica(url)
        p = _caminho(destino)
        p.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Condor)"})
        temporary = p.with_name(p.name + f".{uuid.uuid4().hex}.part")
        with _urlopen_public(req, timeout=120) as r, open(temporary, "wb") as f:
            _validar_url_publica(r.geturl())
            total = 0
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise ValueError("Download excede o limite seguro de 100 MB.")
                f.write(chunk)
        os.replace(temporary, p)
        return _ok(f"Baixado: {p} ({p.stat().st_size / 1024:.1f} KB)")
    except Exception as exc:
        try:
            if 'temporary' in locals() and temporary.exists():
                temporary.unlink()
        except OSError:
            pass
        return _erro(f"{type(exc).__name__}: {exc}")


def ler_pdf(caminho: str, max_chars: int = 12000) -> dict:
    try:
        p = _caminho(caminho)
        if not p.exists():
            return _erro(f"Não existe: {p}")
        from pypdf import PdfReader
        leitor = PdfReader(str(p))
        texto = "\n".join((pg.extract_text() or "") for pg in leitor.pages[:40])
        if not texto.strip():
            return _ok("(PDF sem texto extraível — provavelmente é escaneado)")
        return _ok(texto[:max_chars])
    except ImportError:
        return _erro("pypdf não instalado.")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


# ── Apps e janelas ───────────────────────────────────────────────────────────

def abrir(alvo: str) -> dict:
    """Abre app, arquivo, pasta ou site. Aceita 'spotify', 'C:\\x.txt', 'youtube.com'."""
    alvo = alvo.strip()
    try:
        if re.match(r"^(https?://|www\.)", alvo) or re.match(r"^[\w-]+\.(com|br|org|net|io|dev)", alvo):
            url = alvo if alvo.startswith("http") else f"https://{alvo}"
            _validar_url_publica(url)
            webbrowser.open(url)
            return _ok(f"Abri {url}")

        p = _caminho(alvo)
        if p.exists():
            _abrir_path(p)
            return _ok(f"Abri {p}")

        # Nomes de aplicativo passam como um unico argumento em todos os SOs.
        # Caminhos existentes ja foram tratados acima; metacaracteres de shell
        # nunca sao aceitos nesta borda.
        if not re.fullmatch(r"[\w .()+-]{1,120}", alvo, flags=re.UNICODE):
            return _erro("Nome de aplicativo invalido.")

        if platform.system() != "Windows":
            subprocess.Popen(
                [alvo], cwd=str(ROOT), start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return _ok(f"Abri {alvo}")

        child_environment = os.environ.copy()
        child_environment["CONDOR_APP_TARGET"] = alvo
        # Nome de app: tenta o atalho do menu iniciar, depois o executável direto
        codigo, saida = _rodar(
            ["powershell", "-NoProfile", "-Command",
             "Start-Process -FilePath $env:CONDOR_APP_TARGET -ErrorAction Stop"],
            timeout=20, environment=child_environment)
        if codigo == 0:
            return _ok(f"Abri {alvo}")

        codigo, saida = _rodar(
            ["powershell", "-NoProfile", "-Command",
             "$alvo=$env:CONDOR_APP_TARGET; "
             "$m = Get-ChildItem -Path "
             "\"$env:ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\","
             "\"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\" "
             "-Recurse -Include *.lnk -ErrorAction SilentlyContinue | "
             "Where-Object { $_.BaseName -like ('*' + [WildcardPattern]::Escape($alvo) + '*') } | Select-Object -First 1; "
             "if ($m) { Start-Process $m.FullName; $m.BaseName } else { 'NAOACHEI' }"],
            timeout=45, environment=child_environment)
        if "NAOACHEI" in saida or not saida:
            return _erro(f"Não achei '{alvo}' instalado.")
        return _ok(f"Abri {saida.strip()}")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def fechar_app(nome: str) -> dict:
    try:
        if not re.fullmatch(r"[\w .()+-]{1,120}", nome, flags=re.UNICODE):
            return _erro("Nome de processo invalido.")
        import psutil
        matches = []
        wanted = nome.lower().removesuffix(".exe")
        for process in psutil.process_iter(["name"]):
            current = (process.info.get("name") or "").lower().removesuffix(".exe")
            if current == wanted:
                process.terminate()
                matches.append(str(process.pid))
        return _ok(f"Solicitei encerramento de {len(matches)} processo(s): {nome}") if matches else _erro(f"Nao achei {nome}.")
    except Exception as exc:
        return _erro(str(exc))


def listar_janelas() -> dict:
    try:
        if platform.system() != "Windows":
            import psutil
            names = sorted({(p.info.get("name") or "") for p in psutil.process_iter(["name"]) if p.info.get("name")})
            return _ok("Processos visiveis no sistema:\n" + "\n".join(names[:120]))
        _, saida = _rodar(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
             "Select-Object ProcessName, MainWindowTitle | "
             "Format-Table -AutoSize | Out-String -Width 180"], timeout=20)
        return _ok(saida[:3000] or "(nenhuma janela com título)")
    except Exception as exc:
        return _erro(str(exc))


def focar_janela(titulo: str) -> dict:
    try:
        if not re.fullmatch(r"[\w .()+-]{1,160}", titulo, flags=re.UNICODE):
            return _erro("Titulo de janela invalido.")
        if platform.system() != "Windows":
            return _erro("Focar janela requer um adaptador grafico especifico do Linux/macOS.")
        child_environment = os.environ.copy()
        child_environment["CONDOR_WINDOW_TITLE"] = titulo
        _, saida = _rodar(
            ["powershell", "-NoProfile", "-Command",
             "$w = New-Object -ComObject WScript.Shell; $titulo=$env:CONDOR_WINDOW_TITLE; "
             "if ($w.AppActivate($titulo)) { 'OK' } else { 'NAOACHEI' }"],
            timeout=15, environment=child_environment)
        if "OK" in saida:
            return _ok(f"Janela '{titulo}' em foco.")
        return _erro(f"Não achei janela com '{titulo}' no título.")
    except Exception as exc:
        return _erro(str(exc))


def info_sistema() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.4)
        ram = psutil.virtual_memory()
        disco = psutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
        linhas = [
            f"CPU: {cpu:.0f}%  ({psutil.cpu_count(logical=True)} threads)",
            f"RAM: {ram.percent:.0f}% — {ram.used/1e9:.1f} de {ram.total/1e9:.1f} GB",
            f"Disco principal: {disco.percent:.0f}% — {disco.free/1e9:.1f} GB livres",
            f"Ligado há {(time.time() - psutil.boot_time())/3600:.1f} h",
        ]
        try:
            bat = psutil.sensors_battery()
            if bat:
                linhas.append(f"Bateria: {bat.percent:.0f}%"
                              + (" (na tomada)" if bat.power_plugged else ""))
        except Exception:
            pass
        topo = sorted(psutil.process_iter(["name", "memory_info"]),
                      key=lambda p: (p.info["memory_info"].rss if p.info["memory_info"] else 0),
                      reverse=True)[:5]
        linhas.append("Mais pesados: " + ", ".join(
            f"{p.info['name']} ({p.info['memory_info'].rss/1e6:.0f} MB)"
            for p in topo if p.info["memory_info"]))
        return _ok("\n".join(linhas))
    except Exception as exc:
        return _erro(str(exc))


# ── Tela, mouse e teclado ────────────────────────────────────────────────────

def screenshot() -> dict:
    """Tira print e devolve o caminho + a imagem em base64 (o modelo enxerga)."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
        pasta = DATA / "screenshots"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"tela_{int(time.time())}.png"
        img.save(destino)

        # Reduz antes de mandar pro modelo: 1024px de largura já dá pra ler tudo
        # e corta o custo do token de imagem pela metade.
        copia = img.copy()
        if copia.width > 1400:
            proporcao = 1400 / copia.width
            copia = copia.resize((1400, int(copia.height * proporcao)))
        buf = io.BytesIO()
        copia.convert("RGB").save(buf, format="JPEG", quality=72)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"ok": True, "saida": f"Print salvo em {destino} ({img.size[0]}x{img.size[1]})",
                "imagem_b64": b64}
    except ImportError:
        return _erro("Pillow não instalado.")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def clicar(x: int, y: int, botao: str = "left", duplo: bool = False) -> dict:
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        if duplo:
            pyautogui.doubleClick(x=x, y=y)
        else:
            pyautogui.click(x=x, y=y, button=botao)
        return _ok(f"Clique {'duplo ' if duplo else ''}{botao} em ({x}, {y})")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def digitar(texto: str) -> dict:
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        # write() não dá conta de acento; pro texto com acento vai pelo clipboard.
        if any(ord(c) > 127 for c in texto):
            escrever_clipboard(texto)
            pyautogui.hotkey("ctrl", "v")
            return _ok(f"Digitado (via clipboard): {len(texto)} chars")
        pyautogui.write(texto, interval=0.012)
        return _ok(f"Digitado: {len(texto)} chars")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def atalho(teclas: str) -> dict:
    """Ex.: 'ctrl+c', 'alt+tab', 'win+d', 'enter'."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        partes = [t.strip().lower() for t in re.split(r"[+\-]", teclas) if t.strip()]
        if not partes:
            return _erro("Combinação vazia.")
        if len(partes) == 1:
            pyautogui.press(partes[0])
        else:
            pyautogui.hotkey(*partes)
        return _ok(f"Teclas: {'+'.join(partes)}")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def ler_clipboard() -> dict:
    try:
        import pyperclip
        return _ok(pyperclip.paste()[:5000] or "(clipboard vazio)")
    except Exception:
        try:
            _, saida = _rodar(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                              timeout=10)
            return _ok(saida[:5000] or "(clipboard vazio)")
        except Exception as exc:
            return _erro(str(exc))


def escrever_clipboard(texto: str) -> dict:
    try:
        import pyperclip
        pyperclip.copy(texto)
        return _ok(f"Copiado: {len(texto)} chars")
    except Exception:
        try:
            codigo, _ = _rodar(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                               timeout=10, entrada=texto)
            return {"ok": codigo == 0, "saida": f"Copiado: {len(texto)} chars"}
        except Exception as exc:
            return _erro(str(exc))


# ── Web ──────────────────────────────────────────────────────────────────────

def buscar_web(consulta: str, limite: int = 6) -> dict:
    """Busca no DuckDuckGo sem API key. Devolve título + resumo dos resultados."""
    try:
        import html
        import urllib.parse
        import urllib.request
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(consulta)
        req = urllib.request.Request(url, headers={"User-Agent": _NAVEGADOR})
        with _urlopen_public(req, timeout=20) as r:
            corpo = r.read().decode("utf-8", errors="replace")

        def _limpar(s: str) -> str:
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(s))).strip()

        titulos = [_limpar(t) for t in re.findall(
            r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', corpo, re.DOTALL)]
        resumos = [_limpar(s) for s in re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', corpo, re.DOTALL)]
        itens = [f"{i+1}. {t}\n   {resumos[i] if i < len(resumos) else ''}"
                 for i, t in enumerate(titulos[:limite])]
        return _ok("\n".join(itens) or "(nenhum resultado)")
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def ler_site(url: str, max_chars: int = 8000) -> dict:
    """Baixa a página e devolve só o texto."""
    try:
        import html
        import urllib.request
        _validar_url_publica(url)
        req = urllib.request.Request(url, headers={"User-Agent": _NAVEGADOR})
        with _urlopen_public(req, timeout=25) as r:
            _validar_url_publica(r.geturl())
            corpo = r.read().decode("utf-8", errors="replace")
        corpo = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", corpo,
                       flags=re.DOTALL | re.IGNORECASE)
        texto = re.sub(r"<[^>]+>", " ", corpo)
        texto = re.sub(r"[ \t]+", " ", html.unescape(texto))
        texto = re.sub(r"\n\s*\n+", "\n\n", texto).strip()
        return _ok(texto[:max_chars])
    except Exception as exc:
        return _erro(f"{type(exc).__name__}: {exc}")


def _abrir_path(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)], start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)


def _validar_url_publica(url: str) -> None:
    """Bloqueia acesso do agente a localhost, LAN e metadados de nuvem."""
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Somente URLs HTTP/HTTPS publicas sao permitidas.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("Nao foi possivel resolver o endereco.") from exc
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("O Condor bloqueou acesso a endereco interno ou reservado.")


def _urlopen_public(request, timeout: int):
    """Valida a URL inicial e cada redirecionamento antes de fazer a conexao."""
    import urllib.request

    initial = request.full_url if hasattr(request, "full_url") else str(request)
    _validar_url_publica(initial)

    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _validar_url_publica(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(SafeRedirect()).open(request, timeout=timeout)
