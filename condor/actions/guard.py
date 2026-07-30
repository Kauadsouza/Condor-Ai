"""
Guarda — a única trava do Condor.

Ele tem acesso total ao PC: roda qualquer comando, escreve em qualquer pasta,
instala o que quiser. A ÚNICA coisa que ele não faz sozinho é o que é
catastrófico e sem volta. Nesses casos ele para, pergunta a senha em voz alta
e só continua se você responder certo.

Quatro categorias travadas (configuráveis em data/config.yaml):
  destruir_sistema → format, diskpart, mkfs, apagar registro, escrever no disco cru
  apagar_massa     → remoção recursiva de pasta grande ou raiz de disco
  desligar         → shutdown, restart, logoff
  rede_seguranca   → desativar firewall/Defender, apagar redes wifi

Tudo — liberado ou barrado — vai pro log de auditoria (data/auditoria.log)
e pra tabela `acoes` do banco.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger("condor.guarda")

# ── O que é catastrófico ─────────────────────────────────────────────────────

PADROES: dict[str, list[str]] = {
    "destruir_sistema": [
        r"\bformat(-volume)?\s+(/\w+\s+)*[a-z]:",
        r"\bdiskpart\b",
        r"\bmkfs(\.\w+)?\b",
        r"\bcipher\s+/w",
        r"\b(clear|initialize|set)-disk\b",
        r"\bclear-content\s+.*\b[a-z]:\\(windows|system32)",
        r"\b(reg|reg\.exe)\s+delete\s+hk(lm|cu|cr|u|cc)",
        r"remove-item\s+.*\bhk(lm|cu):",
        r">\s*\\\\\.\\physicaldrive",
        r"\bbcdedit\b.*\b(/deletevalue|/delete)\b",
        r"\bbootrec\b",
        r"\bvssadmin\s+delete\s+shadows",
        r"\bwmic\s+shadowcopy\s+delete",
        r"\bwinsat\s+formal\b.*-v",
        r"\btakeown\s+/f\s+[a-z]:\\\s*$",
    ],
    "apagar_massa": [
        # Remoção recursiva apontando pra raiz de um disco — em qualquer ordem
        # de argumento. É o caso mais perigoso e o mais fácil de escrever sem
        # querer, então casa com o nome do disco em qualquer posição da linha.
        r"\b(remove-item|ri|rm|del|erase)\b(?=.*(-recurse|/s\b|\s-r\b))"
        r".*[\s'\"=]([a-z]:\\?)(?=[\s'\"]|$)",
        # Recursivo dentro de pasta de sistema ou da pasta de usuários
        r"\b(remove-item|rm|del|rd|rmdir)\b(?=.*(-recurse|/s\b|\s-r\b))"
        r".*\\(windows|program files( \(x86\))?|users|system32|programdata)\b",
        r"\brd\s+/s\b", r"\brmdir\s+/s\b",
        r"\brm\s+-rf?\s+[/~]",
        # Pipe clássico: lista a raiz de um disco (ou pasta de sistema) e joga
        # tudo no remove. Exige o caminho perigoso do lado do Get-ChildItem —
        # senão 'Get-ChildItem *.tmp | Remove-Item' cairia aqui, e isso é uso
        # normal e inofensivo.
        r"\bget-childitem\b[^|]*[\s'\"]([a-z]:\\?(?=[\s'\"]|$)"
        r"|[a-z]:\\(windows|users|program files|programdata))[^|]*\|\s*remove-item\b",
        # Equivalentes em Python
        r"shutil\.rmtree\s*\(\s*['\"]?([a-z]:[\\/]*|[\\/]|~[\\/]?)['\"]?\s*[,)]",
        r"os\.removedirs\s*\(",
    ],
    "desligar": [
        r"\bshutdown(\.exe)?\b\s+/?[srfp]",
        r"\bstop-computer\b", r"\brestart-computer\b",
        r"\blogoff\b", r"\bshutdown\s+-[srh]\b",
    ],
    "rede_seguranca": [
        r"\bnetsh\s+advfirewall\s+set\b.*\boff\b",
        r"\bset-netfirewallprofile\b.*-enabled\s+false",
        r"\bset-mppreference\b.*-disable\w*\s+\$?true",
        r"\badd-mppreference\b.*-exclusionpath",
        r"\bnetsh\s+wlan\s+delete\b",
        r"\b(sc|net)\s+stop\s+(windefend|mpssvc|wuauserv)",
        r"\bstop-service\b.*\b(windefend|mpssvc)\b",
        r"\bdisable-windowsoptionalfeature\b",
        r"\buninstall-windowsfeature\b",
    ],
}

_COMPILADOS = {
    cat: re.compile("|".join(p), re.IGNORECASE)
    for cat, p in PADROES.items()
}

DESCRICOES = {
    "destruir_sistema": "destruir o sistema",
    "apagar_massa": "apagar arquivos em massa",
    "desligar": "desligar ou reiniciar o PC",
    "rede_seguranca": "mexer na segurança ou na rede",
}

# Pastas onde apagar qualquer coisa já conta como catastrófico.
_PASTAS_SAGRADAS = [
    "c:\\windows", "c:\\program files", "c:\\program files (x86)",
    "c:\\programdata", "c:\\users", "c:\\$recycle.bin",
]


def _normalizar(texto: str) -> str:
    """Tira acento e baixa caixa — 'Format C:' e 'fórmat c:' viram o mesmo."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def classificar_comando(comando: str) -> str | None:
    """Devolve a categoria catastrófica do comando, ou None se for inofensivo."""
    alvo = _normalizar(comando)
    for categoria, rx in _COMPILADOS.items():
        if rx.search(alvo):
            return categoria
    return None


def classificar_caminho(caminho: str, recursivo: bool = False) -> str | None:
    """Apagar ESTE caminho é catastrófico? Raiz de disco e pasta de sistema são."""
    try:
        p = Path(caminho).expanduser().resolve()
    except Exception:
        return None

    alvo = _normalizar(str(p))
    # Raiz de qualquer disco (C:\, D:\)
    if re.fullmatch(r"[a-z]:\\?", alvo):
        return "destruir_sistema"
    if any(alvo == s or alvo.rstrip("\\") == s for s in _PASTAS_SAGRADAS):
        return "destruir_sistema"
    if any(alvo.startswith(s + "\\") for s in ("c:\\windows", "c:\\program files")):
        return "destruir_sistema"
    # Pasta pessoal inteira
    if recursivo and alvo.rstrip("\\") in (_normalizar(str(Path.home())),):
        return "apagar_massa"
    # Pasta grande: recursivo com muitos arquivos dentro
    if recursivo and p.is_dir():
        try:
            quantos = sum(1 for _ in p.rglob("*"))
            if quantos > 300:
                return "apagar_massa"
        except Exception:
            pass
    return None


# ── A guarda ─────────────────────────────────────────────────────────────────

# Assinatura do pedido de senha: (motivo, categoria) -> texto falado/digitado
PedidoSenha = Callable[[str, str], Awaitable[str | None]]


class Guarda:
    def __init__(self, config, memoria=None) -> None:
        self._cfg = config
        self._memoria = memoria
        self._pedir: PedidoSenha | None = None
        self._log_path = Path(__file__).parent.parent.parent / "data" / "auditoria.log"
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # Autorização válida por pouco tempo: se ele precisar de 2 comandos
        # da mesma categoria em sequência, não te enche o saco duas vezes.
        self._liberado_ate: dict[str, float] = {}

    def registrar_pedido_senha(self, fn: PedidoSenha) -> None:
        """A camada de voz/UI registra aqui COMO perguntar a senha."""
        self._pedir = fn

    # ── Classificação ──────────────────────────────────────────────────────

    def avaliar(self, ferramenta: str, argumentos: dict) -> str | None:
        """Categoria catastrófica desta chamada de ferramenta, ou None."""
        categoria = None

        if ferramenta in ("executar_powershell", "executar_python"):
            alvo = argumentos.get("comando") or argumentos.get("codigo") or ""
            categoria = classificar_comando(alvo)
        elif ferramenta == "deletar":
            categoria = classificar_caminho(argumentos.get("caminho", ""),
                                            bool(argumentos.get("recursivo")))
        elif ferramenta == "escrever_arquivo":
            categoria = classificar_caminho(argumentos.get("caminho", ""))

        if categoria and categoria not in self._cfg.seguranca.exigir_senha:
            return None       # categoria desligada na config → passa direto
        return categoria

    # ── Autorização ────────────────────────────────────────────────────────

    async def autorizar(self, categoria: str, descricao: str) -> bool:
        """Pede a senha e devolve se pode seguir. Sem forma de perguntar,
        BARRA — melhor não fazer do que fazer sem confirmação."""
        agora = time.time()
        if self._liberado_ate.get(categoria, 0) > agora:
            self.auditar(categoria, descricao, "LIBERADO (janela ativa)")
            return True

        if self._pedir is None:
            self.auditar(categoria, descricao, "BARRADO (sem canal pra pedir senha)")
            return False

        esperada = self._cfg.senha
        for tentativa in range(self._cfg.seguranca.tentativas_senha):
            motivo = (f"Isso vai {DESCRICOES.get(categoria, categoria)}. "
                      f"{descricao}. Me diz a senha pra eu seguir.")
            if tentativa:
                motivo = "Senha errada. Tenta de novo."
            resposta = await self._pedir(motivo, categoria)
            if resposta is None:
                self.auditar(categoria, descricao, "BARRADO (sem resposta)")
                return False
            if _senha_confere(resposta, esperada):
                # 90s de janela livre pra mesma categoria
                self._liberado_ate[categoria] = agora + 90
                self.auditar(categoria, descricao, "AUTORIZADO")
                return True

        self.auditar(categoria, descricao, "BARRADO (senha errada)")
        return False

    # ── Auditoria ──────────────────────────────────────────────────────────

    def auditar(self, ferramenta: str, entrada: str, resultado: str,
                sucesso: bool = True, exigiu_senha: bool = True) -> None:
        if not self._cfg.seguranca.auditoria:
            return
        carimbo = time.strftime("%Y-%m-%d %H:%M:%S")
        linha = f"[{carimbo}] {ferramenta} | {entrada[:200]} | {resultado}\n"
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(linha)
        except Exception:
            pass
        if self._memoria is not None:
            try:
                self._memoria.registrar_acao(ferramenta, entrada, resultado,
                                             sucesso, exigiu_senha)
            except Exception:
                pass


def _senha_confere(resposta: str, esperada: str) -> bool:
    """Compara com folga: veio por voz, então ignora acento, caixa, pontuação
    e o 'a senha é ...' que a transcrição costuma trazer junto."""
    limpa = _normalizar(resposta)
    limpa = re.sub(r"[^a-z0-9 ]", " ", limpa)
    limpa = re.sub(r"\b(a\s+)?senha\s+(e|eh|é)?\s*", " ", limpa)
    palavras = limpa.split()
    alvo = _normalizar(esperada)
    return alvo in palavras or limpa.strip() == alvo
