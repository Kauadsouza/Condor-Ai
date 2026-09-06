"""Deteccao deterministica de pedidos de imagem, compartilhada pelas interfaces."""

from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    value = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or ""))
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", value.casefold()).strip()


_ACTION = r"(?:cria|crie|criar|gera|gere|gerar|faz|faca|fazer|produza|produzir|desenha|desenhe|desenhar)"
_MEDIA = r"(?:img|imagem|imagens|foto|fotografia|ilustracao|arte|desenho|poster|capa|thumbnail)"


def is_image_request(text: str) -> bool:
    """Aceita formas naturais como ``cria uma img`` e ``imagem de um condor``."""
    value = _normalize(text)
    if not value:
        return False
    return bool(
        re.search(rf"\b{_ACTION}\b[^.!?]{{0,120}}\b{_MEDIA}\b", value)
        or re.search(rf"\b{_MEDIA}\b[^.!?]{{0,80}}\b{_ACTION}\b", value)
    )


def extract_image_prompt(text: str) -> str:
    """Remove somente o comando; conserva a descricao criativa do dono."""
    original = str(text or "").strip()
    stripped = re.sub(
        rf"^\s*(?:condor[, ]+)?{_ACTION}\s+(?:para mim\s+)?(?:uma?s?\s+)?{_MEDIA}\s*(?:de|do|da|com|:|-)?\s*",
        "",
        original,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or original
