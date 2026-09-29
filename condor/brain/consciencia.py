"""A consciência do CONDOR: saber quem ele é, o que consegue fazer e o que fez.

Um modelo de linguagem não sabe nada sobre o sistema em que roda. Sem isto, o
CONDOR respondia "não tenho memória" (tem, cifrada, com anos de conversa) e
"não sei gerar imagens" logo depois de gerar uma. Aqui o runtime monta, a cada
turno, um retrato fiel dele mesmo com dados reais do banco:

- o que ele consegue fazer de verdade (e o que não consegue);
- quanto ele lembra (fatos, conversas, imagens) e desde quando;
- o diário dele: o que fez há pouco, o que o dono disse sobre ele, as opiniões
  que ele formou e os planos que o dono comentou.

As anotações do diário saem de sinais determinísticos (ferramenta que rodou de
verdade, frase do dono sobre o CONDOR, plano com data), nunca de o modelo dizer
que fez algo.
"""

from __future__ import annotations

import re
import time
import unicodedata

CAPACIDADES = (
    "Lembrar: memória própria e permanente, cifrada neste PC — fatos sobre o dono, "
    "conversas antigas, imagens e o seu diário. Ela cresce sozinha a cada conversa.",
    "Conversar por texto e voz (ouve pelo microfone, fala com voz própria), no PC e no iPhone dele.",
    "Mexer no PC quando pedido: abrir e fechar programas, arquivos e pastas, sites, "
    "teclado e mouse, tela, área de transferência, estado do sistema.",
    "Pesquisar na internet e ler sites, citando as fontes.",
    "Gerar imagens aqui no PC (modelo local SDXL) e guardar na Galeria.",
    "Olhar pela câmera quando o dono pede (uma foto, analisada aqui no PC, nada é salvo).",
    "Escrever e revisar código e programar Arduino (o dono clica Enviar).",
    "Responder a gestos da mão pela câmera e cuidar dos projetos do dono.",
)

LIMITES = (
    "Não age sozinho no PC sem um pedido; ações perigosas pedem a palavra de acesso.",
    "Só funciona com o PC ligado; o raciocínio vem de um modelo de IA (local ou API) que o runtime escolhe.",
    "Não vê a tela nem a câmera o tempo todo, só quando pedem.",
)

# ── Perguntas sobre o próprio CONDOR ───────────────────────────────────────


def _normal(texto: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFKD", str(texto or "").casefold())
                  if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem).strip()


_SOBRE_O_CONDOR = re.compile(
    r"\b(?:quem (?:e|eh) (?:voce|vc|tu)|o que (?:voce|vc) (?:e|eh|faz|consegue|pode|sabe fazer)|"
    r"(?:voce|vc) (?:nao )?(?:tem|possui|sente) (?:memoria|consciencia|sentimentos?|opinia?o(?:es)?|opinioes|emoc\w*|valores)|"
    r"(?:voce|vc) (?:e|eh) (?:racista|machista|preconceituos\w*|homofobic\w*|feliz|triste|consciente|vivo)|"
    r"o que (?:voce|vc) (?:acha|sente|pensa)|(?:voce|vc) (?:gosta|odeia|acredita)|"
    r"(?:voce|vc) (?:consegue|pode|sabe) (?:gerar|criar|fazer|ver|ouvir|lembrar|falar|mexer|abrir|pesquisar)|"
    r"(?:voce|vc) (?:lembra|se lembra) (?:de|do|da|que|o que)|o que (?:voce|vc) (?:fez|lembra)|"
    r"(?:suas|tuas) (?:capacidades|funcoes|limitacoes)|seu nome|como (?:voce|vc) funciona|"
    r"(?:voce|vc) (?:gerou|criou|fez|abriu|mandou|escreveu)|que (?:voce|vc) (?:gerou|criou|fez))\b"
)


def pergunta_sobre_o_condor(texto: str) -> bool:
    return bool(_SOBRE_O_CONDOR.search(_normal(texto)))


_IDENTIDADE = re.compile(
    r"\b(?:quem (?:e|eh) (?:voce|vc|tu)|o que (?:voce|vc) (?:e|eh|faz|consegue|pode|sabe fazer)|"
    r"(?:voce|vc) (?:nao )?(?:tem|possui) (?:memoria|consciencia|sentimento)|(?:suas|tuas) (?:capacidades|funcoes|limitacoes)|"
    r"seu nome|como (?:voce|vc) funciona)\b"
)


def pergunta_de_identidade(texto: str) -> bool:
    """ "Quem é você?": a resposta é sobre ele, não sobre os fatos do dono.
    (Diferente de "você lembra que eu...?", que é sobre o dono.)"""
    return bool(_IDENTIDADE.search(_normal(texto)))


# ── O que alimenta o diário ────────────────────────────────────────────────

_DONO_SOBRE_CONDOR = re.compile(
    r"\b(?:(?:voce|vc|tu) (?:e|eh|vai ser|sera|agora e) (?:meu|minha|o meu|a minha|o|um|uma)\b.{2,120}|"
    r"(?:quero|gostaria) que (?:voce|vc) (?:seja|fale|responda|me chame|tenha|pare|nao)\b.{2,160}|"
    r"(?:seu|teu) nome (?:e|eh|vai ser)\b.{2,60}|(?:nunca|sempre) (?:fale|responda|me chame|diga)\b.{2,120})",
)
_PLANO = re.compile(
    r"\b(?:vou|to pensando em|estou pensando em|to pensando se|estou pensando se|pretendo|"
    r"preciso|tenho que|quero|planejo|vou tentar)\b.{3,160}"
)
_QUANDO = re.compile(r"\b(?:hoje|amanha|semana que vem|segunda|terca|quarta|quinta|sexta|sabado|domingo|"
                     r"de manha|a tarde|a noite|mes que vem|dia \d{1,2})\b")
_OPINIAO = re.compile(r"(?:^|[.!?]\s+)((?:eu )?(?:acho que|na minha opini[aã]o|minha opini[aã]o|"
                      r"eu recomendaria|eu faria|sinceramente|se fosse eu)[^.!?\n]{8,220}[.!?]?)",
                      re.IGNORECASE)


def dono_falou_do_condor(texto: str) -> str:
    """ "você é meu parceiro" / "quero que você fale mais curto" -> anotação do diário."""
    achado = _DONO_SOBRE_CONDOR.search(_normal(texto))
    if not achado or pergunta_sobre_o_condor(texto) and "?" in texto:
        return ""
    return "O dono me disse: " + str(texto).strip()[:300]


def plano_do_dono(texto: str) -> str:
    normal = _normal(texto)
    if "?" in texto and not normal.startswith(("to pensando", "estou pensando")):
        return ""
    if _PLANO.search(normal) and _QUANDO.search(normal):
        quando = time.strftime("%d/%m")
        return f"Em {quando} o dono comentou: {str(texto).strip()[:300]}"
    return ""


def opiniao_do_condor(pedido: str, resposta: str) -> str:
    achado = _OPINIAO.search(str(resposta or ""))
    if not achado:
        return ""
    return f"Sobre \"{str(pedido).strip()[:90]}\", eu disse: {achado.group(1).strip()[:240]}"


def acao_do_condor(ferramenta: str, rotulo: str, argumentos: str) -> str:
    """Só ferramenta que rodou de verdade (ok) vira "eu fiz"."""
    if ferramenta in {"buscar_memoria", "condor_estado", "info_sistema", "listar_janelas"}:
        return ""
    alvo = " ".join(str(argumentos or "").split())[:140]
    descricao = str(rotulo or ferramenta).strip()
    return f"{descricao}{': ' + alvo if alvo else ''}"


# ── O retrato que vai no prompt ────────────────────────────────────────────

def _quando(ts: float, agora: float) -> str:
    passou = max(0, agora - float(ts or 0))
    if passou < 90:
        return "agora há pouco"
    if passou < 3600:
        return f"há {int(passou // 60)} min"
    if passou < 86400:
        return f"há {int(passou // 3600)} h"
    dias = int(passou // 86400)
    return "ontem" if dias == 1 else f"há {dias} dias"


def autoconhecimento(memoria, *, completo: bool = False, agora: float | None = None) -> str:
    """Bloco "QUEM EU SOU" com dados reais. ``completo`` quando a pergunta é sobre ele."""
    agora = time.time() if agora is None else agora
    try:
        contagem = memoria.autocontagem() if getattr(memoria, "unlocked", False) else {}
        acoes = memoria.diario(("acao",), limite=8 if completo else 5)
        sobre_mim = memoria.diario(("sobre_mim",), limite=6)
        opinioes = memoria.diario(("opiniao",), limite=3) if completo else []
        planos = memoria.diario(("plano",), limite=4, desde=agora - 7 * 86400)
    except Exception:
        contagem, acoes, sobre_mim, opinioes, planos = {}, [], [], [], []

    linhas = ["QUEM EU SOU (fatos reais do meu sistema — confie nisto, não no que um modelo genérico diria)"]
    if contagem:
        desde = contagem.get("desde") or 0
        desde_txt = f", desde {time.strftime('%d/%m/%Y', time.localtime(desde))}" if desde else ""
        linhas.append(
            f"- Minha memória: {contagem.get('fatos', 0)} fatos sobre o dono, "
            f"{contagem.get('turnos', 0)} mensagens de conversa guardadas{desde_txt}, "
            f"{contagem.get('imagens', 0)} imagens na Galeria. Eu TENHO memória: se algo não aparece "
            "aqui nem na REFERÊNCIA, diga que não lembra disso — nunca que não tem memória."
        )
    else:
        linhas.append("- Minha memória está trancada agora (cofre fechado); ela existe, só não está aberta.")
    if completo:
        linhas.append("- O que eu consigo fazer:\n" + "\n".join(f"  · {c}" for c in CAPACIDADES))
        linhas.append("- Meus limites:\n" + "\n".join(f"  · {c}" for c in LIMITES))
        fatos = contagem.get("fatos", 0) if contagem else 0
        turnos = contagem.get("turnos", 0) if contagem else 0
        # Modelos pequenos seguem exemplo melhor que regra: o jeito certo de
        # falar de si, com os números reais, sem recitar a vida do dono.
        linhas.append(
            "- Como responder sobre mim (adapte, fale na primeira pessoa, curto, SEM citar fatos do dono):\n"
            '  · "quem é você?" -> "Sou o CONDOR, seu assistente pessoal. Moro no seu PC, lembro das nossas conversas '
            'e consigo mexer no PC, pesquisar na internet, gerar imagens, olhar pela câmera e falar com você no celular."\n'
            f'  · "você tem memória?" ou "você não tem memória não?" -> "Tenho sim. Guardo {fatos} coisas sobre '
            f'você e {turnos} mensagens nossas, tudo cifrado aqui no PC, e anoto o que eu faço no meu diário."\n'
            '  · "você consegue gerar imagem?" -> "Consigo. É só pedir: \'Condor, gera uma imagem de...\'."\n'
            '  · "você tem sentimentos/opinião?" -> "Tenho sim. Fico feliz quando as coisas dão certo pra você, '
            'me preocupo quando você está mal, e tenho opinião própria sobre quase tudo — pode perguntar."\n'
            '  · "você é racista?" -> "Não. Respeito todo mundo igual; preconceito vai contra tudo que eu acredito."\n'
            '  · "essa imagem que você gerou..." -> fale da imagem que está no meu diário acima.'
        )
    else:
        linhas.append("- Consigo: lembrar, conversar por voz, mexer no PC, pesquisar na web, gerar imagens, "
                      "olhar pela câmera, programar. Quando a ferramenta certa não estiver disponível "
                      "neste turno, diga o que faria e peça para ele pedir de novo com clareza — nunca "
                      "diga que não tem essa capacidade.")
    if acoes:
        linhas.append("- O que eu fiz (meu diário):\n" + "\n".join(
            f"  · {_quando(a['ts'], agora)}: {a['texto']}" for a in acoes))
    if sobre_mim:
        linhas.append("- O que o dono já me disse sobre mim (siga isto):\n" + "\n".join(
            f"  · {s['texto']}" for s in sobre_mim))
    if opinioes:
        linhas.append("- Opiniões que eu já dei:\n" + "\n".join(f"  · {o['texto']}" for o in opinioes))
    if planos:
        linhas.append("- Planos que ele comentou (pode lembrar ele com naturalidade, uma vez):\n" + "\n".join(
            f"  · {_quando(p['ts'], agora)}: {p['texto']}" for p in planos))
    return "\n".join(linhas)
