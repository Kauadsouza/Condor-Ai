"""Atualização automática do CONDOR instalado, a partir do GitHub do dono.

Roda antes de o núcleo subir (ao abrir o app e no início em segundo plano):

1. Só age numa pasta criada pelo CondorSetup (marca ``.condor-instalado``);
   nunca num repositório de desenvolvimento.
2. Pergunta ao GitHub se ``main`` está À FRENTE da versão instalada. Versão
   local mais nova (ainda não enviada) nunca é trocada por uma mais velha.
3. Baixa o código daquele commit, extrai sem sair da pasta, troca só os
   arquivos do aplicativo e apaga os que deixaram de existir. ``.venv``,
   ``runtime``, ``python`` e ``~/.condor`` (memória, cofre, modelos) nunca
   são tocados.
4. Se as dependências mudaram, reinstala as bibliotecas no ambiente do app.

Sem internet ou com qualquer erro, o CONDOR abre com a versão que já tem.
Só usa a biblioteca padrão: roda antes de qualquer coisa carregar.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORIO = "Kauadsouza/Condor-Ai"
RAMO = "main"
API = f"https://api.github.com/repos/{REPOSITORIO}"
MARCA_INSTALADO = ".condor-instalado"
ARQUIVO_VERSAO = ".condor-versao"
ARQUIVO_MANIFESTO = ".condor-arquivos.json"
# Nada disso vem do GitHub nem pode ser apagado por uma atualização.
PRESERVAR = {".venv", "runtime", "python", "dist", "build", "__pycache__", "cloud", ".github",
             MARCA_INSTALADO, ARQUIVO_VERSAO, ARQUIVO_MANIFESTO, "Condor.exe"}
DEPENDENCIAS = ("pyproject.toml", "requirements.txt")
LIMITE_PACOTE = 200 * 1024 * 1024


def _estado() -> Path:
    raiz = os.environ.get("CONDOR_HOME")
    return Path(raiz).expanduser() if raiz else Path.home() / ".condor"


def _avisar(texto: str) -> None:
    """A janela de carregamento do Condor.exe lê esta linha e mostra na tela."""
    try:
        alvo = _estado() / "runtime" / "atualizacao.txt"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
    except OSError:
        pass


def _registrar(texto: str) -> None:
    try:
        log = _estado() / "logs" / "atualizacao.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as saida:
            saida.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n")
    except OSError:
        pass


def _pedir(url: str, timeout: float) -> bytes:
    pedido = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Condor-Atualizador",
    })
    with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
        return resposta.read(LIMITE_PACOTE + 1)


def versao_instalada(raiz: Path) -> str:
    try:
        return (raiz / ARQUIVO_VERSAO).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def versao_remota_mais_nova(atual: str, pedir=_pedir) -> str | None:
    """Commit de ``main`` se ele estiver à frente de ``atual``; senão None."""
    dados = json.loads(pedir(f"{API}/commits/{RAMO}", 5))
    remoto = str(dados.get("sha") or "")
    if len(remoto) != 40 or remoto == atual:
        return None
    if not atual:
        return remoto   # instalação sem versão registrada: alinha com o GitHub
    try:
        comparacao = json.loads(pedir(f"{API}/compare/{atual}...{remoto}", 5))
    except urllib.error.HTTPError:
        return None     # versão local desconhecida no GitHub (não enviada): não mexe
    return remoto if comparacao.get("status") == "ahead" else None


def _caminho_seguro(raiz: Path, nome: str) -> Path | None:
    partes = PurePosixPath(nome).parts[1:]   # tira a pasta "Kauadsouza-Condor-Ai-<sha>/"
    if not partes or any(p in ("..", "") or ":" in p for p in partes):
        return None
    if partes[0] in PRESERVAR:
        return None
    alvo = (raiz / Path(*partes)).resolve()
    return alvo if raiz.resolve() in alvo.parents else None


def aplicar_pacote(raiz: Path, pacote: bytes, versao: str) -> dict:
    """Troca o código pelo do pacote. Devolve o que mudou (para testes e log)."""
    raiz = raiz.resolve()
    antigos = set()
    try:
        antigos = set(json.loads((raiz / ARQUIVO_MANIFESTO).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    hash_deps_antes = _hash_dependencias(raiz)
    novos: list[str] = []
    with zipfile.ZipFile(io.BytesIO(pacote)) as zip_:
        with tempfile.TemporaryDirectory(dir=str(raiz)) as tmp:
            preparo = Path(tmp)
            for entrada in zip_.infolist():
                if entrada.is_dir():
                    continue
                alvo = _caminho_seguro(raiz, entrada.filename)
                if alvo is None:
                    continue
                relativo = alvo.relative_to(raiz).as_posix()
                destino = preparo / relativo
                destino.parent.mkdir(parents=True, exist_ok=True)
                with zip_.open(entrada) as origem, destino.open("wb") as saida:
                    shutil.copyfileobj(origem, saida)
                novos.append(relativo)
            if len(novos) < 50 or "condor/server.py" not in novos:
                raise RuntimeError("pacote do GitHub incompleto; atualização cancelada")
            # Só depois de tudo extraído com sucesso a pasta do app é tocada.
            for relativo in novos:
                final = raiz / relativo
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(preparo / relativo, final)
    removidos = []
    for relativo in sorted(antigos - set(novos)):
        alvo = (raiz / relativo).resolve()
        if raiz in alvo.parents and alvo.is_file() and PurePosixPath(relativo).parts[0] not in PRESERVAR:
            alvo.unlink()
            removidos.append(relativo)
    (raiz / ARQUIVO_MANIFESTO).write_text(json.dumps(sorted(novos)), encoding="utf-8")
    (raiz / ARQUIVO_VERSAO).write_text(versao, encoding="utf-8")
    return {"arquivos": len(novos), "removidos": removidos,
            "dependencias_mudaram": _hash_dependencias(raiz) != hash_deps_antes}


def _hash_dependencias(raiz: Path) -> str:
    h = hashlib.sha256()
    for nome in DEPENDENCIAS:
        try:
            h.update((raiz / nome).read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def _reinstalar_bibliotecas(raiz: Path) -> None:
    python = raiz / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return
    opcoes = {"creationflags": 0x08000000} if os.name == "nt" else {}
    subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-e", str(raiz)],
        cwd=str(raiz), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900,
        check=False, **opcoes,
    )


def atualizar(raiz: Path) -> bool:
    """Atualiza se houver versão nova. Nunca levanta erro: no pior caso, não atualiza."""
    raiz = Path(raiz).resolve()
    if not (raiz / MARCA_INSTALADO).is_file() or os.environ.get("CONDOR_SEM_ATUALIZAR"):
        return False
    try:
        nova = versao_remota_mais_nova(versao_instalada(raiz))
        if not nova:
            return False
        _avisar("atualizando o CONDOR...")
        _registrar(f"baixando {nova[:12]}")
        pacote = _pedir(f"{API}/zipball/{nova}", 60)
        if len(pacote) > LIMITE_PACOTE:
            raise RuntimeError("pacote grande demais")
        resultado = aplicar_pacote(raiz, pacote, nova)
        if resultado["dependencias_mudaram"]:
            _avisar("instalando bibliotecas novas...")
            _reinstalar_bibliotecas(raiz)
        _registrar(f"atualizado para {nova[:12]}: {resultado['arquivos']} arquivos, "
                   f"{len(resultado['removidos'])} removidos")
        return True
    except Exception as exc:   # sem internet, GitHub fora, pacote ruim: segue com o que tem
        _registrar(f"sem atualização: {type(exc).__name__}: {exc}")
        return False
    finally:
        _avisar("")


if __name__ == "__main__":
    print("atualizado" if atualizar(Path(__file__).resolve().parent.parent) else "sem mudança")
    sys.exit(0)
