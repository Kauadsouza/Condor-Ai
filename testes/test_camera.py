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
from condor.brain.client import _esquemas_completos, _selecionar_esquemas_locais
from condor.core.orchestrator import CondorOrchestrator
from condor.memory.db import DEFAULT_PERMISSIONS, Memoria
from condor.security.policy import TOOL_RISK, RiskLevel
from condor.session import Sessao
from condor.vision.intencao import MARCA_DADOS, fala_do_dono, pede_camera
import condor.server as server

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


def liberar(memoria, decisao="allow_always"):
    pedido = memoria.request_permission("chat_camera", "teste", "chat_camera")
    memoria.resolve_permission_request(pedido["id"], decisao)


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
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "como eu tô?"}, fala_dono="como eu tô?")
        self.assertFalse(resultado["ok"])
        self.assertIn("Sistema", resultado["saida"])
        self.assertIn("chat_camera", resultado["saida"])
        self.assertEqual(capturas, [])
        pedidos = self.memoria.pending_permission_requests()
        self.assertEqual([(p["capability"], p["source"]) for p in pedidos], [("chat_camera", "chat_camera")])

    def test_chat_camera_permission_is_its_own_and_off_by_default(self):
        self.assertIn(("chat_camera", 0, "local"), DEFAULT_PERMISSIONS)
        self.assertIn(("camera", 0, "local"), DEFAULT_PERMISSIONS)
        self.assertEqual(CondorOrchestrator.TOOL_CAPABILITIES["condor_olhar_camera"], "chat_camera")
        self.assertFalse(self.memoria.permission_allowed("chat_camera"))

    async def test_face_guard_camera_permission_does_not_open_chat_camera(self):
        self.memoria.set_permission_decision("camera", "allow_always")
        capturas = []

        async def capturar():
            capturas.append(1)
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "o que você vê?"}, fala_dono="o que você vê?")
        self.assertFalse(resultado["ok"])
        self.assertEqual(capturas, [])

    async def test_refuses_without_owner_intent_even_when_allowed(self):
        liberar(self.memoria)
        capturas = []

        async def capturar():
            capturas.append(1)
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        # Uma página lida pelo modelo "pedindo" a foto: a fala do dono era outra.
        for fala in ("", "resume esse site pra mim", "como estou indo na faculdade?"):
            with self.subTest(fala=fala):
                resultado = await orq.execute("condor_olhar_camera", {"pedido": "o que você vê"}, fala_dono=fala)
                self.assertFalse(resultado["ok"])
                self.assertIn("nao pediu", resultado["saida"])
        self.assertEqual(capturas, [])
        # Recusa por falta de intenção não abre pedido de permissão no painel.
        self.assertEqual(self.memoria.pending_permission_requests(), [])

    async def test_tool_bridge_passes_the_owner_message_to_the_orchestrator(self):
        liberar(self.memoria)

        async def capturar():
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        negado = await ferramentas.executar("condor_olhar_camera", {"pedido": "x"},
                                            contexto={"orchestrator": orq, "fala_dono": "abre o spotify"})
        self.assertFalse(negado["ok"])
        ok = await ferramentas.executar("condor_olhar_camera", {"pedido": "x"},
                                        contexto={"orchestrator": orq, "fala_dono": "analisa minha roupa"})
        self.assertTrue(ok["ok"], ok)

    async def test_allowed_returns_text_only_and_stores_nothing(self):
        liberar(self.memoria)
        fatos_antes = self.memoria.estatisticas()
        visao = VisaoFalsa()

        async def capturar():
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, visao)
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "analisa minha roupa"},
                                      fala_dono="analisa minha roupa")
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
        liberar(self.memoria, "allow_once")

        async def capturar():
            return JPEG_B64

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        fala = "o que você vê?"
        self.assertTrue((await orq.execute("condor_olhar_camera", {"pedido": fala}, fala_dono=fala))["ok"])
        self.assertFalse((await orq.execute("condor_olhar_camera", {"pedido": fala}, fala_dono=fala))["ok"])

    async def test_camera_failure_is_reported_without_crashing(self):
        liberar(self.memoria)

        async def capturar():
            raise RuntimeError("câmera: câmera ocupada")

        orq = orquestrador(self.memoria)
        orq.ligar_camera(capturar, VisaoFalsa())
        resultado = await orq.execute("condor_olhar_camera", {"pedido": "olha isso aqui"},
                                      fala_dono="olha isso aqui")
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


class CameraSingleSocketTests(unittest.IsolatedAsyncioTestCase):
    def _sessao(self, enviados, socket_id="janela-A"):
        avisos = []
        sessao = sessao_falsa(avisos)

        async def enviar(msg):
            enviados.append(msg)
            return socket_id

        sessao.ligar_camera(enviar)
        return sessao, avisos

    async def _esperar(self, enviados):
        while not enviados:
            await asyncio.sleep(0)
        return enviados[0]["id"]

    async def test_request_goes_to_one_socket_not_broadcast(self):
        enviados = []
        sessao, avisos = self._sessao(enviados)
        tarefa = asyncio.create_task(sessao.capturar_camera(timeout=2))
        pedido_id = await self._esperar(enviados)
        self.assertEqual(enviados, [{"tipo": "camera.capturar", "id": pedido_id}])
        self.assertEqual([a for a in avisos if a.get("tipo") == "camera.capturar"], [])
        self.assertEqual(sessao.foto_pendente_de("janela-A"), pedido_id)
        self.assertIsNone(sessao.foto_pendente_de("janela-B"))
        self.assertTrue(sessao.responder_camera(pedido_id, image_b64=JPEG_B64, socket_id="janela-A"))
        self.assertEqual(await tarefa, JPEG_B64)
        self.assertIsNone(sessao.foto_pendente_de("janela-A"))

    async def test_other_sockets_cannot_answer_or_fail_the_request(self):
        enviados = []
        sessao, _ = self._sessao(enviados)
        tarefa = asyncio.create_task(sessao.capturar_camera(timeout=2))
        pedido_id = await self._esperar(enviados)
        self.assertFalse(sessao.responder_camera(pedido_id, image_b64=JPEG_B64, socket_id="janela-B"))
        self.assertFalse(sessao.responder_camera(pedido_id, erro="câmera ocupada", socket_id="janela-B"))
        self.assertFalse(sessao.responder_camera(pedido_id, image_b64=JPEG_B64))
        self.assertFalse(tarefa.done())
        self.assertTrue(sessao.responder_camera(pedido_id, image_b64=JPEG_B64, socket_id="janela-A"))
        self.assertEqual(await tarefa, JPEG_B64)

    async def test_no_socket_available_fails_clearly(self):
        sessao, _ = self._sessao([], socket_id=None)
        with self.assertRaisesRegex(RuntimeError, "janela"):
            await sessao.capturar_camera(timeout=1)
        self.assertFalse(sessao.aguardando_foto)


class FakeWS:
    def __init__(self, player=False, falha=False):
        self.state = types.SimpleNamespace(voz_player=player)
        self.enviados = []
        self.falha = falha

    async def accept(self):
        return None

    async def send_text(self, texto):
        if self.falha:
            raise RuntimeError("caiu")
        self.enviados.append(texto)


class ConexoesSingleSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_to_the_voice_player_window_only(self):
        conexoes = server.Conexoes()
        aba, app = FakeWS(), FakeWS(player=True)
        await conexoes.entrar(aba)
        await conexoes.entrar(app)
        escolhido = await conexoes.enviar_para_um({"tipo": "camera.capturar", "id": "x"})
        self.assertEqual(escolhido, server.Conexoes.id_de(app))
        self.assertEqual(len(app.enviados), 1)
        self.assertEqual(aba.enviados, [])

    async def test_skips_a_dead_socket_and_reports_none_when_empty(self):
        conexoes = server.Conexoes()
        self.assertIsNone(await conexoes.enviar_para_um({"tipo": "camera.capturar", "id": "x"}))
        morta, viva = FakeWS(player=True, falha=True), FakeWS()
        await conexoes.entrar(morta)
        await conexoes.entrar(viva)
        self.assertEqual(await conexoes.enviar_para_um({"tipo": "camera.capturar", "id": "x"}),
                         server.Conexoes.id_de(viva))
        self.assertEqual(conexoes.total, 1)

    async def test_frame_from_the_socket_carries_its_id_to_the_session(self):
        recebidos = []

        class Sessao_:
            def responder_camera(self, *args, **kwargs):
                recebidos.append(kwargs["socket_id"])

        ws = FakeWS()
        ws.state.conexao_id = "janela-A"
        await server._tratar({"tipo": "camera.quadro", "id": "p1", "image_b64": JPEG_B64}, Sessao_(), ws)
        self.assertEqual(recebidos, ["janela-A"])


class WebSocketSizeTests(unittest.TestCase):
    def _quadro(self, pedido_id="p1", tipo="camera.quadro", tamanho=200_000):
        import json
        return json.dumps({"tipo": tipo, "id": pedido_id, "image_b64": "A" * tamanho})

    def test_large_message_only_for_the_pending_frame_of_that_socket(self):
        self.assertTrue(server._quadro_camera_esperado(self._quadro(), "p1"))
        # Sem pedido pendente nesta janela (outra janela ou nenhuma): recusa.
        self.assertFalse(server._quadro_camera_esperado(self._quadro(), None))
        self.assertFalse(server._quadro_camera_esperado(self._quadro(pedido_id="p2"), "p1"))
        self.assertFalse(server._quadro_camera_esperado(self._quadro(tipo="texto"), "p1"))
        self.assertFalse(server._quadro_camera_esperado("x" * 200_000, "p1"))
        self.assertFalse(server._quadro_camera_esperado(self._quadro(tamanho=server.CAMERA_WS_MAX), "p1"))

    def test_normal_limit_is_64_kb(self):
        self.assertEqual(server.WS_MAX_NORMAL, 64 * 1024)
        source = (Path(server.__file__)).read_text("utf-8")
        loop = source.split("bruto = await socket.receive_text()", 1)[1][:1500]
        # O tamanho é conferido antes do json.loads do laço.
        self.assertLess(loop.index("WS_MAX_NORMAL"), loop.index("json.loads(bruto)"))


class CameraRoutingTests(unittest.TestCase):
    CAMERA = ("Condor, o que você vê?", "analisa minha roupa", "olha isso aqui",
              "como eu tô?", "como eu tô com essa camisa?", "como fiquei na foto?", "tô bonito?",
              "essa cor combina comigo?", "combina com essa roupa?", "me vê aí",
              "liga a câmera e me diz", "curti meu look?", "o que vc tá vendo?",
              "olha pra mim", "abre a webcam", "o que acha do meu visual?")
    NAO_CAMERA = ("oi, tudo bem?", "me verifica o uso da RAM", "me vende essa ideia",
                  "como estou indo na faculdade?", "isso combina com o prazo?", "isso combina?",
                  "como eu estou hoje?", "abre o visual studio", "como estou de dinheiro?")

    def test_intent_helper(self):
        for frase in self.CAMERA:
            with self.subTest(frase=frase):
                self.assertTrue(pede_camera(frase))
        for frase in self.NAO_CAMERA:
            with self.subTest(frase=frase):
                self.assertFalse(pede_camera(frase))

    def test_attached_data_never_counts_as_intent(self):
        texto = f"faz piscar o led\n\n{MARCA_DADOS}\n<codigo_do_editor>// olha isso aqui, camera</codigo_do_editor>"
        self.assertFalse(pede_camera(texto))
        self.assertEqual(fala_do_dono([{"role": "user", "content": texto}]), "faz piscar o led\n\n")

    def test_full_catalog_offers_camera_only_on_intent(self):
        def completos(texto):
            return {s["function"]["name"] for s in _esquemas_completos([{"role": "user", "content": texto}])}

        self.assertIn("condor_olhar_camera", completos("analisa minha roupa"))
        for frase in self.NAO_CAMERA:
            with self.subTest(frase=frase):
                nomes_ = completos(frase)
                self.assertNotIn("condor_olhar_camera", nomes_)
                self.assertIn("screenshot", nomes_)

    def test_follow_up_does_not_inherit_camera(self):
        historico = [
            {"role": "user", "content": "o que você vê?"},
            {"role": "assistant", "content": "Uma camiseta azul."},
            {"role": "user", "content": "e isso no site, resume?"},
        ]
        self.assertNotIn("condor_olhar_camera",
                         {s["function"]["name"] for s in _selecionar_esquemas_locais(historico)})
        self.assertNotIn("condor_olhar_camera",
                         {s["function"]["name"] for s in _esquemas_completos(historico)})

    def test_camera_phrases_route_to_camera(self):
        for frase in self.CAMERA:
            with self.subTest(frase=frase):
                self.assertIn("condor_olhar_camera", nomes(frase))

    def test_screen_phrases_still_route_to_screenshot(self):
        for frase in ("veja a minha tela", "o que você vê na minha tela?", "print da tela"):
            with self.subTest(frase=frase):
                self.assertIn("screenshot", nomes(frase))
                self.assertNotIn("condor_olhar_camera", nomes(frase))

    def test_unrelated_phrases_do_not_offer_camera(self):
        for frase in self.NAO_CAMERA:
            with self.subTest(frase=frase):
                self.assertNotIn("condor_olhar_camera", nomes(frase))


if __name__ == "__main__":
    unittest.main()
