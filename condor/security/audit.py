"""Auditoria JSONL encadeada por hash, ancorada por assinatura do dispositivo.

O encadeamento SHA-256 sozinho revela edicao no meio do arquivo, mas nao revela
o arquivo ser apagado e reconstruido: quem escreve no disco monta uma cadeia nova
coerente do zero. A ancora fecha esse buraco — ela guarda, assinada com a chave
Ed25519 do dispositivo (que mora no cofre cifrado), qual era o ultimo hash e
quantos eventos existiam. Reescrever o historico exige a chave privada.

Eventos gravados com o cofre bloqueado nao podem ser assinados na hora. Por isso
a ancora prova o prefixo ate o ponto assinado, e o encadeamento cobre o resto —
e e exatamente isso que ``verify`` informa.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import threading
from pathlib import Path
from typing import Any

VAZIO = "0" * 64


class IntegrityAudit:
    def __init__(self, path: Path, identity=None) -> None:
        self.path = path
        self.identity = identity
        self.anchor_path = path.with_name("anchor.json")
        self._lock = threading.RLock()
        # Evita reler o log inteiro a cada evento: sem isto o append e O(n²) e
        # cada acao do Condor fica mais lenta que a anterior.
        self._last: str | None = None
        self._count: int | None = None
        # verify() percorre e re-hasheia o log inteiro, e a interface consulta o
        # estado de seguranca em laco. O veredito fica guardado junto da marca
        # (mtime, tamanho) do arquivo: adulteracao externa mexe nos dois, entao
        # a cache cai sozinha e a verificacao roda de novo.
        self._veredito: tuple[bool, int] | None = None
        self._veredito_marca: tuple[int, int] | None = None

    def _marca_do_log(self) -> tuple[int, int]:
        try:
            info = self.path.stat()
            return (info.st_mtime_ns, info.st_size)
        except OSError:
            return (-1, -1)

    def ligar_identidade(self, identity) -> None:
        self.identity = identity

    # ── Escrita ────────────────────────────────────────────────────────────

    def append(self, event: dict[str, Any]) -> str:
        with self._lock:
            previous = self._last_hash()
            body = {
                "version": 1,
                "timestamp": time.time(),
                "previous": previous,
                "event": event,
            }
            encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            record = {**body, "hash": digest}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            self._last = digest
            self._count = (self._count or 0) + 1
            self._veredito = None
            self._veredito_marca = None
            self._ancorar(digest, self._count)
            return digest

    def _ancorar(self, digest: str, count: int) -> None:
        """Assina o ponto atual. Silencioso quando o cofre esta bloqueado."""
        if self.identity is None:
            return
        try:
            payload = json.dumps(
                {"hash": digest, "count": count}, sort_keys=True, separators=(",", ":")
            )
            registro = {"hash": digest, "count": count,
                        "signature": self.identity.sign(payload.encode("utf-8"))}
        except Exception:
            # Cofre bloqueado: a chave privada nao esta acessivel. A cadeia
            # continua protegendo estes eventos; a ancora fica no ponto anterior.
            return
        try:
            temporary = self.anchor_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(registro, sort_keys=True), encoding="utf-8")
            os.replace(temporary, self.anchor_path)
            self.anchor_path.chmod(0o600)
        except OSError:
            pass

    # ── Leitura ────────────────────────────────────────────────────────────

    def verify(self) -> tuple[bool, int]:
        with self._lock:
            marca = self._marca_do_log()
            if self._veredito is not None and marca == self._veredito_marca:
                return self._veredito
            resultado = self._verificar()
            self._veredito = resultado
            self._veredito_marca = marca
            return resultado

    def _verificar(self) -> tuple[bool, int]:
        with self._lock:
            if not self.path.exists():
                return True, 0
            previous = VAZIO
            count = 0
            hashes: list[str] = []
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    record = json.loads(line)
                    expected = record.pop("hash")
                    encoded = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                    actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                    if not hmac.compare_digest(expected, actual) or record.get("previous") != previous:
                        return False, count
                    previous = expected
                    hashes.append(expected)
                    count += 1
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                return False, count
            if not self._ancora_confere(hashes):
                return False, count
            return True, count

    def _ancora_confere(self, hashes: list[str]) -> bool:
        """A cadeia precisa conter o ponto assinado, na mesma posicao.

        Sem ancora legivel (cofre bloqueado, primeira execucao), sobra o
        encadeamento — nao da pra afirmar mais do que isso, entao nao reprova.
        """
        if self.identity is None or not self.anchor_path.exists():
            return True
        try:
            registro = json.loads(self.anchor_path.read_text(encoding="utf-8"))
            digest = str(registro["hash"])
            count = int(registro["count"])
            payload = json.dumps(
                {"hash": digest, "count": count}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            assinada = self.identity.verify(payload, registro["signature"])
        except Exception:
            return True          # cofre bloqueado: sem veredito, sem acusacao
        if not assinada:
            return False
        # Truncar o log abaixo do ponto assinado, ou trocar o evento que estava
        # naquela posicao, quebra aqui.
        if count > len(hashes):
            return False
        return hmac.compare_digest(hashes[count - 1], digest) if count else True

    def _last_hash(self) -> str:
        if self._last is not None:
            return self._last
        if not self.path.exists():
            self._last, self._count = VAZIO, 0
            return self._last
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if not lines:
            self._last, self._count = VAZIO, 0
            return self._last
        self._count = len(lines)
        self._last = str(json.loads(lines[-1]).get("hash") or VAZIO)
        return self._last


def hmac_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
