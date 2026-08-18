"""Testes locais do Condor 2.0. Nao usam API, microfone, tela nem rede."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from condor.brain.tools import ESQUEMAS, FUNCOES
from condor.brain.client import Cerebro
from condor.actions import executor
from condor.actions.guard import Guarda
from condor.config import Config, salvar_config
from condor.core import AIGateway, ContextEngine, EventBus, ProjectEngine
from condor.development import human_model_contract
from condor.devices import ActionSafetyLayer, CameraBridge, DeviceBridge
from condor.memory.db import Memoria
from condor.mobile import MobileAccess, MobileViewer, private_client, private_host
from condor.paths import resolver_alvo, state_path
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


class RegressaoSegurancaTests(unittest.TestCase):
    """Falhas encontradas na auditoria de 2026-08. Nao deixar voltar."""

    def _politica(self):
        raizes = [Path.home() / "Documents", ROOT]
        return PolicyEngine(AutonomyProfile.ADMIN, allowed_roots=raizes)

    def test_variavel_de_ambiente_nao_fura_a_trava_de_pastas(self):
        """A politica expandia %USERPROFILE% diferente do executor e liberava."""
        policy = self._politica()
        for alvo in (
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\x.bat",
            r"%USERPROFILE%\.ssh\authorized_keys",
            r"%USERPROFILE%\.condor\security\vault.json",
            r"%SYSTEMROOT%\System32\drivers\etc\hosts",
        ):
            with self.subTest(alvo=alvo):
                decisao = policy.decide("escrever_arquivo", {"caminho": alvo, "conteudo": "x"})
                self.assertFalse(decisao.allowed)
                self.assertEqual(decisao.risk, RiskLevel.BLOCKED)

    def test_politica_e_executor_resolvem_o_mesmo_destino(self):
        for bruto in (r"%APPDATA%\x", "~/Documents/y.txt", "condor/config.py"):
            with self.subTest(bruto=bruto):
                self.assertEqual(resolver_alvo(bruto), executor._caminho(bruto))

    def test_pasta_permitida_continua_liberada(self):
        decisao = self._politica().decide(
            "escrever_arquivo",
            {"caminho": str(Path.home() / "Documents" / "ok.txt"), "conteudo": "x"},
        )
        self.assertTrue(decisao.allowed)

    def test_sessao_do_dono_nao_libera_as_destrutivas(self):
        """O atalho da sessao autenticada anulava toda a camada de aprovacao."""
        guarda = Guarda(Config())
        guarda.unlock_owner_session()
        for ferramenta in ("escrever_arquivo", "deletar", "mover", "baixar", "fechar_app"):
            with self.subTest(ferramenta=ferramenta):
                decisao = guarda.avaliar(ferramenta, {"caminho": str(ROOT / "a.txt")})
                liberado = asyncio.run(guarda.autorizar(decisao, ferramenta, ferramenta))
                self.assertFalse(liberado, "deveria exigir confirmacao do dono")

    def test_sessao_do_dono_nao_atrapalha_o_uso_normal(self):
        guarda = Guarda(Config())
        guarda.unlock_owner_session()
        for ferramenta in ("screenshot", "clicar", "listar_pasta", "ler_arquivo"):
            with self.subTest(ferramenta=ferramenta):
                decisao = guarda.avaliar(ferramenta, {"caminho": str(ROOT / "a.txt")})
                self.assertTrue(asyncio.run(guarda.autorizar(decisao, ferramenta, ferramenta)))

    def test_desbloqueio_preserva_perfil_e_simulacao_escolhidos(self):
        """unlock_owner_session gravava admin/simulacao=False no config.yaml."""
        config = Config()
        config.seguranca.perfil = "observer"
        config.seguranca.simulacao = True
        Guarda(config).unlock_owner_session()
        self.assertEqual(config.seguranca.perfil, "observer")
        self.assertTrue(config.seguranca.simulacao)

    def test_teclado_nao_abre_lancador_de_comandos(self):
        for combo in ("win+r", "windows+r", "win", "win+x", "ctrl+shift+esc"):
            with self.subTest(combo=combo):
                self.assertFalse(executor.atalho(combo)["ok"])

    def test_enderecos_internos_sao_recusados(self):
        for interno in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",
                        "::ffff:127.0.0.1", "0.0.0.0", "::1"):
            with self.subTest(ip=interno):
                with self.assertRaises(ValueError):
                    executor._garantir_ip_publico(interno)
        for publico in ("8.8.8.8", "1.1.1.1"):
            with self.subTest(ip=publico):
                executor._garantir_ip_publico(publico)

    def test_auditoria_detecta_log_reconstruido_do_zero(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            cofre = CondorVault(base / "vault.json")
            cofre.initialize(PASS)
            identidade = DeviceIdentity(cofre)
            identidade.ensure()
            log = base / "actions.jsonl"

            verdadeiro = IntegrityAudit(log, identidade)
            for indice in range(4):
                verdadeiro.append({"tool": "teste", "n": indice})
            self.assertEqual(verdadeiro.verify(), (True, 4))

            # Atacante sem a chave privada refaz uma cadeia coerente.
            log.unlink()
            falso = IntegrityAudit(log, None)
            for indice in range(4):
                falso.append({"tool": "inocente", "n": indice})
            self.assertFalse(IntegrityAudit(log, identidade).verify()[0])

    def test_auditoria_detecta_truncamento(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            cofre = CondorVault(base / "vault.json")
            cofre.initialize(PASS)
            identidade = DeviceIdentity(cofre)
            identidade.ensure()
            log = base / "actions.jsonl"
            auditoria = IntegrityAudit(log, identidade)
            for indice in range(4):
                auditoria.append({"tool": "teste", "n": indice})
            log.write_text("", encoding="utf-8")
            self.assertFalse(IntegrityAudit(log, identidade).verify()[0])

    def test_codigo_movel_e_de_uso_unico(self):
        acesso = MobileAccess(7778)
        primeiro = acesso.code
        token, status = acesso.pair("192.168.1.50", primeiro)
        self.assertEqual(status, 200)
        self.assertTrue(token)
        self.assertNotEqual(acesso.code, primeiro)
        self.assertEqual(acesso.pair("192.168.1.51", primeiro)[1], 403)

    def test_cofre_sobrevive_a_muitas_gravacoes(self):
        """set() relia o salt do disco e podia inutilizar o cofre."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "vault.json"
            cofre = CondorVault(caminho)
            cofre.initialize(PASS, {"A": "1"})
            for indice in range(25):
                cofre.set(f"k{indice}", indice)
            cofre.lock()
            reaberto = CondorVault(caminho)
            reaberto.unlock(PASS)
            self.assertEqual(reaberto.get("k24"), 24)
            self.assertEqual(reaberto.get("A"), "1")


class FluidezTests(unittest.TestCase):
    """Gargalos que travavam a interface. Medidos, nao estimados."""

    def test_leitura_da_memoria_nao_reescreve_o_snapshot(self):
        """Toda consulta re-cifrava e dava fsync no banco inteiro."""
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "m.enc"
            memoria = Memoria(alvo)
            memoria.inicializar()
            memoria.unlock(os.urandom(32))
            for indice in range(40):
                memoria.salvar_fato("t", f"c{indice}", "valor " * 20)

            antes = alvo.stat().st_mtime_ns
            for _ in range(5):
                memoria.estatisticas()
                memoria.custo_hoje()
                memoria.fatos_recentes(20)
                memoria.acoes_recentes(20)
                memoria.hub_snapshot()
            self.assertEqual(alvo.stat().st_mtime_ns, antes,
                             "leitura nao pode reescrever o snapshot cifrado")

            memoria.salvar_fato("t", "novo", "x")
            self.assertNotEqual(alvo.stat().st_mtime_ns, antes,
                                "escrita precisa persistir na hora")

    def test_escrita_continua_duravel_apos_lock(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "m.enc"
            chave = os.urandom(32)
            memoria = Memoria(alvo)
            memoria.inicializar()
            memoria.unlock(chave)
            memoria.salvar_fato("t", "sobrevive", "conteudo")
            memoria.lock()

            outra = Memoria(alvo)
            outra.unlock(chave)
            self.assertTrue(
                any(f["chave"] == "sobrevive" for f in outra.fatos_recentes(50))
            )

    def test_info_sistema_usa_cache(self):
        """psutil varre processos por ~1,6 s; sem cache cada consulta pagava isso."""
        executor._CACHE_SISTEMA.clear()
        primeira = time.perf_counter()
        executor.info_sistema()
        custo_frio = time.perf_counter() - primeira

        segunda = time.perf_counter()
        for _ in range(5):
            executor.info_sistema()
        custo_quente = (time.perf_counter() - segunda) / 5
        self.assertLess(custo_quente, max(custo_frio / 10, 0.005))

    def test_integridade_recacheia_quando_o_codigo_muda(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta) / "raiz"
            (raiz / "condor").mkdir(parents=True)
            fonte = raiz / "condor" / "core.py"
            fonte.write_text("NAME = 'Condor'\n", encoding="utf-8")
            cofre = CondorVault(Path(pasta) / "vault.json")
            cofre.initialize(PASS, {})
            identidade = DeviceIdentity(cofre)
            identidade.ensure()
            check = CodeIntegrity(Path(pasta) / "manifest.json", identidade, raiz)
            check.refresh()

            self.assertTrue(check.verify()[0])
            self.assertTrue(check.verify()[0])          # agora vem da cache
            fonte.write_text("NAME = 'adulterado'\n", encoding="utf-8")
            self.assertFalse(check.verify()[0],
                             "cache nao pode esconder alteracao de codigo")

    def test_auditoria_recacheia_quando_o_log_muda(self):
        with tempfile.TemporaryDirectory() as pasta:
            log = Path(pasta) / "actions.jsonl"
            auditoria = IntegrityAudit(log)
            auditoria.append({"tool": "teste"})
            self.assertTrue(auditoria.verify()[0])
            self.assertTrue(auditoria.verify()[0])      # cache
            log.write_text('{"adulterado": true}\n', encoding="utf-8")
            self.assertFalse(IntegrityAudit(log).verify()[0])


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

    def test_mobile_view_accepts_only_private_network_and_dedicated_code(self):
        self.assertTrue(private_client("127.0.0.1"))
        self.assertTrue(private_client("192.168.1.25"))
        self.assertTrue(private_client("10.12.0.8"))
        self.assertFalse(private_client("8.8.8.8"))
        self.assertTrue(private_host("192.168.1.10:7778"))
        self.assertFalse(private_host("evil.example:7778"))

        access = MobileAccess(7778)
        access.code = "12345678"
        self.assertEqual(access.pair("192.168.1.20", "00000000"), (None, 403))
        token, status = access.pair("192.168.1.20", "12345678")
        self.assertEqual(status, 200)
        self.assertTrue(access.valid(token))
        self.assertFalse(access.valid("wrong"))

    def test_mobile_view_is_read_only_paired_and_sanitized(self):
        from fastapi.testclient import TestClient

        snapshot = {
            "nome": "Condor", "estado": "dormindo", "acordado": False,
            "cerebro_pronto": True, "modelo": "local", "provedor": "local",
            "voz_local_pronta": True, "integridade_ok": True,
            "modo": "somente leitura", "projetos": [],
        }
        viewer = MobileViewer(7778, lambda: snapshot)
        viewer.access.code = "12345678"
        client = TestClient(
            viewer.app,
            base_url="http://192.168.1.10:7778",
            client=("192.168.1.25", 50000),
        )
        self.assertEqual(client.get("/api/status").status_code, 401)
        paired = client.post("/api/pair", json={"code": "12345678"})
        self.assertEqual(paired.status_code, 200, paired.text)
        self.assertIn("HttpOnly", paired.headers["set-cookie"])
        status = client.get("/api/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json(), snapshot)
        self.assertIn("frame-ancestors 'none'", status.headers["content-security-policy"])
        self.assertEqual(status.headers["x-frame-options"], "DENY")
        self.assertEqual(client.post("/api/status").status_code, 405)

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
                # Cabecalho e forjavel por qualquer processo local: sem o segredo
                # de boot, que exige LER um arquivo do perfil do dono, a sessao
                # nao sai.
                self.assertEqual(
                    client.post(
                        "/api/session", headers={
                            "Origin": "http://127.0.0.1:7777",
                            "X-Condor-Client": "desktop-ui",
                        }
                    ).status_code,
                    403,
                )
                segredo = state_path("security", "ui-token").read_text(
                    encoding="utf-8").strip()
                self.assertTrue(segredo)
                self.assertEqual(
                    client.post(
                        "/api/session", headers={
                            "Origin": "http://127.0.0.1:7777",
                            "X-Condor-Client": "desktop-ui",
                            "X-Condor-Token": segredo + "x",
                        }
                    ).status_code,
                    403,
                )
                response = client.post(
                    "/api/session", headers={
                        "Origin": "http://127.0.0.1:7777",
                        "X-Condor-Client": "desktop-ui",
                        "X-Condor-Token": segredo,
                    }
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn("SameSite=strict", response.headers["set-cookie"])
                # O Hub em /hub renova pelo cookie ja estabelecido, sem o arquivo.
                self.assertEqual(
                    client.post(
                        "/api/session", headers={
                            "Origin": "http://127.0.0.1:7777",
                            "X-Condor-Client": "hub-local",
                        }
                    ).status_code,
                    200,
                )
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
            region_item = memory.condor_x_create_region_item(
                "left-forearm", "componente", "Registro privado", "detalhe anatomico cifrado"
            )
            self.assertTrue(memory.condor_x_update_region_item(
                region_item["id"], "Registro privado", "detalhe atualizado", "planejado"
            ))
            memory.lock()
            self.assertNotIn("conteudo cifrado do Hub", path.read_text("utf-8"))
            self.assertNotIn("conteudo atualizado do Hub", path.read_text("utf-8"))
            self.assertNotIn("detalhe anatomico cifrado", path.read_text("utf-8"))
            self.assertNotIn("detalhe atualizado", path.read_text("utf-8"))
            reopened = Memoria(path)
            reopened.inicializar()
            reopened.unlock(key)
            state = reopened.hub_snapshot()
            self.assertEqual(state["tasks"][0]["status"], "concluida")
            self.assertEqual(state["notes"][0]["id"], note["id"])
            self.assertEqual(state["notes"][0]["conteudo"], "conteudo atualizado do Hub")
            stored_region = reopened.condor_x_region_items("left-forearm")
            self.assertEqual(stored_region[0]["id"], region_item["id"])
            self.assertEqual(stored_region[0]["status"], "planejado")


class CondorCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_camera_bridge_keeps_endpoint_private_and_emits_local_alert(self):
        class Vision:
            async def analisar(self, image_b64, pedido):
                self.received = (image_b64, pedido)
                return '{"person_present":true,"confidence":0.91,"summary":"pessoa"}'

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "camera-memory.enc"
            memory = Memoria(path)
            memory.inicializar()
            memory.unlock(os.urandom(32))
            bus = EventBus(memory)
            received = []
            bus.subscribe("SECURITY_ALERT", lambda event: received.append(event))
            bridge = CameraBridge(memory, bus, Vision())
            camera = await bridge.add_source(
                "Entrada", "rtsp", "rtsp://usuario:senha@192.168.1.20/stream", "Porta"
            )
            self.assertNotIn("endpoint", camera)
            result = await bridge.analyze_frame(camera["id"], "aW1hZ2Vt")
            self.assertTrue(result["person_present"])
            self.assertFalse(result["stored_frame"])
            self.assertEqual(len(received), 1)
            self.assertIn("Confirme a imagem", result["alert"]["summary"])
            memory.lock()
            encrypted = path.read_text("utf-8")
            self.assertNotIn("usuario:senha", encrypted)
            self.assertNotIn("192.168.1.20", encrypted)

    async def test_device_scan_never_executes_serial_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = Memoria(Path(tmp) / "devices.enc")
            memory.inicializar()
            memory.unlock(os.urandom(32))
            bridge = DeviceBridge(memory, EventBus(memory), ActionSafetyLayer())
            result = await bridge.scan()
            self.assertEqual(result["executed_commands"], 0)
            self.assertIsInstance(result["serial_ports"], list)

    async def test_ai_gateway_injects_structured_interface_context(self):
        class Provider:
            provedor = "test"
            modelo_ativo = "test-model"
            pronto = True

            async def responder(self, historico, **kwargs):
                self.historico = historico
                self.kwargs = kwargs
                return "ok"

        provider = Provider()
        context = ContextEngine()
        context.update(project_id="condor-x", region_id="right-forearm", mode="development")
        gateway = AIGateway(provider, context, EventBus())
        result = await gateway.responder([{"role": "user", "content": "Aumenta isso"}])
        self.assertEqual(result, "ok")
        reference = provider.kwargs["memoria_relevante"]
        self.assertIn("ESTADO ATUAL DA INTERFACE", reference)
        self.assertIn('"region_id":"right-forearm"', reference)
        self.assertEqual(context.snapshot()["recent_intent"], "Aumenta isso")

    async def test_project_draft_versions_and_explicit_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "core-memory.enc"
            memory = Memoria(path)
            memory.inicializar()
            memory.unlock(os.urandom(32))
            context = ContextEngine()
            events = EventBus(memory)
            projects = ProjectEngine(memory, context, events)

            opened = await projects.open("condor-x")
            self.assertEqual(opened["context"]["project_id"], "condor-x")
            draft = await projects.create_draft("condor-x", "right-forearm", {
                "name": "Carcaça externa", "type": "component", "notes": "rascunho isolado",
            })
            self.assertFalse(draft["integrated"])
            self.assertEqual(draft["status"], "draft")
            version = await projects.create_version(draft["id"], {
                "snapshot": {"name": "Carcaça externa", "clearance": "undefined"}
            })
            self.assertEqual(version["label"], "V2")
            integrated = await projects.integrate(draft["id"])
            self.assertTrue(integrated["integrated"])
            self.assertEqual(integrated["status"], "integrated")
            self.assertIn("MODEL_UPDATED", {item["type"] for item in memory.eventos_recentes()})
            memory.lock()
            self.assertNotIn("Carcaça externa", path.read_text("utf-8"))

    async def test_event_bus_context_and_physical_safety_are_independent(self):
        context = ContextEngine()
        context.update(project_id="condor-x", region_id="left-hand", mode="development")
        self.assertEqual(context.for_ai()["region_id"], "left-hand")
        bus = EventBus()
        received = []
        bus.subscribe("PART_SELECTED", lambda event: received.append(event))
        await bus.publish("PART_SELECTED", {"region": "left-hand"})
        self.assertEqual(received[0]["payload"]["region"], "left-hand")
        decision = ActionSafetyLayer().evaluate({"risk_level": 4, "command": "move actuator"})
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)

    def test_human_model_has_layers_joints_and_individual_fingers(self):
        model = human_model_contract()
        self.assertEqual(model["default_layer"], "silhouette")
        self.assertEqual(len(model["layers"]), 6)
        fingers = model["hands"]["right"]["digits"]
        self.assertEqual([finger["id"] for finger in fingers], ["thumb", "index", "middle", "ring", "little"])
        self.assertEqual(len(fingers[1]["bones"]), 3)
        self.assertIn("wrist", model["joint_movements"])


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

    def test_mobile_view_has_a_separate_port_and_core_stays_loopback(self):
        config = Config()
        self.assertEqual(config.servidor.host, "127.0.0.1")
        self.assertEqual(config.servidor.porta, 7777)
        self.assertTrue(config.visualizacao_movel.ativa)
        self.assertEqual(config.visualizacao_movel.porta, 7778)

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
    def test_condor_universal_logo_is_used_by_app_and_shortcuts(self):
        assets = ROOT / "condor" / "ui" / "assets"
        interface = (ROOT / "condor" / "ui" / "index.html").read_text("utf-8")
        window = (ROOT / "condor_window.pyw").read_text("utf-8")
        windows_identity = (ROOT / "condor" / "windows_identity.py").read_text("utf-8")
        windows_shortcut = (ROOT / "scripts" / "install_app_shortcut.ps1").read_text("utf-8")
        linux_shortcut = (ROOT / "scripts" / "install_app_shortcut.sh").read_text("utf-8")
        native_launcher = (ROOT / "windows" / "CondorLauncher.cs").read_text("utf-8")
        shortcut_identity = (ROOT / "windows" / "ShortcutIdentity.cs").read_text("utf-8")

        self.assertTrue((assets / "condor-logo.png").is_file())
        self.assertTrue((assets / "condor-logo.ico").is_file())
        self.assertIn('href="assets/condor-logo.png"', interface)
        self.assertIn("condor-logo.ico", window)
        self.assertIn("condor-logo.png", window)
        self.assertIn("prepare_process", window)
        self.assertIn("SHGetPropertyStoreForWindow", windows_identity)
        self.assertIn("condor-logo.ico", windows_identity)
        self.assertIn("ARTX.Condor.Local", windows_identity)
        self.assertIn('options["icon"]', window)
        self.assertIn("condor-logo.ico", windows_shortcut)
        self.assertNotIn('$Shortcut.IconLocation = "$Pythonw,0"', windows_shortcut)
        self.assertIn("Condor.exe", windows_shortcut)
        self.assertIn("ARTX.Condor.Local", windows_shortcut)
        self.assertIn("SetCurrentProcessExplicitAppUserModelID", native_launcher)
        self.assertIn("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3", shortcut_identity)
        self.assertIn("ARTX.Condor.Local", native_launcher)
        self.assertTrue((ROOT / "Condor.exe").is_file())
        self.assertIn("condor-logo.png", linux_shortcut)
        self.assertIn("Icon=%s", linux_shortcut)

    def test_mobile_view_is_separate_from_full_condor_control(self):
        mobile = (ROOT / "condor" / "mobile" / "index.html").read_text("utf-8")
        mobile_script = (ROOT / "condor" / "mobile" / "mobile.js").read_text("utf-8")
        desktop = (ROOT / "condor" / "ui" / "index.html").read_text("utf-8")
        desktop_script = (ROOT / "condor" / "ui" / "scripts" / "mobile-access.js").read_text("utf-8")
        server = (ROOT / "condor" / "server.py").read_text("utf-8")
        packaging = (ROOT / "pyproject.toml").read_text("utf-8")

        self.assertIn("SOMENTE LEITURA", mobile)
        self.assertIn("/api/pair", mobile_script)
        self.assertIn("/api/status", mobile_script)
        self.assertNotIn("/api/memoria", mobile_script)
        self.assertNotIn("/api/seguranca", mobile_script)
        self.assertNotIn('id="mobileAccessBtn"', desktop)
        self.assertIn("/api/mobile/access", desktop_script)
        self.assertIn('host="0.0.0.0"', server)
        self.assertIn("config.visualizacao_movel.porta", server)
        self.assertIn('"mobile/**/*"', packaging)

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

    def test_condor_x_keeps_human_reference_without_unverified_specs(self):
        source = (ROOT / "condor" / "ui" / "scripts" / "condor-x.js").read_text("utf-8")
        interface = (ROOT / "condor" / "ui" / "index.html").read_text("utf-8")
        projects = (ROOT / "condor" / "ui" / "scripts" / "projects.js").read_text("utf-8")
        security = (ROOT / "condor" / "ui" / "scripts" / "security.js").read_text("utf-8")
        vendor = ROOT / "condor" / "ui" / "vendor"
        self.assertTrue((vendor / "three.module.min.js").is_file())
        self.assertTrue((vendor / "three.core.min.js").is_file())
        self.assertIn("three.core.min.js", (vendor / "three.module.min.js").read_text("utf-8"))
        self.assertIn('class="cx-human-map"', source)
        self.assertIn('id="cxHeadShape"', source)
        self.assertIn('id="cxNeckShape"', source)
        self.assertIn('id="cxChestShape"', source)
        self.assertIn('id="cxAbdomenShape"', source)
        self.assertIn('id="cxLeftShoulderShape"', source)
        self.assertIn('id="cxLeftForearmShape"', source)
        self.assertIn('id="cxLeftHandShape"', source)
        self.assertIn('id="cxLeftThighShape"', source)
        self.assertIn('id="cxLeftKneeShape"', source)
        self.assertIn('id="cxLeftShinShape"', source)
        self.assertIn('data-zone="power"', source)
        self.assertIn("Silhueta humana frontal dividida em regiões", source)
        self.assertIn("function openRegion", source)
        self.assertIn("SALVAR NO COFRE", source)
        self.assertIn("/api/condor-x/regions/", source)
        self.assertNotIn("SphereGeometry", source)
        self.assertNotIn("CapsuleGeometry", source)
        self.assertIn("Base visual para planejamento futuro", interface)
        self.assertIn("ZONAS DE PLANEJAMENTO", interface)
        self.assertIn("Nenhuma armadura está em desenvolvimento", interface)
        self.assertNotIn("1,80 m", interface)
        self.assertNotIn("85 kg", interface)
        self.assertNotIn("PARAR CONDOR", security)
        self.assertNotIn("setPreviewMode", security)
        self.assertNotIn("VER O APP BLOQUEADO", security)
        self.assertNotIn("VER A INTERFACE PRIMEIRO", security)
        self.assertNotIn("PRIVATE SYSTEM", security)
        self.assertNotIn("OWNER ACCESS NODE", security)
        self.assertNotIn("LOCAL VAULT // ENCRYPTED", security)
        self.assertNotIn("A interface permanece isolada", security)
        self.assertIn("frame.setAttribute('inert', '')", security)
        self.assertIn("AUTORIZAR ACESSO", security)
        self.assertIn('data-screen="projetos">Projetos</button>', interface)
        self.assertIn('id="projectsCatalog"', interface)
        self.assertIn('data-project-open="condor-x"', interface)
        self.assertIn('id="projectDetail" hidden', interface)
        self.assertIn("ABRIR AMBIENTE", interface)
        self.assertIn("function abrirProjeto", projects)
        self.assertIn("function voltarAoCatalogo", projects)
        self.assertIn("condor-x-visibility", projects)
        self.assertNotIn("Estado operacional", interface)
        self.assertNotIn("Nível de autonomia", interface)
        self.assertNotIn("Controle local", interface)
        self.assertNotIn("addArmor", source)
        self.assertNotIn('data-screen="desenvolvimento"', interface)
        self.assertNotIn('data-screen="corpo"', interface)
        self.assertNotIn('data-screen="dispositivos"', interface)
        self.assertIn('data-screen="programacao">Programação</button>', interface)
        self.assertIn('id="deviceScan"', interface)
        self.assertIn('id="cameraForm"', interface)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
