"""Câmera amiga: uma foto sob pedido, analisada localmente, nunca guardada."""
import asyncio
import base64
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Nenhum teste escreve em ~/.condor: a raiz temporária vem antes dos imports.
_ESTADO = tempfile.TemporaryDirectory(prefix="condor-camera-tests-")
os.environ.setdefault("CONDOR_HOME", _ESTADO.name)

from condor.brain import tools as ferramentas
from condor.brain.client import _selecionar_esquemas_locais
from condor.core.orchestrator import CondorOrchestrator
from condor.memory.db import Memoria
from condor.security.policy import TOOL_RISK, RiskLevel
from condor.session import Sessao

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
JPEG_B64 = base64.b64encode(JPEG).decode()
PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()


def nomes(texto):
    return {s["function"]["name"] for s in _selecionar_esquemas_locais([{"role": "user", "content": texto}])}


class VisaoFalsa:
    def __init__(self):
        self.chamadas = []

    async def analisar(self, imagem_b64, pedido=""):
        self.chamadas.append((imagem_b64, pedido))
        return "Camiseta azul-marinho lisa, calça jeans clara, fundo com estante."


def orquestrador(memoria):
    return CondorOrchestrator(memoria, None, None, None, None)


class CameraToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "camera-memory.enc"
        self.memoria = Memoria(self.path)
        self.memoria.inicializar()
        self.memoria.unlock(os.urandom(32))

    def tearDown(self):
        self.memoria.lock()
        self._tmp.cleanup()

    def test_tool_is_internal_reviewed_and_labeled(self):
        self.assertIn("condor_olhar_camera", ferramentas.INTERNAS)
        self.assertEqual(TOOL_RISK["condor_olhar_camera"], RiskLevel.REVIEW)
        self.assertEqual(ferramentas.ROTULOS["condor_olhar_camera"], "olhando pela câmera")
        self.assertIn("condor_olhar_camera", {s["function"]["name"] for s in ferramentas.ESQUEMAS})

    async def test_without_permission_asks_in_sistema_and_never_opens_camera(self):
        capturas = []

        async def capturar():
            capturas.append(1)
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "como eu tô?"})
        self.assertFalse(resultado["ok"])
        self.assertIn("Sistema", resultado["saida"])
        self.assertEqual(capturas, [])
        pedidos = self.memoria.pending_permission_requests()
        self.assertEqual([(p["capability"], p["source"]) for p in pedidos], [("camera", "chat_camera")])

    async def test_allowed_returns_text_only_and_stores_nothing(self):
        pedido = self.memoria.request_permission("camera", "teste", "chat_camera")
        self.memoria.resolve_permission_request(pedido["id"], "allow_always")
        fatos_antes = self.memoria.estatisticas()
        visao = VisaoFalsa()

        async def capturar():
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, visao)
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "analisa minha roupa"})
        self.assertTrue(resultado["ok"], resultado)
        self.assertIn("Camiseta azul-marinho", resultado["saida"])
        self.assertNotIn(JPEG_B64, resultado["saida"])
        self.assertNotIn("image_b64", resultado["saida"])
        self.assertNotIn("imagem_b64", resultado)
        # A análise foi local e recebeu o pedido do dono no prompt.
        self.assertEqual(visao.chamadas[0][0], JPEG_B64)
        self.assertIn("analisa minha roupa", visao.chamadas[0][1])
        self.assertEqual(self.memoria.estatisticas(), fatos_antes)

    async def test_one_time_grant_is_consumed_by_a_single_photo(self):
        pedido = self.memoria.request_permission("camera", "teste", "chat_camera")
        self.memoria.resolve_permission_request(pedido["id"], "allow_once")

        async def capturar():
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        self.assertTrue((await orq.execute("condor_olhar_camera", {"pedido": "o que você vê?"}))["ok"])
        self.assertFalse((await orq.execute("condor_olhar_camera", {"pedido": "de novo"}))["ok"])

    async def test_camera_failure_is_reported_without_crashing(self):
        pedido = self.memoria.request_permission("camera", "teste", "chat_camera")
        self.memoria.resolve_permission_request(pedido["id"], "allow_always")

        async def capturar():
            raise RuntimeError("câmera: câmera ocupada")

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "olha isso aqui"})
        self.assertFalse(resultado["ok"])
        self.assertIn("ocupada", resultado["saida"])


def sessao_falsa(eventos, janela=True):
    guarda = types.SimpleNamespace(registrar_pedido_senha=lambda fn: None)
    sessao = Sessao(types.SimpleNamespace(), None, None, None, None, guarda, None, None, None)

    async def avisar(msg):
        eventos.append(msg)

    sessao.ligar_avisos(avisar)
    sessao.ligar_janelas(lambda: janela)
    return sessao


class CameraBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def _pedir_e_responder(self, sessao, eventos, **resposta):
        tarefa = asyncio.create_task(sessao.capturar_camera(timeout=2))
        while not eventos:
            await asyncio.sleep(0)
        self.assertEqual(eventos[0]["tipo"], "camera.capturar")
        sessao.responder_camera(eventos[0]["id"], **resposta)
        return await tarefa

    async def test_round_trip_returns_the_frame_and_clears_pending(self):
        eventos = []
        sessao = sessao_falsa(eventos)
        self.assertEqual(await self._pedir_e_responder(sessao, eventos, image_b64=JPEG_B64), JPEG_B64)
        self.assertFalse(sessao.aguardando_foto)

    async def test_png_is_accepted(self):
        eventos = []
        sessao = sessao_falsa(eventos)
        self.assertEqual(await self._pedir_e_responder(sessao, eventos, image_b64=PNG_B64), PNG_B64)

    async def test_no_window_fails_clearly(self):
        sessao = sessao_falsa([], janela=False)
        with self.assertRaisesRegex(RuntimeError, "janela"):
            await sessao.capturar_camera(timeout=1)

    async def test_timeout_releases_the_request(self):
        sessao = sessao_falsa([])
        with self.assertRaisesRegex(RuntimeError, "tempo"):
            await sessao.capturar_camera(timeout=0.05)
        self.assertFalse(sessao.aguardando_foto)

    async def test_unknown_id_is_ignored(self):
        eventos = []
        sessao = sessao_falsa(eventos)
        tarefa = asyncio.create_task(sessao.capturar_camera(timeout=2))
        while not eventos:
            await asyncio.sleep(0)
        self.assertFalse(sessao.responder_camera("forjado", image_b64=JPEG_B64))
        self.assertFalse(tarefa.done())
        self.assertTrue(sessao.responder_camera(eventos[0]["id"], image_b64=JPEG_B64))
        self.assertEqual(await tarefa, JPEG_B64)

    async def test_oversize_frame_is_rejected(self):
        eventos = []
        sessao = sessao_falsa(eventos)
        grande = base64.b64encode(b"\xff\xd8\xff" + b"\x00" * (3 * 1024 * 1024)).decode()
        with self.assertRaisesRegex(RuntimeError, "grande"):
            await self._pedir_e_responder(sessao, eventos, image_b64=grande)

    async def test_non_image_frame_is_rejected(self):
        eventos = []
        sessao = sessao_falsa(eventos)
        with self.assertRaisesRegex(RuntimeError, "JPEG ou PNG"):
            await self._pedir_e_responder(sessao, eventos, image_b64=base64.b64encode(b"GIF89a....").decode())

    async def test_window_error_is_forwarded(self):
        eventos = []
        sessao = sessao_falsa(eventos)
        with self.assertRaisesRegex(RuntimeError, "ocupada"):
            await self._pedir_e_responder(sessao, eventos, erro="câmera ocupada")


class CameraRoutingTests(unittest.TestCase):
    def test_camera_phrases_route_to_camera(self):
        for frase in ("Condor, o que você vê?", "analisa minha roupa", "olha isso aqui",
                      "como eu tô?", "como eu estou hoje?", "tô bonito?", "isso combina?",
                      "me vê aí", "liga a câmera e me diz", "curti meu look?"):
            with self.subTest(frase=frase):
                self.assertIn("condor_olhar_camera", nomes(frase))

    def test_screen_phrases_still_route_to_screenshot(self):
        for frase in ("veja a minha tela", "o que você vê na minha tela?", "print da tela"):
            with self.subTest(frase=frase):
                self.assertIn("screenshot", nomes(frase))
                self.assertNotIn("condor_olhar_camera", nomes(frase))

    def test_unrelated_phrases_do_not_offer_camera(self):
        for frase in ("oi, tudo bem?", "me verifica o uso da RAM", "me vende essa ideia"):
            with self.subTest(frase=frase):
                self.assertNotIn("condor_olhar_camera", nomes(frase))


if __name__ == "__main__":
    unittest.main()
