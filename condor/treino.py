"""Treino do Condor: transforma as conversas avaliadas em dataset de ajuste fino.

O fluxo inteiro:

1. Cada resposta real do cérebro vira um exemplo cifrado (``treino_exemplos``).
2. No chat, o dono dá 👍/👎 e, no 👎, escreve como deveria ter sido.
3. ``exportar`` gera um JSONL no formato de mensagens (system/user/assistant)
   com o MESMO prompt de sistema que o Condor usa em cada turno.
4. O notebook ``treino/condor_treino_colab.ipynb`` treina o Qwen3-4B no Colab
   gratuito e devolve um ``.gguf``.
5. ``scripts/instalar_modelo_treinado.py`` registra o arquivo no Ollama e
   troca o modelo local do Condor (com volta fácil ao original).

O JSONL exportado fica em texto claro: é para ser enviado ao Colab. A
interface avisa isso antes de exportar.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from condor.brain.persona import conversa_leve, montar_prompt, montar_prompt_leve
from condor.paths import CODE_ROOT

# Abaixo disso o ajuste fino tende a decorar em vez de aprender o estilo.
META_EXEMPLOS = 150
NOTEBOOK = CODE_ROOT / "treino" / "condor_treino_colab.ipynb"
# Exemplos de estilo (direto, uma resposta por mensagem, sem puxar memória).
# Entram em todo treino: o primeiro já sai no jeito certo, antes de qualquer 👍.
ESTILO_BASE = CODE_ROOT / "treino" / "estilo_direto.json"


def exemplos_de_estilo() -> list[dict]:
    if not ESTILO_BASE.is_file():
        return []
    dados = json.loads(ESTILO_BASE.read_text(encoding="utf-8"))
    return [
        {"pedido": e["pedido"], "resposta": e["resposta"], "contexto": e.get("contexto", ""),
         "anteriores": e.get("anteriores", []), "por_voz": False}
        for e in dados.get("exemplos", []) if e.get("pedido") and e.get("resposta")
    ]


def montar_mensagens(exemplo: dict, dono: str) -> dict:
    # Mesmo prompt que o CONDOR usa na hora de responder (leve para papo,
    # enxuto e sem regras de ferramenta para o resto): o treino se transfere.
    pedido = str(exemplo.get("pedido") or "")
    if conversa_leve(pedido) and not exemplo.get("anteriores"):
        sistema = montar_prompt_leve(dono)
    else:
        sistema = montar_prompt(
            dono,
            str(exemplo.get("contexto") or ""),
            bool(exemplo.get("por_voz")),
            mensagem_atual=pedido,
            conhecimento_tecnico="",
            ferramentas=False,
        )
    alvo = str(exemplo.get("correcao") or "").strip() or str(exemplo.get("resposta") or "")
    mensagens = [{"role": "system", "content": sistema}]
    mensagens.extend(
        {"role": m["role"], "content": m["content"]}
        for m in exemplo.get("anteriores") or []
        if m.get("role") in {"user", "assistant"} and m.get("content")
    )
    mensagens.append({"role": "user", "content": str(exemplo.get("pedido") or "")})
    mensagens.append({"role": "assistant", "content": alvo})
    return {"messages": mensagens}


def montar_dataset(memoria, dono: str) -> list[dict]:
    exemplos = exemplos_de_estilo() + memoria.exemplos_para_treino()
    return [montar_mensagens(exemplo, dono) for exemplo in exemplos]


def exportar(memoria, dono: str, pasta: Path) -> dict:
    """Escreve o JSONL (e uma cópia do notebook) numa pasta do dono."""
    linhas = montar_dataset(memoria, dono)
    if not linhas:
        raise ValueError("não há exemplos de treino (nem os de estilo nem avaliações do chat)")
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = time.strftime("%Y%m%d-%H%M")
    destino = pasta / f"condor-treino-{carimbo}.jsonl"
    with destino.open("w", encoding="utf-8", newline="\n") as arquivo:
        for linha in linhas:
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
    notebook = None
    if NOTEBOOK.is_file():
        notebook = pasta / NOTEBOOK.name
        shutil.copyfile(NOTEBOOK, notebook)
    return {
        "arquivo": str(destino),
        "notebook": str(notebook) if notebook else "",
        "pasta": str(pasta),
        "exemplos": len(linhas),
        "estilo_base": len(exemplos_de_estilo()),
        "meta": META_EXEMPLOS,
    }
