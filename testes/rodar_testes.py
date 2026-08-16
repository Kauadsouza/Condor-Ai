"""Testes locais do Condor 2.0. Nao usam API, microfone, tela nem rede."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from condor.brain.tools import ESQUEMAS, FUNCOES
from condor.brain.client import Cerebro
from condor.actions import executor
from condor.actions.guard import Guarda
from condor.config import Config, salvar_config
from condor.memory.db import Memoria
from condor.security.approval import OwnerAuth
from condor.security.audit import IntegrityAudit
from condor.security.identity import DeviceIdentity
from condor.security.integrity import CodeIntegrity
from condor.security.policy import AutonomyProfile, PolicyEngine, RiskLevel, action_digest
from condor.security.session import LocalSessionSecurity
from condor.security.vault import CondorVault, VaultError


PASS = "uma frase secreta longa e exclusiva"


class VaultTests(unittest.TestCase):
    def test_roundtrip_and_no_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vault.json"
            vault = CondorVault(path)
            vault.initialize(PASS, {"token": "segredo-super-privado"})
            self.assertNotIn("segredo-super-privado", path.read_text("utf-8"))
            vault.lock()
            vault.unlock(PASS)
            self.assertEqual(vault.get("token"), "segredo-super-privado")

    def test_wrong_passphrase_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = CondorVault(Path(tmp) / "vault.json")
            vault.initialize(PASS, {"x": 1})
            vault.lock()
            with self.assertRaises(VaultError):
                vault.unlock("outra frase secreta longa")

    def test_rotate(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = CondorVault(Path(tmp) / "vault.json")
            vault.initialize(PASS, {"x": 42})
            vault.rotate(PASS, "uma frase substituta longa e segura")
            vault.lock()
            vault.unlock("uma frase substituta longa e segura")
            self.assertEqual(vault.get("x"), 42)

    def test_device_identity_is_stable_and_signs(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = CondorVault(Path(tmp) / "vault.json")
            vault.initialize(PASS, {})
            identity = DeviceIdentity(vault)
            first = identity.ensure()
            signature = identity.sign(b"condor")
            self.assertTrue(identity.verify(b"condor", signature))
            self.assertFalse(identity.verify(b"alterado", signature))
            self.assertEqual(first, DeviceIdentity(vault).ensure())

    def test_signed_code_manifest_detects_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            package = root / "condor"
            package.mkdir(parents=True)
            source = package / "core.py"
            source.write_text("NAME = 'Condor'\n", encoding="utf-8")
            vault = CondorVault(Path(tmp) / "vault.json")
            vault.initialize(PASS, {})
            identity = DeviceIdentity(vault)
            identity.ensure()
            check = CodeIntegrity(Path(tmp) / "manifest.json", identity, root)
            self.assertEqual(check.refresh(), 1)
            self.assertTrue(check.verify()[0])
            source.write_text("NAME = 'alterado'\n", encoding="utf-8")
            self.assertFalse(check.verify()[0])


class ApprovalTests(unittest.TestCase):
    def test_exact_and_single_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = OwnerAuth(Path(tmp) / "owner.json")
            owner.setup(PASS)
            digest = action_digest("deletar", {"caminho": "/tmp/a"})
            challenge = owner.challenge(digest, "apagar a")
            token = owner.approve(challenge.id, PASS)
            self.assertIsNotNone(token)
            self.assertFalse(owner.consume(token, action_digest("deletar", {"caminho": "/tmp/b"})))
            self.assertFalse(owner.consume(token, digest))

    def test_wrong_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = OwnerAuth(Path(tmp) / "owner.json")
            owner.setup(PASS)
            challenge = owner.challenge("a" * 64, "acao")
            self.assertIsNone(owner.approve(challenge.id, "frase incorreta mas comprida"))


class PolicyTests(unittest.TestCase):
    def test_shell_and_python_are_blocked(self):
        policy = PolicyEngine(AutonomyProfile.ADMIN)
        for tool in ("executar_powershell", "executar_python", "instalar_pacote"):
            self.assertEqual(policy.decide(tool, {}).risk, RiskLevel.BLOCKED)

    def test_delete_always_requires_approval(self):
        decision = PolicyEngine(AutonomyProfile.ADMIN).decide("deletar", {"caminho": "x"})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_assistant_reviews_file_read(self):
        decision = PolicyEngine(AutonomyProfile.ASSISTANT).decide("ler_arquivo", {"caminho": "x"})
        self.assertTrue(decision.requires_approval)

    def test_assistant_reviews_local_metadata_and_web(self):
        policy = PolicyEngine(AutonomyProfile.ASSISTANT)
        for tool in ("info_sistema", "listar_pasta", "buscar_web", "ler_site"):
            self.assertTrue(policy.decide(tool, {}).requires_approval)

    def test_operator_can_read_allowed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            decision = PolicyEngine(AutonomyProfile.OPERATOR, [Path(tmp)]).decide(
                "ler_arquivo", {"caminho": str(Path(tmp) / "a.txt")}
            )
            self.assertTrue(decision.allowed)
            self.assertFalse(decision.requires_approval)

    def test_path_escape_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            decision = PolicyEngine(AutonomyProfile.ADMIN, [Path(tmp)]).decide(
                "ler_arquivo", {"caminho": str(Path(tmp).parent / "fora.txt")}
            )
            self.assertFalse(decision.allowed)

    def test_simulation_does_not_execute(self):
        decision = PolicyEngine(AutonomyProfile.ADMIN, simulation=True).decide(
            "escrever_arquivo", {"caminho": "x", "conteudo": "y"}
        )
        self.assertTrue(decision.simulated)
        self.assertFalse(decision.allowed)

    def test_observer_cannot_mutate(self):
        decision = PolicyEngine(AutonomyProfile.OBSERVER).decide("abrir", {"alvo": "x"})
        self.assertFalse(decision.allowed)

    def test_application_names_reject_command_injection(self):
        malicious = "calc'; Start-Process powershell #"
        self.assertFalse(executor.abrir(malicious)["ok"])
        self.assertFalse(executor.fechar_app(malicious)["ok"])
        self.assertFalse(executor.focar_janela(malicious)["ok"])


class OwnerSessionTests(unittest.TestCase):
    def test_locked_owner_cannot_use_pc_and_unlock_enables_fixed_admin_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("CONDOR_HOME")
            os.environ["CONDOR_HOME"] = tmp
            try:
                config = Config(seguranca={
                    "perfil": "admin",
                    "simulacao": False,
                    "pastas_permitidas": [tmp],
                })
                guard = Guarda(config)
                guard.configurar_dono(PASS)
                locked = guard.avaliar("abrir", {"alvo": "notepad"})
                self.assertFalse(locked.allowed)
                self.assertIn("bloqueado", locked.reason.lower())

                guard.unlock_owner_session()
                self.assertTrue(guard.owner_session_active)
                self.assertEqual(config.seguranca.perfil, "admin")
                self.assertFalse(config.seguranca.simulacao)
                destructive = guard.avaliar("deletar", {"caminho": str(Path(tmp) / "arquivo.txt")})
                self.assertTrue(destructive.allowed)
                self.assertTrue(destructive.requires_approval)
                self.assertTrue(asyncio.run(guard.autorizar(destructive, "excluir arquivo permitido")))

                guard.lock_owner_session()
                self.assertFalse(guard.owner_session_active)
                self.assertFalse(guard.avaliar("abrir", {"alvo": "notepad"}).allowed)
            finally:
                if previous is None:
                    os.environ.pop("CONDOR_HOME", None)
                else:
                    os.environ["CONDOR_HOME"] = previous


class AuditTests(unittest.TestCase):
    def test_chain_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            audit = IntegrityAudit(path)
            audit.append({"a": 1})
            audit.append({"b": 2})
            self.assertEqual(audit.verify(), (True, 2))
            path.write_text(path.read_text("utf-8").replace('"a": 1', '"a": 9'), "utf-8")
            self.assertFalse(audit.verify()[0])


class SessionSecurityTests(unittest.TestCase):
    def test_loopback_only(self):
        security = LocalSessionSecurity("127.0.0.1", 7777)
        self.assertTrue(security.host_allowed("127.0.0.1:7777"))
        self.assertTrue(security.origin_allowed("http://127.0.0.1:7777"))
        self.assertFalse(security.host_allowed("condor.example.com"))
        self.assertFalse(security.origin_allowed("https://evil.example"))

    def test_token_constant_validation(self):
        security = LocalSessionSecurity("127.0.0.1", 7777)
        self.assertTrue(security.token_valid(security.token))
        self.assertFalse(security.token_valid("wrong"))
        security._expires_at = 0
        self.assertFalse(security.token_valid(security.token))

    def test_same_origin_client_and_rate_controls(self):
        security = LocalSessionSecurity("127.0.0.1", 7777)
        self.assertTrue(security.client_allowed("desktop-ui"))
        self.assertTrue(security.client_allowed("hub-local"))
        self.assertFalse(security.client_allowed("website"))
        self.assertTrue(security.request_allowed(
            "http://127.0.0.1:7777", None, "same-origin", "POST"
        ))
        self.assertFalse(security.request_allowed(
            "http://127.0.0.1:9999", None, "same-site", "POST"
        ))
        self.assertTrue(security.request_allowed(
            None, "http://127.0.0.1:7777/ui/index.html", "same-origin", "GET"
        ))
        self.assertTrue(security.rate_allowed("test", 2, 60))
        self.assertTrue(security.rate_allowed("test", 2, 60))
        self.assertFalse(security.rate_allowed("test", 2, 60))

    def test_authentication_backoff(self):
        security = LocalSessionSecurity("127.0.0.1", 7777)
        for _ in range(3):
            self.assertEqual(security.auth_failed("unlock"), 0)
        self.assertGreaterEqual(security.auth_failed("unlock"), 2)
        allowed, wait = security.auth_allowed("unlock")
        self.assertFalse(allowed)
        self.assertGreaterEqual(wait, 1)
        security.auth_succeeded("unlock")
        self.assertEqual(security.auth_allowed("unlock"), (True, 0))

    def test_server_requires_local_session_and_sets_up_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("CONDOR_HOME")
            os.environ["CONDOR_HOME"] = tmp
            try:
                from fastapi.testclient import TestClient
                from condor.server import montar

                app, session = montar(Config())
                opened = []
                session.abrir_aplicativo = lambda: opened.append(True) or True
                client = TestClient(app, base_url="http://127.0.0.1:7777")
                self.assertEqual(client.get("/api/estado").status_code, 403)
                self.assertEqual(client.post("/api/app/abrir").status_code, 403)
                root = client.get("/", follow_redirects=False)
                self.assertEqual(root.status_code, 307)
                self.assertEqual(root.headers["location"], "/ui/index.html")
                self.assertEqual(
                    client.post("/api/session", headers={"Origin": "https://evil.example"}).status_code,
                    403,
                )
                self.assertEqual(
                    client.post(
                        "/api/session",
                        headers={"Origin": "http://127.0.0.1:7777"},
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.post(
                        "/api/session",
                        headers={
                            "Origin": "http://127.0.0.1:7777",
                            "X-Condor-Client": "desktop-ui",
                            "Content-Length": str(1024 * 1024 + 1),
                        },
                    ).status_code,
                    413,
                )
                response = client.post(
                    "/api/session", headers={
                        "Origin": "http://127.0.0.1:7777",
                        "X-Condor-Client": "desktop-ui",
                    }
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn("SameSite=strict", response.headers["set-cookie"])
                client.headers.update({"Origin": "http://127.0.0.1:7777"})
                self.assertEqual(
                    client.post(
                        "/api/emergencia/parar",
                        headers={"Origin": "http://127.0.0.1:9999"},
                    ).status_code,
                    403,
                )
                app_open = client.post("/api/app/abrir")
                self.assertEqual(app_open.status_code, 200, app_open.text)
                self.assertEqual(app_open.json()["app"], "Condor")
                self.assertEqual(opened, [True])
                state_headers = client.get("/api/estado").headers
                self.assertIn("form-action 'self'", state_headers["content-security-policy"])
                self.assertEqual(state_headers["cross-origin-opener-policy"], "same-origin")
                self.assertEqual(state_headers["cross-origin-resource-policy"], "same-origin")
                self.assertEqual(state_headers["x-robots-tag"], "noindex, nofollow, noarchive")
                setup = client.post("/api/seguranca/configurar", json={
                    "owner": "Kaua", "passphrase": PASS,
                })
                self.assertEqual(setup.status_code, 200, setup.text)
                state = client.get("/api/seguranca/estado").json()
                self.assertTrue(state["code_integrity"]["ok"])
                self.assertTrue(state["device_id"].startswith("condor-"))
                self.assertTrue(state["owner_session_active"])
                self.assertEqual(state["profile"], "admin")
                self.assertFalse(state["simulation"])
                self.assertEqual(
                    client.post("/api/seguranca/politica", json={
                        "profile": "operator", "simulation": True, "passphrase": PASS,
                    }).status_code,
                    404,
                )
                stopped = client.post("/api/emergencia/parar")
                self.assertEqual(stopped.status_code, 200, stopped.text)
                stopped_state = client.get("/api/seguranca/estado").json()
                self.assertTrue(stopped_state["emergency_stop"])
                self.assertFalse(stopped_state["vault_unlocked"])
                self.assertFalse(stopped_state["owner_session_active"])
                resumed = client.post("/api/emergencia/retomar", json={"passphrase": PASS})
                self.assertEqual(resumed.status_code, 200, resumed.text)
                self.assertFalse(resumed.json()["vault_unlocked"])
                unlocked = client.post("/api/seguranca/desbloquear", json={"passphrase": PASS})
                self.assertEqual(unlocked.status_code, 200, unlocked.text)
                self.assertTrue(client.get("/api/seguranca/estado").json()["owner_session_active"])
            finally:
                if previous is None:
                    os.environ.pop("CONDOR_HOME", None)
                else:
                    os.environ["CONDOR_HOME"] = previous


class MemoryTests(unittest.TestCase):
    def test_encrypted_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.enc"
            key = os.urandom(32)
            memory = Memoria(path)
            memory.inicializar()
            memory.unlock(key)
            memory.salvar_fato("pessoal", "nome", "conteudo ultrassecreto")
            memory.lock()
            self.assertTrue(path.exists())
            self.assertNotIn("conteudo ultrassecreto", path.read_text("utf-8"))

            reopened = Memoria(path)
            reopened.inicializar()
            reopened.unlock(key)
            self.assertIn("ultrassecreto", reopened.fatos_recentes()[0]["valor"])

    def test_wrong_memory_key_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.enc"
            memory = Memoria(path)
            memory.inicializar()
            memory.unlock(os.urandom(32))
            memory.salvar_fato("x", "y", "z")
            memory.lock()
            reopened = Memoria(path)
            reopened.inicializar()
            with self.assertRaises(RuntimeError):
                reopened.unlock(os.urandom(32))

    def test_hub_data_is_seeded_crud_and_encrypted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hub-memory.enc"
            key = os.urandom(32)
            memory = Memoria(path)
            memory.inicializar()
            self.assertTrue(memory.hub_snapshot()["locked"])
            memory.unlock(key)
            snapshot = memory.hub_snapshot()
            self.assertFalse(snapshot["locked"])
            self.assertTrue(any(item["id"] == "condor-x" for item in snapshot["projects"]))
            task = memory.hub_create_task("Validar o Hub", "condor", "alta")
            self.assertTrue(memory.hub_update_task(task["id"], "concluida"))
            note = memory.hub_create_note("Privada", "conteudo cifrado do Hub", "condor")
            self.assertTrue(memory.hub_update_note(note["id"], "Atualizada", "conteudo atualizado do Hub"))
            memory.lock()
            self.assertNotIn("conteudo cifrado do Hub", path.read_text("utf-8"))
            self.assertNotIn("conteudo atualizado do Hub", path.read_text("utf-8"))
            reopened = Memoria(path)
            reopened.inicializar()
            reopened.unlock(key)
            state = reopened.hub_snapshot()
            self.assertEqual(state["tasks"][0]["status"], "concluida")
            self.assertEqual(state["notes"][0]["id"], note["id"])
            self.assertEqual(state["notes"][0]["conteudo"], "conteudo atualizado do Hub")


class CatalogTests(unittest.TestCase):
    def test_no_unrestricted_tools_are_exposed(self):
        names = {schema["function"]["name"] for schema in ESQUEMAS}
        self.assertFalse(names & {"executar_powershell", "executar_python", "instalar_pacote"})

    def test_every_exposed_tool_has_implementation_or_is_memory(self):
        names = {schema["function"]["name"] for schema in ESQUEMAS}
        self.assertFalse(names - set(FUNCOES) - {"buscar_memoria"})

    def test_schemas_are_strict(self):
        for schema in ESQUEMAS:
            params = schema["function"]["parameters"]
            self.assertIs(params.get("additionalProperties"), False)


class ConfigTests(unittest.TestCase):
    def test_server_rejects_non_loopback(self):
        with self.assertRaises(ValueError):
            Config(servidor={"host": "0.0.0.0", "porta": 7777})

    def test_name_is_condor_in_project(self):
        self.assertEqual("Condor".lower(), "condor")

    def test_authenticated_owner_profile_is_fixed_and_operational(self):
        config = Config()
        self.assertEqual(config.seguranca.perfil, "admin")
        self.assertFalse(config.seguranca.simulacao)

    def test_local_connector_is_loopback_only_and_has_priority(self):
        with self.assertRaises(ValueError):
            Config(cerebro={"endpoint_local": "https://example.com/v1"})
        config = Config(cerebro={"modelo_local": "condor-local-model"})
        brain = Cerebro(config, None, None, None)
        self.assertEqual(brain.provedor, "local")
        self.assertEqual(brain.modelo_ativo, "condor-local-model")

    def test_private_memory_sharing_is_off_by_default(self):
        config = Config()
        self.assertFalse(config.cerebro.compartilhar_memoria_com_conector)
        self.assertFalse(config.cerebro.aprendizado_automatico_por_conector)

    def test_voice_and_vision_are_local_by_default(self):
        config = Config()
        self.assertEqual(config.voz.modelo_stt, "faster-whisper-small")
        self.assertEqual(config.voz.modelo_tts, "pt_BR-faber-medium")
        self.assertEqual(config.cerebro.modelo_visao_local, "qwen3-vl:2b")

    def test_config_honors_runtime_condor_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("CONDOR_HOME")
            os.environ["CONDOR_HOME"] = tmp
            try:
                salvar_config(Config(cerebro={"modelo_local": "isolated-model"}))
                text = (Path(tmp) / "config.yaml").read_text("utf-8")
                self.assertIn("isolated-model", text)
            finally:
                if previous is None:
                    os.environ.pop("CONDOR_HOME", None)
                else:
                    os.environ["CONDOR_HOME"] = previous


class InterfaceBoundaryTests(unittest.TestCase):
    def test_desktop_app_targets_operational_ui_not_hub(self):
        launcher = (ROOT / "condor_app.pyw").read_text("utf-8")
        window = (ROOT / "condor_window.pyw").read_text("utf-8")
        session = (ROOT / "condor" / "session.py").read_text("utf-8")
        for source in (launcher, window, session):
            self.assertIn("/ui/index.html", source)
        self.assertNotIn("/hub/index.html", launcher)
        self.assertNotIn("/hub/index.html", window)

    def test_hub_condor_is_assistant_without_embedded_operational_ui(self):
        component = ROOT.parent.parent / "ARTX Hub" / "src" / "components" / "CondorWorkspace.tsx"
        if not component.exists():
            self.skipTest("ARTX Hub nao esta neste checkout")
        source = component.read_text("utf-8")
        self.assertIn("Fale. O Condor organiza.", source)
        self.assertIn("Ativo no Hub", source)
        self.assertNotIn("Demonstração limitada", source)
        self.assertNotIn("<iframe", source)
        self.assertNotIn("/api/hub/condor-x/", source)

    def test_condor_x_keeps_realistic_human_reference_and_c_mark(self):
        source = (ROOT / "condor" / "ui" / "scripts" / "condor-x.js").read_text("utf-8")
        interface = (ROOT / "condor" / "ui" / "index.html").read_text("utf-8")
        projects = (ROOT / "condor" / "ui" / "scripts" / "projects.js").read_text("utf-8")
        vendor = ROOT / "condor" / "ui" / "vendor"
        self.assertTrue((vendor / "three.module.min.js").is_file())
        self.assertTrue((vendor / "three.core.min.js").is_file())
        self.assertIn("three.core.min.js", (vendor / "three.module.min.js").read_text("utf-8"))
        self.assertIn("const exactScale = 1.8 / naturalHeight", source)
        self.assertIn("Assinatura C", source)
        self.assertIn("const cArc", source)
        self.assertIn("const upperLid", source)
        self.assertIn("Polegar e quatro dedos", source)
        self.assertIn("joelhos naturais e pés completos", source)
        self.assertIn("Anatomia técnica de alta fidelidade", interface)
        self.assertIn("Núcleo C", interface)
        self.assertIn('data-screen="projetos">Projetos</button>', interface)
        self.assertIn('id="projectsCatalog"', interface)
        self.assertIn('data-project-open="condor-x"', interface)
        self.assertIn('id="projectDetail" hidden', interface)
        self.assertIn("ABRIR PROJETO", interface)
        self.assertIn("function abrirProjeto", projects)
        self.assertIn("function voltarAoCatalogo", projects)
        self.assertIn("condor-x-visibility", projects)
        self.assertNotIn("Estado operacional", interface)
        self.assertNotIn("Nível de autonomia", interface)
        self.assertNotIn("Controle local", interface)
        self.assertNotIn("addArmor", source)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
