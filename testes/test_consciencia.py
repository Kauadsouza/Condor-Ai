"""Consciência do CONDOR: ele sabe que tem memória, o que consegue fazer e o que
fez — com dados reais do banco, não com o que um modelo genérico diria."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ORIGINAL_HOME = os.environ.get("CONDOR_HOME")
_STATE = tempfile.TemporaryDirectory(prefix="condor-consciencia-")
os.environ["CONDOR_HOME"] = _STATE.name

from condor.brain import consciencia  # noqa: E402
from condor.brain.persona import montar_prompt, montar_prompt_leve  # noqa: E402
from condor.memory.db import Memoria  # noqa: E402


def tearDownModule():
    if _ORIGINAL_HOME is None:
        os.environ.pop("CONDOR_HOME", None)
    else:
        os.environ["CONDOR_HOME"] = _ORIGINAL_HOME
    _STATE.cleanup()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memoria = Memoria(Path(self.tmp.name) / "m.enc")
        self.memoria.inicializar()
        self.chave = os.urandom(32)
        self.memoria.unlock(self.chave)

    def tearDown(self):
        self.memoria.lock()
        self.tmp.cleanup()


class DiarioTests(Base):
    def test_diary_records_dedupes_and_survives_restart(self):
        self.assertTrue(self.memoria.registrar_diario("acao", "gerei uma imagem: rosto de Deus"))
        self.assertFalse(self.memoria.registrar_diario("acao", "gerei uma imagem: rosto de Deus"))
        self.assertFalse(self.memoria.registrar_diario("inventado", "x" * 10))
        self.memoria.registrar_diario("sobre_mim", "O dono me disse: você é meu Jarvis")
        self.assertEqual([d["tipo"] for d in self.memoria.diario()], ["sobre_mim", "acao"])
        self.assertEqual(self.memoria.autocontagem()["diario"], 2)

    def test_locked_memory_writes_nothing(self):
        self.memoria.lock()
        self.assertFalse(self.memoria.registrar_diario("acao", "abri o spotify"))
        self.assertEqual(self.memoria.diario(), [])
        self.memoria.unlock(self.chave)


class LimpezaTabelasAntigasTests(Base):
    def test_old_system_tables_go_away_and_real_memory_stays(self):
        with self.memoria._conn() as conn:
            conn.execute("CREATE TABLE hub_notes (id TEXT)")
            conn.execute("INSERT INTO hub_notes VALUES ('nota antiga do hub')")
            conn.execute("CREATE TABLE memory_episodes (id TEXT)")
        self.memoria.salvar_fato("pessoal", "nome", "O dono se chama Kauã")
        self.memoria.salvar_turno("user", "oi")
        self.memoria.registrar_diario("acao", "gerei uma imagem: gato")
        self.memoria.lock()
        self.memoria.unlock(self.chave)
        with self.memoria._conn(persistir=False) as conn:
            tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"hub_notes", "memory_episodes"} & tabelas)
        self.assertEqual(self.memoria.autocontagem()["fatos"], 1)
        self.assertEqual(self.memoria.historico(5)[0]["content"], "oi")
        self.assertEqual(len(self.memoria.diario()), 1)


class ApagarMensagemEFotoTests(Base):
    def test_deleted_message_leaves_the_db_and_the_live_conversation(self):
        from condor.session import Sessao
        self.memoria.salvar_turno("user", "minha senha do banco é 1234, esquece isso")
        self.memoria.salvar_turno("assistant", "Ok.")
        itens = self.memoria.historico_com_ids()
        self.assertEqual([i["role"] for i in itens], ["user", "assistant"])
        apagada = self.memoria.apagar_turno(itens[0]["id"])
        self.assertEqual(apagada["role"], "user")
        self.assertIsNone(self.memoria.apagar_turno(itens[0]["id"]))
        self.assertEqual(len(self.memoria.historico_com_ids()), 1)

        sessao = Sessao.__new__(Sessao)
        sessao.historico = [{"role": "user", "content": "minha senha do banco é 1234, esquece isso"},
                            {"role": "assistant", "content": "Ok."}]
        sessao.esquecer_mensagem(apagada["role"], apagada["content"])
        self.assertEqual(sessao.historico, [{"role": "assistant", "content": "Ok."}])

    def test_phone_photo_is_described_locally_and_only_the_request_is_saved(self):
        import asyncio
        import base64
        from condor.session import Sessao
        sessao = Sessao.__new__(Sessao)
        turnos, eventos = [], []

        async def processar(texto, por_voz, **kw):
            turnos.append((texto, kw.get("canal"), kw.get("anexo")))

        async def evento(tipo, **dados):
            eventos.append((tipo, dados.get("texto")))

        async def mudar(_novo):
            pass

        async def analisar(b64, pedido):
            self.assertEqual(pedido, "tô bem vestido?")
            return "camisa azul, calça preta"

        sessao.processar, sessao._evento, sessao._mudar_estado = processar, evento, mudar
        jpeg = base64.b64encode(b"\xff\xd8\xff" + b"0" * 100).decode()
        asyncio.run(sessao.foto_do_celular("tô bem vestido?", jpeg, analisar))
        texto, canal, anexo = turnos[0]
        self.assertEqual((texto, canal), ("tô bem vestido? [foto]", "celular"))
        self.assertIn("camisa azul", anexo)
        self.assertIn("<foto_enviada_pelo_dono>", anexo)
        asyncio.run(sessao.foto_do_celular("e essa?", base64.b64encode(b"GIF89a").decode(), analisar))
        self.assertEqual(eventos[-1][0], "erro")           # só JPEG/PNG


class DetectoresTests(unittest.TestCase):
    def test_identity_questions_are_about_him_not_the_owner(self):
        for frase in ("quem e voce ?", "Quem é você?", "o que você consegue fazer?", "você tem memória?",
                      "voce nao tem memoria nao ?"):
            self.assertTrue(consciencia.pergunta_de_identidade(frase), frase)
        self.assertFalse(consciencia.pergunta_de_identidade("você lembra que eu gosto de pizza?"))
        self.assertTrue(consciencia.pergunta_sobre_o_condor("essa img que vc gerou e do deus verdadeiro ?"))
        self.assertTrue(consciencia.pergunta_sobre_o_condor("voce nao tem memoria nao ?") or
                        consciencia.pergunta_de_identidade("voce tem memoria"))

    def test_what_the_owner_says_about_condor_goes_to_the_diary(self):
        self.assertIn("meu Jarvis", consciencia.dono_falou_do_condor("você é meu Jarvis, entendeu"))
        self.assertIn("mais curto", consciencia.dono_falou_do_condor("quero que você fale mais curto"))
        self.assertEqual(consciencia.dono_falou_do_condor("abre o spotify"), "")

    def test_plans_with_a_date_are_noted(self):
        self.assertIn("gravar", consciencia.plano_do_dono("eu to pensando se eu começo a gravar meus videos hoje ou amanhã"))
        self.assertIn("academia", consciencia.plano_do_dono("amanhã vou na academia cedo"))
        self.assertEqual(consciencia.plano_do_dono("vou pensar nisso"), "")
        self.assertEqual(consciencia.plano_do_dono("que horas são hoje?"), "")

    def test_opinions_and_real_actions(self):
        opiniao = consciencia.opiniao_do_condor(
            "começo hoje?", "Vai sim. Eu acho que começar hoje, mesmo simples, vale mais que esperar o perfeito.")
        self.assertIn("começar hoje", opiniao)
        self.assertEqual(consciencia.opiniao_do_condor("oi", "Oi! Tudo bem?"), "")
        self.assertEqual(consciencia.acao_do_condor("abrir", "abrindo", "spotify"), "abrindo: spotify")
        self.assertEqual(consciencia.acao_do_condor("buscar_memoria", "buscando", "x"), "")


class AutoconhecimentoTests(Base):
    def test_self_portrait_has_real_numbers_and_recent_actions(self):
        self.memoria.salvar_fato("pessoal", "nome", "O dono se chama Kauã")
        self.memoria.registrar_diario("acao", "gerei uma imagem: rosto de Deus")
        retrato = consciencia.autoconhecimento(self.memoria)
        self.assertIn("1 fatos sobre o dono", retrato)
        self.assertIn("Eu TENHO memória", retrato)
        self.assertIn("gerei uma imagem: rosto de Deus", retrato)
        self.assertIn("gerar imagens", retrato)
        completo = consciencia.autoconhecimento(self.memoria, completo=True)
        self.assertIn("Gerar imagens aqui no PC", completo)
        self.assertIn("Meus limites", completo)

    def test_locked_memory_still_says_it_exists(self):
        self.memoria.lock()
        self.assertIn("trancada", consciencia.autoconhecimento(self.memoria))
        self.memoria.unlock(self.chave)

    def test_prompt_carries_the_portrait_and_no_longer_denies_memory(self):
        prompt = montar_prompt("Kaua", modo_voz=False, mensagem_atual="quem é você?",
                               autoconhecimento="QUEM EU SOU\n- teste")
        self.assertIn("QUEM EU SOU", prompt)
        self.assertNotIn("Só existe memória quando", prompt)
        self.assertIn("Você TEM memória permanente", prompt)
        self.assertIn("opinião própria", prompt)
        self.assertIn("verdade dura", prompt)
        self.assertIn("INICIATIVA", prompt)
        leve = montar_prompt_leve("Kaua", "Em 29/09 o dono comentou: vou gravar hoje")
        self.assertIn("vou gravar hoje", leve)
        self.assertNotIn("lembrando isto", montar_prompt_leve("Kaua"))


class ValoresEmocoesTests(unittest.TestCase):
    def test_he_has_values_emotions_and_opinions(self):
        prompt = montar_prompt("Kaua", modo_voz=False, mensagem_atual="vc e racista ?")
        self.assertIn("Você TEM opiniões, emoções e valores pessoais", prompt)
        self.assertIn("racismo", prompt)
        self.assertTrue(consciencia.pergunta_sobre_o_condor("vc e racista ?"))
        self.assertTrue(consciencia.pergunta_sobre_o_condor("voce tem sentimentos?"))

    def test_base_model_denial_is_removed_but_normal_text_stays(self):
        from condor.brain.client import polir_resposta
        resposta = ("Não, eu não sou racista.\n\nSou uma inteligência artificial, e não tenho opiniões, "
                    "emoções ou valores pessoais. Respeito todo mundo igual.")
        polida = polir_resposta(resposta)
        self.assertNotIn("inteligência artificial", polida)
        self.assertIn("Respeito todo mundo igual.", polida)
        for normal in ("Não tenho valores exatos do preço, mas fica perto de 50 reais.",
                       "O ChatGPT é uma inteligência artificial da OpenAI."):
            self.assertEqual(polir_resposta(normal), normal)


class SessaoTests(Base):
    def _sessao(self):
        from condor.session import Sessao

        sessao = Sessao.__new__(Sessao)
        sessao.memoria = self.memoria
        sessao.historico = []
        sessao.ultimo_contato = 0
        return sessao

    def test_chat_image_enters_the_conversation_and_the_diary(self):
        sessao = self._sessao()
        sessao.registrar_imagem_do_chat("gere a IMG do rosto de Deus", "face of God, renaissance", "sdxl")
        self.assertEqual(sessao.historico[0], {"role": "user", "content": "gere a IMG do rosto de Deus"})
        self.assertIn("Gerei a imagem", sessao.historico[1]["content"])
        self.assertIn("gerei uma imagem", self.memoria.diario(("acao",))[0]["texto"])
        self.assertEqual(len(self.memoria.historico(10)), 2)

    def test_owner_speech_feeds_the_diary_but_secrets_do_not(self):
        sessao = self._sessao()
        sessao._anotar_fala_do_dono("você é meu Jarvis")
        sessao._anotar_fala_do_dono("amanhã vou gravar o vídeo novo")
        sessao._anotar_fala_do_dono("quero que você seja meu Jarvis, minha senha é sk-abc123def456ghi789jkl")
        tipos = sorted(d["tipo"] for d in self.memoria.diario())
        self.assertEqual(tipos, ["plano", "sobre_mim"])


if __name__ == "__main__":
    unittest.main()
