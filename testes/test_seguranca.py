"""Segurança: o CONDOR falha fechado.

Sem a sessão local (segredo de boot + cookie), nenhuma rota da API pode
responder com sucesso — nem as que existirem no futuro, porque o teste
percorre todas as rotas registradas no servidor. E a auditoria que protege o
histórico de ações não aceita uma âncora adulterada como "íntegra".
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Rotas que respondem antes da sessão por desenho: abrir a sessão em si
# (recusa sem segredo, testado abaixo) e o redirecionamento da raiz.
LIVRES = {("POST", "/api/session")}
NEGADO = {401, 403, 404, 405, 409, 410, 422, 423, 429}


class FailClosedTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._antes = os.environ.get("CONDOR_HOME")
        os.environ["CONDOR_HOME"] = self._tmp.name

    def tearDown(self):
        if self._antes is None:
            os.environ.pop("CONDOR_HOME", None)
        else:
            os.environ["CONDOR_HOME"] = self._antes
        self._tmp.cleanup()

    def test_every_api_route_denies_without_a_local_session(self):
        from fastapi.testclient import TestClient
        from condor.config import Config
        from condor.server import montar

        app, _ = montar(Config())
        cliente = TestClient(app, base_url="http://127.0.0.1:7777")
        vazou = []
        for rota in app.routes:
            caminho = getattr(rota, "path", "")
            if not caminho.startswith("/api"):
                continue
            concreto = caminho.replace("{", "").replace("}", "")
            for metodo in sorted(getattr(rota, "methods", set()) - {"HEAD", "OPTIONS"}):
                if (metodo, caminho) in LIVRES:
                    continue
                resposta = cliente.request(metodo, concreto, json={})
                if resposta.status_code not in NEGADO:
                    vazou.append(f"{metodo} {caminho} -> {resposta.status_code}")
        self.assertEqual(vazou, [], "rotas que responderam sem sessão: " + "; ".join(vazou))

    def test_session_is_refused_without_the_boot_secret(self):
        from fastapi.testclient import TestClient
        from condor.config import Config
        from condor.server import montar

        app, _ = montar(Config())
        cliente = TestClient(app, base_url="http://127.0.0.1:7777")
        sem_segredo = cliente.post("/api/session", headers={
            "Origin": "http://127.0.0.1:7777", "X-Condor-Client": "desktop-ui",
        })
        self.assertEqual(sem_segredo.status_code, 403)
        errado = cliente.post("/api/session", headers={
            "Origin": "http://127.0.0.1:7777", "X-Condor-Client": "desktop-ui",
            "X-Condor-Token": "chute-de-quem-nao-leu-o-arquivo",
        })
        self.assertEqual(errado.status_code, 403)


class AuditAnchorTests(unittest.TestCase):
    """Âncora do histórico de ações corrompida é adulteração, não "sem veredito"."""

    def test_garbage_anchor_fails_closed(self):
        from condor.security.audit import IntegrityAudit

        class Identidade:
            def verify(self, _payload, _assinatura):
                return True

        with tempfile.TemporaryDirectory() as tmp:
            log = IntegrityAudit(Path(tmp) / "actions.jsonl")
            log.identity = Identidade()
            log.anchor_path.write_text("{}", encoding="utf-8")
            self.assertFalse(log._ancora_confere([]))
            log.anchor_path.write_text("isso nao e json", encoding="utf-8")
            self.assertFalse(log._ancora_confere([]))

    def test_locked_vault_still_gives_no_verdict(self):
        from condor.security.audit import IntegrityAudit

        class CofreBloqueado:
            def verify(self, _payload, _assinatura):
                raise RuntimeError("cofre bloqueado")

        with tempfile.TemporaryDirectory() as tmp:
            log = IntegrityAudit(Path(tmp) / "actions.jsonl")
            log.identity = CofreBloqueado()
            log.anchor_path.write_text(json.dumps({"hash": "a" * 64, "count": 0, "signature": "x"}), encoding="utf-8")
            self.assertTrue(log._ancora_confere([]))


if __name__ == "__main__":
    unittest.main()
