"""CONDOR no iPhone: pareamento com convite + palavra de acesso, canal fechado
para quem não pareou, e a voz do turno pedido pelo celular volta para ele."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ORIGINAL_HOME = os.environ.get("CONDOR_HOME")
_STATE = tempfile.TemporaryDirectory(prefix="condor-celular-")
os.environ["CONDOR_HOME"] = _STATE.name

from fastapi.testclient import TestClient  # noqa: E402

from condor.celular import (  # noqa: E402
    COOKIE, Aparelhos, CanalCelular, Pontes, host_permitido, montar_app_celular, wav_valido,
)

SENHA = "uma frase secreta longa e exclusiva"
HOST = "https://pc-kaua.tail1234.ts.net"


def tearDownModule():
    if _ORIGINAL_HOME is None:
        os.environ.pop("CONDOR_HOME", None)
    else:
        os.environ["CONDOR_HOME"] = _ORIGINAL_HOME
    _STATE.cleanup()


def wav_b64(segundos=0.5):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(16000)
        arquivo.writeframes(b"\x00\x01" * int(16000 * segundos))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class AparelhosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agora = [1000.0]
        self.arquivo = Path(self.tmp.name) / "celulares.json"
        self.aparelhos = Aparelhos(self.arquivo, relogio=lambda: self.agora[0])

    def tearDown(self):
        self.tmp.cleanup()

    def test_pairing_needs_open_invite_and_passphrase(self):
        with self.assertRaises(PermissionError):
            self.aparelhos.parear("qualquer", lambda: True, "iPhone")
        convite = self.aparelhos.novo_convite()
        with self.assertRaises(PermissionError):
            self.aparelhos.parear(convite["codigo"], lambda: False, "iPhone")
        with self.assertRaises(PermissionError):
            self.aparelhos.parear("errado", lambda: True, "iPhone")
        token, aparelho = self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone do Kauã")
        self.assertEqual(aparelho["nome"], "iPhone do Kauã")
        self.assertEqual(self.aparelhos.validar(token)["id"], aparelho["id"])
        # O convite é de uso único.
        with self.assertRaises(PermissionError):
            self.aparelhos.parear(convite["codigo"], lambda: True, "outro")

    def test_only_the_token_hash_is_stored(self):
        convite = self.aparelhos.novo_convite()
        token, _ = self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")
        conteudo = self.arquivo.read_text(encoding="utf-8")
        self.assertNotIn(token, conteudo)
        relido = Aparelhos(self.arquivo, relogio=lambda: self.agora[0])
        self.assertIsNotNone(relido.validar(token))
        self.assertIsNone(relido.validar(token + "x"))
        self.assertIsNone(relido.validar(""))

    def test_invite_expires_and_guessing_burns_it(self):
        convite = self.aparelhos.novo_convite()
        self.agora[0] += 301
        with self.assertRaises(PermissionError):
            self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")
        convite = self.aparelhos.novo_convite()
        for _ in range(5):                      # código certo, senha chutada
            with self.assertRaises(PermissionError):
                self.aparelhos.parear(convite["codigo"], lambda: False, "iPhone")
        with self.assertRaises(PermissionError):
            self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")

    def test_revoked_or_expired_token_stops_working(self):
        convite = self.aparelhos.novo_convite()
        token, aparelho = self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")
        self.assertTrue(self.aparelhos.revogar(aparelho["id"]))
        self.assertIsNone(self.aparelhos.validar(token))
        convite = self.aparelhos.novo_convite()
        token, _ = self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")
        self.agora[0] += 181 * 86400
        self.assertIsNone(self.aparelhos.validar(token))

    def test_corrupted_file_is_ignored(self):
        self.arquivo.write_text('{"aparelhos": [{"id": "x", "hash": "nada"}]}', encoding="utf-8")
        self.assertEqual(Aparelhos(self.arquivo).listar(), [])
        ruins = [{"id": "a" * 12, "hash": "b" * 64, "criado": "ontem", "visto": 1, "expira": 1},
                 {"id": "c" * 12, "hash": "d" * 64, "criado": 1, "visto": 1, "expira": "inf"}]
        self.arquivo.write_text(json.dumps({"aparelhos": ruins}), encoding="utf-8")
        self.assertEqual(Aparelhos(self.arquivo).listar(), [])      # e o boot não cai

    def test_wrong_code_does_not_burn_the_owner_invite(self):
        convite = self.aparelhos.novo_convite()
        for _ in range(10):
            with self.assertRaises(PermissionError):
                self.aparelhos.parear("chute", lambda: True, "iPhone")
        with self.assertRaises(PermissionError):
            self.aparelhos.parear("çódigo-não-ascii", lambda: True, "iPhone")
        token, _ = self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")
        self.assertTrue(token)

    def test_idle_phone_must_pair_again(self):
        convite = self.aparelhos.novo_convite()
        token, _ = self.aparelhos.parear(convite["codigo"], lambda: True, "iPhone")
        self.agora[0] += 13 * 86400
        self.assertIsNotNone(self.aparelhos.validar(token))          # uso renova
        self.agora[0] += 15 * 86400
        self.assertIsNone(self.aparelhos.validar(token))


class Nucleo:
    """Pontes falsas: registra o que o celular pediu ao núcleo."""

    def __init__(self):
        self.textos, self.audios, self.senhas = [], [], []
        self.destrancado = True

    def pontes(self):
        async def texto(t):
            self.textos.append(t)

        async def audio(wav, com_nome):
            self.audios.append((len(wav), com_nome))

        async def destrancar(senha):
            return {"ok": senha == SENHA}

        async def calar():
            pass

        return Pontes(
            pronto=lambda: self.destrancado, motivo=lambda: "" if self.destrancado else "trancado",
            destrancar=destrancar, senha_confere=lambda s: s == SENHA,
            texto=texto, audio=audio, senha=self.senhas.append, calar=calar,
            estado=lambda: {"estado": "dormindo"}, historico=lambda: [],
        )


class AppCelularTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.aparelhos = Aparelhos(Path(self.tmp.name) / "celulares.json")
        self.canal = CanalCelular()
        self.nucleo = Nucleo()
        self.app = montar_app_celular(self.aparelhos, self.canal, self.nucleo.pontes(), 7778)
        self.cliente = TestClient(self.app, base_url=HOST)

    def tearDown(self):
        self.tmp.cleanup()

    def parear(self):
        convite = self.aparelhos.novo_convite()
        resposta = self.cliente.post("/api/parear", json={"codigo": convite["codigo"], "senha": SENHA, "nome": "iPhone"},
                                     headers={"Origin": HOST})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        cookie = resposta.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.token = resposta.cookies.get(COOKIE) or cookie.split("=", 1)[1].split(";", 1)[0]

    def test_nothing_answers_without_pairing(self):
        self.assertEqual(self.cliente.get("/api/eu").status_code, 401)
        self.assertEqual(self.cliente.post("/api/destrancar", json={"senha": SENHA}, headers={"Origin": HOST}).status_code, 401)
        with self.assertRaises(Exception):
            with self.cliente.websocket_connect("/ws", headers={"Origin": HOST, "Host": "pc-kaua.tail1234.ts.net", "Cookie": f"{COOKIE}=inventado"}) as ws:
                ws.receive_text()

    def test_wrong_passphrase_does_not_pair(self):
        convite = self.aparelhos.novo_convite()
        resposta = self.cliente.post("/api/parear", json={"codigo": convite["codigo"], "senha": "outra frase qualquer"},
                                     headers={"Origin": HOST})
        self.assertEqual(resposta.status_code, 403)
        self.assertNotIn("set-cookie", resposta.headers)

    def test_foreign_host_and_cross_origin_are_refused(self):
        self.assertFalse(host_permitido("evil.example", 7778))
        self.assertTrue(host_permitido("pc-kaua.tail1234.ts.net", 7778))
        self.assertTrue(host_permitido("127.0.0.1:7778", 7778))
        estranho = TestClient(self.app, base_url="https://evil.example")
        self.assertEqual(estranho.get("/api/eu").status_code, 400)
        convite = self.aparelhos.novo_convite()
        resposta = self.cliente.post("/api/parear", json={"codigo": convite["codigo"], "senha": SENHA},
                                     headers={"Origin": "https://evil.example"})
        self.assertEqual(resposta.status_code, 403)

    def test_other_port_on_the_same_tailnet_name_is_another_site(self):
        for origem in ("https://pc-kaua.tail1234.ts.net:8443", "http://pc-kaua.tail1234.ts.net", "null"):
            convite = self.aparelhos.novo_convite()
            resposta = self.cliente.post("/api/parear", json={"codigo": convite["codigo"], "senha": SENHA},
                                         headers={"Origin": origem})
            self.assertEqual(resposta.status_code, 403, origem)
        self.assertTrue(COOKIE.startswith("__Host-"))

    def test_body_without_length_is_refused(self):
        def corpo():
            yield b'{"codigo": "x", "senha": "' + b"a" * 20000 + b'"}'
        resposta = self.cliente.post("/api/parear", content=corpo(),
                                     headers={"Origin": HOST, "Content-Type": "application/json"})
        self.assertEqual(resposta.status_code, 411)

    def test_one_turn_at_a_time_and_voice_goes_to_who_asked(self):
        self.parear()
        async def texto_lento(_t):
            await asyncio.sleep(0.5)

        self.app = montar_app_celular(self.aparelhos, self.canal, Pontes(
            **{**self.nucleo.pontes().__dict__, "texto": texto_lento}), 7778)
        cliente = TestClient(self.app, base_url=HOST)
        cabecalho = {"Origin": HOST, "Host": "pc-kaua.tail1234.ts.net", "Cookie": f"{COOKIE}={self.token}"}
        with cliente.websocket_connect("/ws", headers=cabecalho) as ws:
            ws.receive_text(); ws.receive_text()
            ws.send_text(json.dumps({"tipo": "texto", "texto": "primeiro"}))
            ws.send_text(json.dumps({"tipo": "texto", "texto": "segundo"}))
            self.assertEqual(json.loads(ws.receive_text())["tipo"], "ocupado")
            meu_id = self.canal._sockets[0].state.celular_id
            self.assertEqual(self.canal.alvo_voz, meu_id)

    def test_paired_phone_chats_and_talks(self):
        self.parear()
        eu = self.cliente.get("/api/eu")
        self.assertEqual(eu.status_code, 200)
        self.assertTrue(eu.json()["pronto"])
        self.assertIn("microphone=(self)", eu.headers["permissions-policy"])
        # O cliente de teste não manda cookie Secure em ws://; o iPhone usa wss://.
        with self.cliente.websocket_connect("/ws", headers={"Origin": HOST, "Host": "pc-kaua.tail1234.ts.net", "Cookie": f"{COOKIE}={self.token}"}) as ws:
            self.assertEqual(json.loads(ws.receive_text())["tipo"], "estado")
            ws.receive_text()                                   # histórico
            ws.send_text(json.dumps({"tipo": "texto", "texto": "Condor, que horas são?"}))
            ws.send_text(json.dumps({"tipo": "audio", "wav": wav_b64(), "com_nome": True}))
            ws.send_text(json.dumps({"tipo": "audio", "wav": "não é áudio"}))
            self.assertEqual(json.loads(ws.receive_text())["tipo"], "erro")
            ws.send_text(json.dumps({"tipo": "senha", "texto": SENHA}))
            ws.send_text(json.dumps({"tipo": "ping"}))
            self.assertEqual(json.loads(ws.receive_text())["tipo"], "pong")
        self.assertEqual(self.nucleo.textos, ["Condor, que horas são?"])
        self.assertEqual(self.nucleo.audios[0][1], True)
        self.assertEqual(self.nucleo.senhas, [SENHA])

    def test_locked_pc_can_be_unlocked_from_the_phone(self):
        self.parear()
        self.nucleo.destrancado = False
        self.assertEqual(self.cliente.get("/api/eu").json()["motivo"], "trancado")
        errada = self.cliente.post("/api/destrancar", json={"senha": "chute errado aqui"}, headers={"Origin": HOST})
        self.assertEqual(errada.status_code, 403)
        certa = self.cliente.post("/api/destrancar", json={"senha": SENHA}, headers={"Origin": HOST})
        self.assertEqual(certa.status_code, 200)

    def test_revoked_phone_loses_access(self):
        self.parear()
        aparelho = self.aparelhos.listar()[0]
        self.aparelhos.revogar(aparelho["id"])
        self.assertEqual(self.cliente.get("/api/eu").status_code, 401)


class FiltroDeEventosTests(unittest.TestCase):
    def test_phone_only_gets_the_main_conversation(self):
        canal = CanalCelular()
        enviados = []

        class Socket:
            class state:
                voz_player = True

            async def send_text(self, texto):
                enviados.append(json.loads(texto)["tipo"])

        canal._sockets.append(Socket())

        async def rodar():
            for msg in ({"tipo": "resposta.token", "texto": "oi"},
                        {"tipo": "resposta.token", "texto": "x", "contexto": "programacao"},
                        {"tipo": "core.event", "event": {}}, {"tipo": "custo"},
                        {"tipo": "voz.audio", "wav": "..."}):
                await canal.transmitir(msg)
            await canal.entregar_voz({"tipo": "voz.audio", "wav": "..."})

        asyncio.run(rodar())
        self.assertEqual(enviados, ["resposta.token", "voz.audio"])

    def test_wav_validation(self):
        self.assertIsNotNone(wav_valido(wav_b64()))
        self.assertIsNone(wav_valido(base64.b64encode(b"x" * 5000).decode()))
        self.assertIsNone(wav_valido("%%%"))
        self.assertIsNone(wav_valido(None))
        self.assertIsNone(wav_valido(wav_b64(40)))           # grande demais


class SessaoCelularTests(unittest.IsolatedAsyncioTestCase):
    def _sessao(self):
        from condor.session import Sessao

        sessao = Sessao.__new__(Sessao)
        sessao._fala = None
        sessao._canal_turno = ""
        sessao._celular_toca = lambda: True
        sessao._entregar_celular = None
        sessao._tem_player = lambda: True
        sessao._avisar = None

        class Voz:
            pronto = True

            def calar(self):
                pass

            async def sintetizar(self, _frase):
                return b""

        sessao.voz = Voz()
        return sessao

    async def test_phone_turn_speaks_on_the_phone_not_on_the_pc(self):
        sessao = self._sessao()
        pc, celular = [], []

        async def no_pc(msg):
            pc.append(msg)

        async def no_celular(msg):
            celular.append(msg)

        sessao._entregar_audio = no_pc
        sessao.ligar_celular(lambda: True, no_celular)
        sessao._canal_turno = "celular"
        fala = sessao._nova_fala()
        self.assertIs(fala._entregar, no_celular)
        fala.cancelar()
        sessao._canal_turno = ""
        fala = sessao._nova_fala()
        self.assertIs(fala._entregar, no_pc)
        fala.cancelar()

    async def test_phone_turn_without_phone_player_stays_silent(self):
        sessao = self._sessao()

        async def entregar(_msg):
            pass

        sessao.ligar_celular(lambda: False, entregar)
        sessao._canal_turno = "celular"
        self.assertIsNone(sessao._nova_fala())

    async def test_hands_free_audio_needs_the_name(self):
        sessao = self._sessao()
        turnos, eventos = [], []

        class Ouvidos:
            def __init__(self):
                self.texto = ""

            async def transcrever(self, _wav):
                return self.texto

        async def processar(texto, por_voz, **kw):
            turnos.append((texto, por_voz, kw.get("canal")))

        async def evento(tipo, **dados):
            eventos.append(tipo)

        sessao.ouvidos = Ouvidos()
        sessao.processar = processar
        sessao._evento = evento
        from unittest import mock
        with mock.patch("condor.voice.wake.vosk_ouviu_condor", return_value=None):
            sessao.ouvidos.texto = "estou vendo um vídeo aqui"
            await sessao.audio_do_celular(b"wav", com_nome=True)
            sessao.ouvidos.texto = "Condor, que horas são?"
            await sessao.audio_do_celular(b"wav", com_nome=True)
            sessao.ouvidos.texto = "abre o spotify"
            await sessao.audio_do_celular(b"wav", com_nome=False)   # botão do microfone
        with mock.patch("condor.voice.wake.vosk_ouviu_condor", return_value=False):
            await sessao.audio_do_celular(b"wav", com_nome=True)    # porteiro barrou
        self.assertEqual(turnos, [("Condor, que horas são?", True, "celular"),
                                  ("abre o spotify", True, "celular")])
        self.assertEqual(eventos, ["transcricao", "transcricao"])


if __name__ == "__main__":
    unittest.main()
