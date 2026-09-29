"""Aba Programação: busca sob demanda, alvo escolhido, chat embutido e envio."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Nenhum teste escreve em ~/.condor.
_TEST_STATE = tempfile.TemporaryDirectory(prefix="condor-programacao-")
os.environ["CONDOR_HOME"] = _TEST_STATE.name

from condor.brain.persona import montar_prompt
from condor.config import Config
from condor.core.orchestrator import CondorOrchestrator
from condor.development import ArduinoToolchain
from condor.memory.db import Memoria
from condor.memory.extractor import Extrator
from condor.memory.recall import Recall
from condor.session import Sessao, instrucao_programacao
import condor.server as server

UI = ROOT / "condor" / "ui"


def _html() -> str:
    return (UI / "index.html").read_text("utf-8")


def _core_ui() -> str:
    return (UI / "scripts" / "core-ui.js").read_text("utf-8")


class ProgramacaoInterfaceTests(unittest.TestCase):
    def test_inventory_card_and_polling_are_gone(self):
        html = _html()
        core = _core_ui()
        self.assertNotIn("DISPOSITIVOS PRESENTES", html)
        self.assertNotIn("O INVENTÁRIO CONTINUA ATIVO", html)
        self.assertNotIn("CAPACIDADES DETECTÁVEIS", html)
        self.assertNotIn("ROTEAMENTO POR CAPACIDADE", html)
        self.assertNotIn("SOMENTE DETECÇÃO", core)
        self.assertIn("PESQUISAR DISPOSITIVOS", html)
        # Só o contador da senha usa intervalo; nada de varrer dispositivos em laço.
        self.assertEqual(core.count("setInterval("), 1)
        self.assertIn("permissionCooldownTimer = setInterval(tick, 1000)", core)
        self.assertNotIn("deviceScanTimer", core)
        atualizar = re.search(r"function atualizar\(screen\) \{(.*)", core).group(1)
        self.assertNotIn("scanDevices", atualizar.split("if (screen === 'laboratorio')")[0])

    def test_required_ids_exist(self):
        html = _html()
        for element_id in ("deviceScan", "connectedDevice", "programChat", "programChatLog",
                           "programChatInput", "programChatMic", "programOrb", "programVerify",
                           "programRun", "programConfirm", "programBuffer"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('id="deviceCommandCard" hidden', html)

    def test_core_ui_uses_chosen_target_and_inline_confirmation(self):
        core = _core_ui()
        self.assertIn("/api/devices/connect", core)
        self.assertIn("/api/devices/scan", core)
        self.assertIn("/api/programming/arduino/run", core)
        self.assertIn("/api/programming/arduino/verify", core)
        self.assertIn("confirmed: true", core)
        self.assertNotIn("/api/programming/auto-run", core)
        self.assertNotIn("window.confirm", core)
        self.assertIn("confirmInline('programConfirm'", core)
        self.assertIn("error.status === 403", core)
        self.assertIn("/api/voice/transcribe?dispatch=false", core)
        self.assertIn("contexto: 'programacao'", core)
        self.assertIn("CODE_BUFFER_UPDATED", core)
        self.assertIn("onCodeBufferUpdated", core)

    def test_main_chat_ignores_programming_turns(self):
        conversation = (UI / "scripts" / "conversation.js").read_text("utf-8")
        self.assertIn("m.contexto === 'programacao'", conversation)
        self.assertIn("if (deOutroPainel(m)) return;", conversation)

    @unittest.skipUnless(shutil.which("node"), "node ausente")
    def test_sketch_extraction_helper(self):
        script = r"""
const vm = require('vm'); const fs = require('fs');
const api = vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8') + ';CondorCoreUI', {});
const fence = '```';
const cases = [
  'Pisca o LED.\n' + fence + 'cpp\nvoid setup(){}\nvoid loop(){}\n' + fence + '\nPronto.',
  fence + 'cpp\nint a;\n' + fence + ' depois ' + fence + 'ino\nvoid setup(){}\nvoid loop(){}\n' + fence,
  fence + 'python\nprint(1)\n' + fence + '\n' + fence + '\nvoid setup(){}\nvoid loop(){}\n' + fence,
  'sem código',
];
process.stdout.write(JSON.stringify(cases.map(api.extractSketch)));
"""
        output = subprocess.run(
            ["node", "-e", script, str(UI / "scripts" / "core-ui.js")],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
        self.assertEqual(json.loads(output), [
            "void setup(){}\nvoid loop(){}\n",
            "void setup(){}\nvoid loop(){}\n",
            "void setup(){}\nvoid loop(){}\n",
            "",
        ])


class ProgramacaoServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_forwards_programming_context_and_target(self):
        calls = []

        class FakeSession:
            async def processar_texto(self, texto, **kwargs):
                calls.append((texto, kwargs))

        class FakeSocket:
            async def send_text(self, _text):
                return None

        await server._tratar({
            "tipo": "texto", "texto": "pisca o led", "contexto": "programacao",
            "alvo": {"fqbn": "arduino:avr:uno", "name": "Arduino Uno", "port": "COM3", "extra": "x" * 50},
        }, FakeSession(), FakeSocket())
        await server._tratar({"tipo": "texto", "texto": "oi"}, FakeSession(), FakeSocket())
        await asyncio.gather(*tuple(server._EM_VOO))
        self.assertEqual(calls[0], ("pisca o led", {
            "contexto": "programacao",
            "alvo": {"name": "Arduino Uno", "port": "COM3", "fqbn": "arduino:avr:uno"},
        }))
        self.assertEqual(calls[1], ("oi", {}))

    def test_verify_endpoint_and_explicit_run_confirmation(self):
        source = (ROOT / "condor" / "server.py").read_text("utf-8")
        self.assertIn('@app.post("/api/programming/arduino/verify")', source)
        run = source.split('@app.post("/api/programming/arduino/run")', 1)[1][:900]
        self.assertIn('payload.get("confirmed")', run)
        self.assertIn('"arduino_upload"', run)
        self.assertIn("status_code=403", run)

    def test_prompt_carries_turn_instruction(self):
        hint = instrucao_programacao({"fqbn": "arduino:avr:nano", "name": "Arduino Nano"})
        self.assertIn("aba Programação", hint)
        self.assertIn("arduino:avr:nano", hint)
        self.assertIn("```cpp", hint)
        self.assertIn("o dono clica Enviar", hint)
        prompt = montar_prompt("Kauã", instrucao_turno=hint)
        self.assertIn("INSTRUÇÃO DESTE TURNO", prompt)
        self.assertIn(hint, prompt)
        self.assertNotIn("INSTRUÇÃO DESTE TURNO", montar_prompt("Kauã"))


class ProgramacaoSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_programming_turn_gets_hint_and_tagged_events(self):
        class Brain:
            pronto = True
            modelo_ativo = "teste"
            provedor = "local"
            ultimas_fontes = []

            def __init__(self):
                self.kwargs = []

            async def responder(self, historico, **kwargs):
                self.kwargs.append(kwargs)
                await kwargs["on_token"]("```cpp\n")
                return "Pisca.\n```cpp\nvoid setup(){}\nvoid loop(){}\n```"

            async def embedding(self, _texto):
                return None

            async def completar(self, *_args, **_kwargs):
                return ""

        class Guard:
            def registrar_pedido_senha(self, fn):
                self.fn = fn

        class Wake:
            ativa = False
            palavra = "Condor"
            motivo_inativa = "teste"

            def silenciar(self):
                return None

            def voltar_a_ouvir(self):
                return None

        class Ears:
            pronto = False

        class Voice:
            pronto = False

        with tempfile.TemporaryDirectory() as tmp:
            memory = Memoria(Path(tmp) / "programacao.enc")
            memory.inicializar()
            memory.unlock(os.urandom(32))
            brain = Brain()
            config = Config(sessao={"abrir_janela_ao_acordar": False, "fechar_janela_ao_dormir": False})
            session = Sessao(config, memory, brain, Recall(memory), Extrator(memory, brain, config),
                             Guard(), Wake(), Ears(), Voice())
            events = []

            async def notify(event):
                events.append(event)

            session.ligar_avisos(notify)
            await session.processar_texto(
                "pisca o led", contexto="programacao",
                alvo={"fqbn": "arduino:avr:uno", "name": "Arduino Uno"},
            )
            await session.processar_texto("e agora?")
            await session.extrator.encerrar()

        self.assertIn("instrucao_turno", brain.kwargs[0])
        self.assertIn("arduino:avr:uno", brain.kwargs[0]["instrucao_turno"])
        self.assertNotIn("instrucao_turno", brain.kwargs[1])
        answers = [event for event in events if event["tipo"].startswith("resposta.")]
        first_turn = answers[:2]
        self.assertEqual([event["tipo"] for event in first_turn], ["resposta.token", "resposta.fim"])
        self.assertTrue(all(event.get("contexto") == "programacao" for event in first_turn))
        self.assertTrue(all("contexto" not in event for event in answers[2:]))
        self.assertTrue(all("contexto" not in event for event in events if event["tipo"] == "estado"))


class BuscarDispositivosTests(unittest.IsolatedAsyncioTestCase):
    def _orchestrator(self):
        class Memory:
            unlocked = True

            def permission_allowed(self, _capability):
                return False  # ai_devices vem desligada por padrão

        class Devices:
            async def scan(self):
                return {
                    "count": 2, "executed_commands": 0,
                    "serial_ports": [{"port": "COM3", "description": "Arduino Uno", "family": "Arduino",
                                      "connectable": True, "baud_rates": [9600, 115200]}],
                }

        return CondorOrchestrator(Memory(), None, None, None, Devices())

    async def test_scan_is_read_only_and_does_not_need_ai_devices(self):
        result = await self._orchestrator().execute("condor_buscar_dispositivos", {})
        self.assertTrue(result["ok"], result["saida"])
        self.assertEqual(json.loads(result["saida"])["serial_ports"][0]["port"], "COM3")

    async def test_connecting_still_requires_permission(self):
        result = await self._orchestrator().execute("condor_conectar_dispositivo", {"port": "COM3"})
        self.assertFalse(result["ok"])
        self.assertIn("ai_devices", result["saida"])


class ArduinoVerifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_compile_only_never_uploads(self):
        toolchain = ArduinoToolchain(Path(sys.executable))
        calls = []

        async def fake_invoke(args, timeout=30):
            calls.append(args[0])
            return {"ok": True, "exit_code": 0, "output": "ok"}

        toolchain._invoke = fake_invoke
        result = await toolchain.compile_only(
            content="void setup(){}\nvoid loop(){}\n", sketch_name="teste.ino", fqbn="arduino:avr:uno",
        )
        self.assertTrue(result["success"])
        self.assertEqual(calls, ["compile"])
        with self.assertRaisesRegex(ValueError, "modelo de placa"):
            await toolchain.compile_only(content="void setup(){}\nvoid loop(){}\n",
                                         sketch_name="x.ino", fqbn="uno")


def tearDownModule():
    _TEST_STATE.cleanup()


if __name__ == "__main__":
    unittest.main()


class EditorCodeInTurnTests(unittest.TestCase):
    """O CONDOR da aba enxerga o código do editor para poder arrumá-lo."""

    def test_hint_carries_current_editor_code(self):
        hint = instrucao_programacao({"name": "Arduino Uno"}, "void setup() {}\nvoid loop() { piscar(); }")
        self.assertIn("piscar();", hint)
        self.assertIn("devolva o sketch inteiro", hint)
        self.assertNotIn("CÓDIGO QUE ESTÁ NO EDITOR", instrucao_programacao({"name": "Arduino Uno"}, ""))

    def test_project_id_is_validated_before_reaching_the_prompt(self):
        from condor.server import _alvo_programacao
        self.assertEqual(_alvo_programacao({"projeto": "condor-x"})["projeto"], "condor-x")
        self.assertNotIn("projeto", _alvo_programacao({"projeto": "../../vault"}))
