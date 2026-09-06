"""Ponte de dados do Condor local para a mente privada hospedada.

O modulo nao abre uma porta externa no PC. Ele faz somente conexoes HTTPS de
saida, usa um token do dono guardado no cofre e replica conversa, fatos e notas.
Ferramentas, arquivos, comandos, biometria e credenciais nunca entram no lote.
"""

from __future__ import annotations

import json
import logging
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from condor.memory.extractor import sanitizar_para_memoria

log = logging.getLogger("condor.cloud")
CONDOR_MIND_ID = "condor-kaua-primary-v1"


class CloudError(RuntimeError):
    """Falha segura e apresentavel da ponte cloud."""


def _iso(timestamp: object) -> str:
    try:
        value = float(timestamp)
    except (TypeError, ValueError):
        value = time.time()
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class CloudSyncClient:
    ACCESS = "CONDOR_CLOUD_ACCESS_TOKEN"
    REFRESH = "CONDOR_CLOUD_REFRESH_TOKEN"
    EXPIRES = "CONDOR_CLOUD_TOKEN_EXPIRES_AT"

    def __init__(self, config, vault, identity) -> None:
        self.config = config
        self.vault = vault
        self.identity = identity
        self.last_sync_at: float | None = None
        self.last_error = ""
        self.imported = 0
        self.uploaded = 0

    @property
    def configured(self) -> bool:
        cloud = self.config.cloud
        return bool(
            cloud.ativa
            and cloud.api_url
            and cloud.supabase_url
            and cloud.supabase_publishable_key
        )

    @property
    def device_key(self) -> str:
        return self.identity.device_id

    def _token(self, name: str, default: str = "") -> str:
        if not self.vault.unlocked:
            return default
        return str(self.vault.get(name, default) or default)

    def status(self) -> dict:
        authenticated = bool(self._token(self.REFRESH))
        return {
            "configured": self.configured,
            "mind_id": CONDOR_MIND_ID,
            "authenticated": authenticated,
            "connected": bool(authenticated and not self.last_error),
            "api_url": self.config.cloud.api_url if self.configured else "",
            "supabase_url": self.config.cloud.supabase_url if self.configured else "",
            "supabase_publishable_key": (
                self.config.cloud.supabase_publishable_key if self.configured else ""
            ),
            "device_key": self.device_key if self.vault.unlocked else None,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
            "uploaded": self.uploaded,
            "imported": self.imported,
            "interval_seconds": self.config.cloud.intervalo_sync_segundos,
            "pc_online": True,
        }

    @staticmethod
    def _decode_response(response) -> Any:
        raw = response.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 45,
    ) -> Any:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "Condor-Desktop/1.0",
            **(headers or {}),
        }
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return self._decode_response(response)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error")
            except (ValueError, UnicodeDecodeError, AttributeError):
                detail = None
            error = CloudError(str(detail or f"servico cloud recusou a operacao ({exc.code})"))
            error.status = exc.code  # type: ignore[attr-defined]
            raise error from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudError("nao foi possivel alcancar o Condor AI Cloud") from exc

    def login(self, email: str, password: str) -> dict:
        if not self.configured:
            raise CloudError("configure as URLs do Condor AI Cloud primeiro")
        if not self.vault.unlocked:
            raise CloudError("desbloqueie o cofre do Condor")
        email = str(email or "").strip()
        if not email or not password:
            raise CloudError("email e senha sao obrigatorios")
        url = f"{self.config.cloud.supabase_url}/auth/v1/token?grant_type=password"
        result = self._json_request(
            url,
            method="POST",
            payload={"email": email, "password": password},
            headers={"apikey": self.config.cloud.supabase_publishable_key},
        )
        self._save_session(result)
        self.last_error = ""
        return {"ok": True, "expires_at": self._token(self.EXPIRES)}

    def _save_session(self, payload: dict) -> None:
        access = str(payload.get("access_token") or "")
        refresh = str(payload.get("refresh_token") or "")
        if not access or not refresh:
            raise CloudError("Supabase nao devolveu uma sessao valida")
        expires_at = payload.get("expires_at")
        if not expires_at:
            expires_at = time.time() + max(60, int(payload.get("expires_in") or 3600))
        self.vault.set(self.ACCESS, access)
        self.vault.set(self.REFRESH, refresh)
        self.vault.set(self.EXPIRES, str(int(float(expires_at))))

    def _refresh(self) -> str:
        refresh = self._token(self.REFRESH)
        if not refresh:
            raise CloudError("conecte sua conta privada do Condor AI Cloud")
        url = f"{self.config.cloud.supabase_url}/auth/v1/token?grant_type=refresh_token"
        result = self._json_request(
            url,
            method="POST",
            payload={"refresh_token": refresh},
            headers={"apikey": self.config.cloud.supabase_publishable_key},
        )
        self._save_session(result)
        return self._token(self.ACCESS)

    def _access_token(self) -> str:
        access = self._token(self.ACCESS)
        try:
            expires = float(self._token(self.EXPIRES, "0"))
        except ValueError:
            expires = 0
        if not access or expires < time.time() + 60:
            return self._refresh()
        return access

    def _api(self, path: str, *, method: str = "GET", payload: dict | None = None) -> Any:
        if not self.configured:
            raise CloudError("Condor AI Cloud ainda nao configurado")
        token = self._access_token()
        url = f"{self.config.cloud.api_url}{path}"
        try:
            result = self._json_request(
                url,
                method=method,
                payload=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=120 if path == "/api/chat" else 45,
            )
            return self._canonical(result)
        except CloudError as exc:
            if getattr(exc, "status", None) != 401:
                raise
            token = self._refresh()
            result = self._json_request(
                url,
                method=method,
                payload=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=120 if path == "/api/chat" else 45,
            )
            return self._canonical(result)

    @staticmethod
    def _canonical(result: Any) -> Any:
        if not isinstance(result, dict) or result.get("mindId") != CONDOR_MIND_ID:
            raise CloudError("o servidor nao confirmou a mente canonica do Condor")
        return result

    def register_device(self) -> dict:
        return self._api(
            "/api/devices",
            method="POST",
            payload={
                "deviceKey": self.device_key,
                "name": f"Condor PC - {platform.node() or 'Windows'}"[:120],
                "kind": "desktop",
                "capabilities": ["chat", "notes", "sync"],
            },
        )

    def logout(self) -> None:
        if not self.vault.unlocked:
            return
        self.vault.delete(self.ACCESS)
        self.vault.delete(self.REFRESH)
        self.vault.delete(self.EXPIRES)
        self.last_error = ""

    def history(self, conversation_id: str = "") -> dict:
        query = ""
        if conversation_id:
            query = "?conversationId=" + urllib.parse.quote(conversation_id, safe="")
        return self._api("/api/history" + query)

    def notes(self) -> dict:
        return self._api("/api/notes")

    def create_note(self, title: str, body: str) -> dict:
        return self._api(
            "/api/notes",
            method="POST",
            payload={
                "title": sanitizar_para_memoria(title)[:160],
                "body": sanitizar_para_memoria(body)[:16000],
                "clientEventId": str(uuid.uuid4()),
                "deviceKey": self.device_key,
            },
        )

    def chat(self, message: str, conversation_id: str = "", _retried: bool = False) -> dict:
        """Le o SSE do backend e entrega a resposta pronta para a UI desktop."""
        text = sanitizar_para_memoria(message).strip()[:8000]
        payload = {
            "message": text,
            "clientMessageId": str(uuid.uuid4()),
            "deviceKey": self.device_key,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id
        token = self._access_token()
        request = urllib.request.Request(
            f"{self.config.cloud.api_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "Condor-Desktop/1.0",
            },
            method="POST",
        )
        answer: list[str] = []
        meta: dict = {}
        try:
            with urllib.request.urlopen(request, timeout=150) as response:
                event = ""
                for raw in response:
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        if event == "delta":
                            answer.append(str(data.get("text") or ""))
                        elif event == "meta":
                            meta.update(data)
                        elif event == "error":
                            raise CloudError(str(data.get("message") or "resposta interrompida"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and not _retried:
                self._refresh()
                return self.chat(message, conversation_id, True)
            raise CloudError(f"chat cloud recusado ({exc.code})") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudError("chat cloud indisponivel") from exc
        if meta.get("mindId") != CONDOR_MIND_ID:
            raise CloudError("o chat nao confirmou a mente canonica do Condor")
        return {"answer": "".join(answer).strip(), **meta}

    def sync(self, memory) -> dict:
        if not memory.unlocked:
            raise CloudError("memoria local bloqueada")
        snapshot = memory.cloud_snapshot()
        events: list[dict] = []
        for item in snapshot["messages"]:
            content = sanitizar_para_memoria(item["conteudo"])[:8000]
            events.append({
                "clientEventId": f"local-message-{item['id']}",
                "type": "message",
                "payload": {
                    "originId": str(item["id"]),
                    "conversationOriginId": f"session-{item['sessao']}",
                    "role": item["papel"],
                    "content": content,
                    "createdAt": _iso(item["ts"]),
                },
            })
        for item in snapshot["facts"]:
            stamp = int(float(item["atualizado"]) * 1000)
            events.append({
                "clientEventId": f"local-fact-{item['id']}-{stamp}",
                "type": "fact",
                "payload": {
                    "originId": str(item["id"]),
                    "category": str(item["categoria"])[:40],
                    "key": str(item["chave"])[:80],
                    "value": sanitizar_para_memoria(item["valor"])[:2000],
                    "confidence": min(1.0, max(0.0, float(item["confianca"]))),
                    "updatedAt": _iso(item["atualizado"]),
                },
            })
        for item in snapshot["notes"]:
            stamp = int(float(item["atualizado"]) * 1000)
            events.append({
                "clientEventId": f"local-note-{item['id']}-{stamp}",
                "type": "note",
                "payload": {
                    "originId": str(item["id"]),
                    "title": sanitizar_para_memoria(item["titulo"])[:160],
                    "body": sanitizar_para_memoria(item["conteudo"])[:16000],
                    "updatedAt": _iso(item["atualizado"]),
                },
            })

        uploaded = 0
        for offset in range(0, len(events), 500):
            result = self._api(
                "/api/sync",
                method="POST",
                payload={"deviceKey": self.device_key, "events": events[offset:offset + 500]},
            )
            uploaded += int(result.get("accepted") or 0)

        cursor = memory.cloud_cursor()
        query = urllib.parse.urlencode({"deviceKey": self.device_key, "since": cursor})
        result = self._api(f"/api/sync?{query}")
        imported = 0
        for event in result.get("events") or []:
            if str(event.get("deviceKey") or "") == self.device_key:
                continue
            if memory.importar_cloud_event(event):
                imported += 1
        memory.set_cloud_cursor(int(result.get("cursor") or cursor))
        self.last_sync_at = time.time()
        self.last_error = ""
        self.imported = imported
        self.uploaded = uploaded
        return {"ok": True, "uploaded": uploaded, "imported": imported, "cursor": memory.cloud_cursor()}

    def safe_sync(self, memory) -> dict:
        try:
            return self.sync(memory)
        except Exception as exc:
            self.last_error = str(exc)[:240]
            log.warning("Condor AI Cloud nao sincronizou: %s", self.last_error)
            return {"ok": False, "error": self.last_error}
