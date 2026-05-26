"""
Executor de alto poder — dá ao Condor controle total sobre o PC.

O AI inclui blocos especiais na resposta usando o marcador ◆:
  ◆CMD: Get-ChildItem C:/Users          → executa PowerShell
  ◆PY:\nx=1+1\nprint(x)                 → executa Python no contexto do Condor
  ◆READ: C:/caminho/arquivo.txt          → lê um arquivo
  ◆WRITE: C:/caminho/arquivo.txt\nconteúdo → escreve um arquivo
  ◆GET: https://url.com -> C:/destino   → baixa arquivo da internet
  ◆PIP: nome_pacote                     → instala pacote Python

O server.py detecta esses marcadores, executa e injeta os resultados
de volta na conversa para que o Condor possa agir sobre eles.
"""

from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import sys
import textwrap
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Any

log = logging.getLogger("condor.executor")

# Raiz do projeto — disponível para o código Python executado pelo Condor
ROOT = Path(__file__).parent.parent.parent

# Padrões de extração dos marcadores
_CMD_RE   = re.compile(r'◆CMD:\s*(.+?)(?=◆|\Z)', re.DOTALL)
_PY_RE    = re.compile(r'◆PY:\s*\n(.*?)(?=◆|\Z)', re.DOTALL)
_READ_RE  = re.compile(r'◆READ:\s*(.+?)(?=◆|\Z)')
_WRITE_RE = re.compile(r'◆WRITE:\s*(.+?)\n(.*?)(?=◆|\Z)', re.DOTALL)
_GET_RE   = re.compile(r'◆GET:\s*(https?://\S+)\s*->\s*(.+?)(?=◆|\Z)')
_PIP_RE   = re.compile(r'◆PIP:\s*(.+?)(?=◆|\Z)')


def extract_and_run(response: str, context: dict | None = None) -> list[dict]:
    """
    Extrai todos os marcadores ◆ do texto do AI e executa cada um.
    Retorna lista de resultados [{marker, input, output, success}].
    """
    results = []

    # ── ◆CMD ──────────────────────────────────────────────────────────────────
    for m in _CMD_RE.finditer(response):
        cmd = m.group(1).strip()
        results.append(_run_shell(cmd))

    # ── ◆PY ───────────────────────────────────────────────────────────────────
    for m in _PY_RE.finditer(response):
        code = textwrap.dedent(m.group(1))
        results.append(_run_python(code, context))

    # ── ◆READ ─────────────────────────────────────────────────────────────────
    for m in _READ_RE.finditer(response):
        path = m.group(1).strip()
        results.append(_read_file(path))

    # ── ◆WRITE ────────────────────────────────────────────────────────────────
    for m in _WRITE_RE.finditer(response):
        path    = m.group(1).strip()
        content = m.group(2)
        results.append(_write_file(path, content))

    # ── ◆GET ──────────────────────────────────────────────────────────────────
    for m in _GET_RE.finditer(response):
        url  = m.group(1).strip()
        dest = m.group(2).strip()
        results.append(_download(url, dest))

    # ── ◆PIP ──────────────────────────────────────────────────────────────────
    for m in _PIP_RE.finditer(response):
        pkg = m.group(1).strip()
        results.append(_pip_install(pkg))

    return results


def format_results(results: list[dict]) -> str:
    """Formata resultados para injetar de volta na conversa."""
    if not results:
        return ""
    lines = []
    for r in results:
        status = "✓" if r["success"] else "✗"
        lines.append(f"[{status} {r['marker']}] {r['input'][:80]}")
        if r["output"]:
            lines.append(r["output"][:1500])
    return "\n".join(lines)


# ── Implementações ─────────────────────────────────────────────────────────────

def _run_shell(cmd: str) -> dict:
    log.info("◆CMD: %s", cmd[:120])
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
            cwd=str(ROOT),
        )
        out = (result.stdout + result.stderr).strip() or "(sem saída)"
        return {"marker": "CMD", "input": cmd, "output": out[:2000], "success": result.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"marker": "CMD", "input": cmd, "output": "Timeout (60s)", "success": False}
    except Exception as exc:
        return {"marker": "CMD", "input": cmd, "output": str(exc), "success": False}


def _run_python(code: str, context: dict | None = None) -> dict:
    log.info("◆PY: %s...", code[:60].replace('\n', ' '))
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    # Contexto de execução: tem acesso ao banco, ao grafo, ao ROOT
    exec_globals: dict[str, Any] = {
        "__builtins__": __builtins__,
        "ROOT": ROOT,
        "Path": Path,
        "os": os,
        "sys": sys,
        "subprocess": subprocess,
        "re": re,
    }
    # Injeta referências vivas do servidor se disponíveis
    if context:
        exec_globals.update(context)

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(compile(code, "<condor>", "exec"), exec_globals)
        out = stdout_buf.getvalue() + stderr_buf.getvalue()
        return {"marker": "PY", "input": code[:80], "output": out.strip()[:2000] or "(executado sem output)", "success": True}
    except Exception as exc:
        return {"marker": "PY", "input": code[:80], "output": f"{type(exc).__name__}: {exc}", "success": False}


def _read_file(path: str) -> dict:
    try:
        p = Path(path.strip())
        if not p.is_absolute():
            p = ROOT / p
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"marker": "READ", "input": str(p), "output": content[:3000], "success": True}
    except Exception as exc:
        return {"marker": "READ", "input": path, "output": str(exc), "success": False}


def _write_file(path: str, content: str) -> dict:
    try:
        p = Path(path.strip())
        if not p.is_absolute():
            p = ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"marker": "WRITE", "input": str(p), "output": f"Escrito: {len(content)} chars", "success": True}
    except Exception as exc:
        return {"marker": "WRITE", "input": path, "output": str(exc), "success": False}


def _download(url: str, dest: str) -> dict:
    try:
        import urllib.request
        p = Path(dest.strip())
        if not p.is_absolute():
            p = ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, p)
        size = p.stat().st_size
        return {"marker": "GET", "input": url, "output": f"Baixado: {p} ({size/1024:.1f} KB)", "success": True}
    except Exception as exc:
        return {"marker": "GET", "input": url, "output": str(exc), "success": False}


def _pip_install(pkg: str) -> dict:
    log.info("◆PIP: %s", pkg)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg.strip(), "--quiet"],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        out = (result.stdout + result.stderr).strip() or "Instalado."
        return {"marker": "PIP", "input": pkg, "output": out[:500], "success": result.returncode == 0}
    except Exception as exc:
        return {"marker": "PIP", "input": pkg, "output": str(exc), "success": False}
