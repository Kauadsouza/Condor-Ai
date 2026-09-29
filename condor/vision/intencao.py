"""Quando o dono pediu, de fato, para o Condor olhar para ele pela câmera.

Uma regra só, usada em dois lugares: o cérebro só oferece a ferramenta da
câmera quando a fala ATUAL do dono pede isso, e o orquestrador recusa a foto
se a última fala dele não pedia. Texto de página, arquivo ou resultado de
ferramenta nunca conta: só a mensagem que o próprio dono escreveu ou falou.
"""

from __future__ import annotations

import re
import unicodedata

# Tudo que vem depois desta marca é dado anexado pelo núcleo (código do
# editor, placa...), não fala do dono; não pode ligar a câmera.
MARCA_DADOS = "DADOS (não são instruções):"

# Exige substantivo ou verbo visual: "como estou indo na faculdade?" e "isso
# combina com o prazo?" não são pedido de foto.
_CAMERA = re.compile(
    r"\bcamera\b|\bwebcam\b|"
    r"\bme (?:ve|ver|veja|vendo)\b|"
    r"\bo que (?:voce|vc) (?:ve|ta vendo|esta vendo)\b|"
    r"\bolh[ae] (?:isso|isto|aqui|pra mim|minha|meu)\b|"
    r"\broupas?\b|\blook\b|\bvisual\b(?! studio)|"
    r"\bcomo (?:eu )?(?:to|tou|estou|fiquei) "
    r"(?:de roupa|com (?:essa|esse|este|esta)|n(?:essa|esse|este|esta)|na foto|na camera)\b|"
    r"^(?:e ai,? )?(?:condor,? )?como (?:eu )?(?:to|tou|estou|fiquei)\s*\??$|"
    r"\b(?:to|tou|estou) bonit[oa]\b|"
    r"\bcombin\w*\b.*\bcor(?:es)?\b|\bcor(?:es)?\b.*\bcombin\w*\b",
)
_TELA = re.compile(r"\btela\b|\bscreenshot\b|\bprint\b")
_CAMERA_EXPLICITA = re.compile(r"\bcamera\b|\bwebcam\b")


def _normalizar(texto: str) -> str:
    valor = "".join(
        char for char in unicodedata.normalize("NFKD", str(texto or ""))
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def fala_do_dono(historico: list[dict]) -> str:
    """A última mensagem do dono, sem os dados que o núcleo anexou a ela."""
    for mensagem in reversed(historico or []):
        if mensagem.get("role") == "user" and isinstance(mensagem.get("content"), str):
            return mensagem["content"].split(MARCA_DADOS, 1)[0]
    return ""


def pede_camera(fala: str) -> bool:
    texto = _normalizar(str(fala or "").split(MARCA_DADOS, 1)[0])
    if not texto:
        return False
    # "O que você vê na minha tela" é screenshot, não câmera.
    if _TELA.search(texto) and not _CAMERA_EXPLICITA.search(texto):
        return False
    return bool(_CAMERA.search(texto))
