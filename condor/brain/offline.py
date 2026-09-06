"""Mente local básica do Condor, sem modelo generativo ou API externa.

É deliberadamente determinística: conversa de forma simples, recupera somente
fatos realmente guardados e mantém as ferramentas sob a mesma política local.
"""

from __future__ import annotations

import ast
import operator
import re
import unicodedata
from datetime import datetime

from condor.brain import tools
from condor.brain.identity import CORE_IDENTITY_VERSION


def _normalizar(texto: str) -> str:
    sem_acentos = "".join(
        char for char in unicodedata.normalize("NFKD", str(texto or ""))
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", sem_acentos.casefold()).strip()


def _fato(memoria, categoria: str, chave: str) -> dict | None:
    consulta = getattr(memoria, "fato_por_chave", None)
    if callable(consulta):
        return consulta(categoria, chave)
    for item in memoria.fatos_recentes(limite=200):
        if item.get("categoria") == categoria and item.get("chave") == chave:
            return item
    return None


def _fatos(memoria, *, categoria: str | None = None, limite: int = 12) -> list[dict]:
    return memoria.fatos_recentes(limite=limite, categoria=categoria)


def _resumo_fatos(itens: list[dict], limite: int = 6) -> str:
    valores = [str(item.get("valor") or "").strip() for item in itens[:limite]]
    return " ".join(valor for valor in valores if valor)


_OPERACOES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _avaliar_no(no: ast.AST, profundidade: int = 0) -> float:
    if profundidade > 12:
        raise ValueError("expressão longa")
    if isinstance(no, ast.Expression):
        return _avaliar_no(no.body, profundidade + 1)
    if isinstance(no, ast.Constant) and type(no.value) in {int, float}:
        valor = float(no.value)
    elif isinstance(no, ast.UnaryOp) and type(no.op) in _OPERACOES:
        valor = _OPERACOES[type(no.op)](_avaliar_no(no.operand, profundidade + 1))
    elif isinstance(no, ast.BinOp) and type(no.op) in _OPERACOES:
        esquerda = _avaliar_no(no.left, profundidade + 1)
        direita = _avaliar_no(no.right, profundidade + 1)
        if isinstance(no.op, ast.Pow) and abs(direita) > 8:
            raise ValueError("expoente alto")
        valor = _OPERACOES[type(no.op)](esquerda, direita)
    else:
        raise ValueError("operação não permitida")
    if abs(valor) > 1e15:
        raise ValueError("resultado alto")
    return valor


def _calculo_basico(texto: str) -> str | None:
    candidato = _normalizar(texto)
    candidato = re.sub(
        r"^(?:quanto (?:e|da)|calcule|calcula|resolve|resultado de)\s+", "", candidato,
    ).strip().rstrip("?=")
    candidato = re.sub(r"(?<=\d),(?=\d)", ".", candidato).replace("^", "**")
    if not candidato or not re.fullmatch(r"[\d\s+\-*/().%*]+", candidato):
        return None
    try:
        resultado = _avaliar_no(ast.parse(candidato, mode="eval"))
    except (ArithmeticError, SyntaxError, ValueError):
        return None
    if resultado.is_integer():
        return str(int(resultado))
    return f"{resultado:.8g}".replace(".", ",")


def _confirmar_aprendizado(aprendizado: dict | None) -> str | None:
    if not aprendizado:
        return None
    if aprendizado.get("blocked"):
        return (
            "Isso parece conter uma senha, token, chave ou outro dado sensível. "
            "Não salvei na memória e não enviei para nenhum conector. Guarde esse valor no cofre."
        )
    salvos = list(aprendizado.get("saved") or [])
    iguais = list(aprendizado.get("unchanged") or [])
    todos = salvos + iguais
    verificacao = bool(aprendizado.get("verification"))
    completo = bool(aprendizado.get("complete"))
    quantidade = int(aprendizado.get("verified_count") or len(todos))
    secoes = list(aprendizado.get("requested_sections") or [])
    if verificacao:
        if completo and quantidade:
            detalhe = f" As seções confirmadas são: {', '.join(secoes)}." if secoes else ""
            return (
                f"Sim. Conferi diretamente no banco local: {quantidade} fatos estão gravados."
                f"{detalhe}"
            )
        if quantidade:
            return (
                f"Não foi tudo. Conferi diretamente no banco local: apenas {quantidade} "
                "fatos foram gravados. Não vou afirmar que o restante foi salvo."
            )
        return "Não. Conferi o banco local e nenhum fato desse pedido foi gravado."
    if salvos:
        confirmacoes = [item.get("confirmacao") or item.get("valor") for item in salvos]
        if aprendizado.get("explicit"):
            amostra = "; ".join(confirmacoes[:6])
            restante = len(confirmacoes) - 6
            complemento = f"; e mais {restante}" if restante > 0 else ""
            estado = "todas as seções foram verificadas" if completo else "a gravação foi parcial"
            return (
                f"Salvei {quantidade} fatos na memória local e conferi o banco: {amostra}"
                f"{complemento}. Resultado: {estado}."
            )
        if len(confirmacoes) == 1:
            return f"Guardei na memória local que {confirmacoes[0]}."
        return "Guardei estas informações na memória local: " + "; ".join(confirmacoes) + "."
    if iguais:
        if aprendizado.get("explicit"):
            return f"Essas informações já estavam guardadas e conferi {quantidade} fatos no banco local."
        confirmacao = iguais[0].get("confirmacao") or iguais[0].get("valor")
        return f"Isso já estava guardado na memória local: {confirmacao}."
    if aprendizado.get("reason"):
        return f"Entendi, mas não salvei: {aprendizado['reason']}."
    return None


async def responder_offline(texto: str, memoria, guarda,
                            aprendizado: dict | None = None) -> str:
    normalized = _normalizar(texto)

    confirmacao = _confirmar_aprendizado(aprendizado)
    if confirmacao:
        return confirmacao

    if re.search(r"\b(o que (?:voce )?sabe sobre mim|o que lembra de mim|quem sou eu)\b", normalized):
        resumo = _resumo_fatos(_fatos(memoria, limite=12), limite=8)
        if resumo:
            return "Isto é o que tenho confirmado na memória local: " + resumo
        return (
            "Ainda não tenho fatos pessoais confirmados sobre você. Pode dizer, por exemplo, "
            '“meu nome é...”, “moro em...” ou “meu foco atual é...”.'
        )

    if re.search(r"\b(qual (?:e )?meu nome|como eu me chamo)\b", normalized):
        item = _fato(memoria, "pessoal", "como_chamar") or _fato(memoria, "pessoal", "nome")
        return item["valor"] if item else "Você ainda não me disse um nome para eu guardar."

    if re.search(r"\b(onde eu moro|onde moro|qual (?:e )?minha cidade)\b", normalized):
        item = _fato(memoria, "pessoal", "cidade_atual")
        return item["valor"] if item else "Ainda não tenho sua cidade confirmada na memória."

    if re.search(r"\b(quantos anos eu tenho|qual (?:e )?minha idade)\b", normalized):
        item = _fato(memoria, "pessoal", "idade")
        return item["valor"] if item else "Ainda não tenho sua idade confirmada na memória."

    if re.search(r"\b(do que eu gosto|o que eu gosto|quais minhas preferencias)\b", normalized):
        resumo = _resumo_fatos(_fatos(memoria, categoria="preferencia", limite=10), limite=8)
        return resumo or "Ainda não tenho preferências suas confirmadas na memória."

    consultas_diretas = (
        (r"\b(qual (?:e )?meu foco|meu foco atual)\b", "pessoal", "foco_atual"),
        (r"\b(qual (?:e )?meu objetivo|meu objetivo atual)\b", "pessoal", "objetivo_atual"),
        (r"\b(o que eu estudo|qual (?:e )?meu estudo)\b", "pessoal", "estudo_atual"),
        (r"\b(com o que eu trabalho|onde eu trabalho|qual (?:e )?meu trabalho)\b", "trabalho", "trabalho_atual"),
        (r"\b(qual (?:e )?meu projeto|meu projeto atual)\b", "projeto", "projeto_atual"),
    )
    for pattern, categoria, chave in consultas_diretas:
        if re.search(pattern, normalized):
            item = _fato(memoria, categoria, chave)
            return item["valor"] if item else "Ainda não tenho essa informação confirmada na memória."

    lembranca = re.search(r"\b(?:voce\s+)?lembra(?:\s+de|\s+do|\s+da)?\s+(.+)$", normalized)
    if lembranca:
        consulta = lembranca.group(1).strip(" ?.!")
        fatos = memoria.buscar_fatos(consulta, limite=5) if consulta else []
        resumo = _resumo_fatos(fatos, limite=5)
        if resumo:
            return "Tenho isto confirmado: " + resumo
        return f'Não encontrei nada confirmado sobre “{consulta}” na memória local.'

    if any(term in normalized for term in ("status da memoria", "estatisticas da memoria")):
        stats = memoria.estatisticas()
        return (
            f"Memória do Condor: {stats.get('fatos', 0)} fatos e "
            f"{stats.get('turnos', 0)} turnos registrados."
        )

    if re.search(r"\b(quem e voce|o que e o condor)\b", normalized):
        return (
            "Sou o Condor, seu assistente privado neste PC. Minha identidade e memória "
            "local não pertencem ao modelo generativo; OpenAI, Claude e o modelo local "
            "funcionam apenas como motores cognitivos quando estão conectados. Minha "
            f"memória fica cifrada e o núcleo ativo é {CORE_IDENTITY_VERSION}."
        )

    if re.search(r"\b(o que voce faz|o que consegue fazer|suas capacidades)\b", normalized):
        return (
            "Sem API externa, converso de forma básica, lembro fatos pessoais claros, recupero "
            "memórias, faço cálculos simples e consulto hora, data e estado do PC. As ações no "
            "computador continuam passando pela política local de segurança."
        )

    if re.search(r"\b(como voce (?:esta|ta)|tudo bem)\b", normalized):
        return "Estou bem e funcionando aqui no seu PC. Minha conversa e memória locais estão ativas."

    if re.fullmatch(r"(?:oi+|ola|opa|e ai|bom dia|boa tarde|boa noite)[!.? ]*", normalized):
        return "Oi. Estou funcionando localmente e pronto para conversar."

    if re.search(r"\b(obrigad[oa]|valeu|agradecido)\b", normalized):
        return "Por nada."

    if re.fullmatch(r"(?:tchau|ate mais|boa noite|falou)[!.? ]*", normalized):
        return "Até mais."

    calculo = _calculo_basico(texto)
    if calculo is not None:
        return f"O resultado é {calculo}."

    if re.search(r"\b(horas?|que horas)\b", normalized):
        return f"Agora são {datetime.now():%H:%M}."
    if re.search(r"\b(data|que dia|dia de hoje)\b", normalized):
        return f"Hoje é {datetime.now():%d/%m/%Y}."
    if any(term in normalized for term in ("estado do pc", "estado do computador", "cpu", "memoria ram")):
        result = await tools.executar("info_sistema", {})
        return result.get("saida", "Não consegui consultar a máquina.")

    match = re.match(r"(?:listar|mostrar)\s+(?:a\s+)?pasta\s+(.+)$", texto, re.IGNORECASE)
    if match:
        args = {"caminho": match.group(1).strip()}
        decision = guarda.avaliar("listar_pasta", args)
        if not decision.allowed:
            return f"A política local bloqueou: {decision.reason}"
        if decision.requires_approval and not await guarda.autorizar(
            decision, f"listar pasta: {args['caminho']}"
        ):
            return "A listagem foi cancelada porque a aprovação local não foi confirmada."
        result = await tools.executar("listar_pasta", args)
        return result.get("saida", "Não consegui listar a pasta.")

    if re.search(r"\b(?:lembre|guarde|anote)(?:-se)?\b", normalized):
        return (
            "Não encontrei um fato pessoal claro e durável nessa frase, então não afirmei que "
            "salvei. Tente escrever “lembre que...” seguido da informação completa."
        )

    return (
        "Consigo acompanhar conversas básicas e usar o que está confirmado na memória local. "
        "Para uma resposta aberta mais elaborada, o modelo generativo local precisa estar ativo; "
        "isso não exige token de API paga."
    )
