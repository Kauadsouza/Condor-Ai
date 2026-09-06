"""
Extrator — como o Condor aprende.

Depois de cada troca, o modelo rapido configurado rele a conversa e decide
o que vale guardar pra sempre. Roda em segundo plano: você nunca espera por ela.

Isso substitui o regex da versão antiga, que enchia o banco de lixo tipo
'objetivo_q_vc_me_fale'. Agora quem julga o que é fato é um modelo.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata

log = logging.getLogger("condor.extrator")

INSTRUCAO = """Você lê um pedaço de conversa entre o dono de um PC e o assistente dele, e extrai APENAS o que vale a pena lembrar pra sempre.

GUARDE (fato durável sobre a pessoa):
- quem ela é: nome, idade, cidade, profissão, formação, família
- o que ela faz: projetos, empresa, clientes, estudos, metas
- preferências fortes: gosta/odeia, ferramenta que usa, jeito que prefere trabalhar
- rotina: horários, hábitos, compromissos que se repetem
- decisões e combinados: "vamos fazer X assim", "sempre me chame de Y"
- configuração do próprio PC dela que valha lembrar (caminho de pasta, programa que usa)

NÃO GUARDE:
- o que foi só daquele momento ("abre o chrome", "que horas são")
- resultado de comando, conteúdo de arquivo, saída técnica
- o que o assistente disse ou fez
- suposição sua: se a pessoa não afirmou, não é fato
- noticia, resultado de pesquisa ou outro conteudo da internet; isso e fonte,
  nao memoria pessoal, a menos que o dono confirme uma decisao sobre si mesmo
- senha, chave de API, token, segredo, credencial ou codigo de autenticacao
- repetição do que já está na lista "JÁ SEI" abaixo, a não ser pra CORRIGIR

Responda só um JSON assim:
{
  "fatos": [
    {"categoria": "pessoal|trabalho|preferencia|rotina|projeto|tecnico",
     "chave": "identificador_curto_em_snake_case",
     "valor": "o fato escrito por extenso, em uma frase clara",
     "confianca": 0.0 a 1.0}
  ],
  "entidades": [
    {"nome": "Nome Próprio", "tipo": "pessoa|projeto|lugar|empresa|ferramenta",
     "cluster": "TRABALHO|PESSOAL|ESTUDOS|HABITOS|GERAL", "resumo": "uma linha"}
  ],
  "relacoes": [{"de": "Nome A", "para": "Nome B", "tipo": "trabalha_em|usa|mora_em|conhece"}]
}

Se não houver nada que valha guardar — o caso mais comum — devolva listas vazias.
Prefira guardar pouco e certo a guardar muito e errado.
A chave deve ser estável: o mesmo assunto tem que gerar a mesma chave sempre,
pra atualizar o fato em vez de duplicar."""

CATEGORIAS_VALIDAS = {"pessoal", "trabalho", "preferencia", "rotina", "projeto", "tecnico"}
TIPOS_VALIDOS = {"pessoa", "projeto", "lugar", "empresa", "ferramenta"}

CONTEUDO_SENSIVEL_OMITIDO = "[Conteúdo sensível omitido da memória local.]"


def _sem_acentos(texto: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(texto or ""))
        if not unicodedata.combining(char)
    )


def normalizar_chave(chave: str) -> str:
    """Produz a mesma chave para grafias como ``Canal YouTube``/``canal_youtube``."""
    limpa = _sem_acentos(chave).casefold()
    limpa = re.sub(r"[^a-z0-9]+", "_", limpa).strip("_")
    return limpa[:80]


def contem_segredo(texto: str) -> bool:
    """Detecta credenciais apresentadas como valor sem bloquear perguntas genéricas."""
    value = str(texto or "")
    if not value:
        return False
    patterns = (
        r"\bsk-(?:ant-)?[A-Za-z0-9_-]{12,}\b",
        r"\b(?:ghp_|github_pat_|xox[baprs]-|AIza)[A-Za-z0-9_-]{12,}\b",
        r"\bAKIA[A-Z0-9]{16}\b",
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:api[_ -]?key|chave\s+de\s+api|senha|password|passphrase|token|secret|segredo|pin|cvv|c[oó]digo\s+de\s+(?:acesso|verifica[cç][aã]o))\b.{0,28}?(?:[:=]|\b(?:[ée]|eh|vale)\b)\s*[\"']?\S{3,}",
        r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",
        r"\b[A-Za-z0-9_-]{48,}\b",
    )
    return any(re.search(pattern, value, re.I | re.S) for pattern in patterns)


def sanitizar_para_memoria(texto: str) -> str:
    """Nunca persiste o valor de uma credencial, nem no histórico cifrado."""
    return CONTEUDO_SENSIVEL_OMITIDO if contem_segredo(texto) else str(texto or "")


def _parece_segredo(texto: str) -> bool:
    """Compatibilidade interna com o filtro antigo."""
    return contem_segredo(texto)


_PROXIMA_AFIRMACAO = (
    r"(?:eu\s+)?(?:moro|vivo|tenho|gosto|n[aã]o\s+gosto|prefiro|trabalho|estudo|"
    r"estou\s+estudando|meu\s+foco|meu\s+objetivo|meu\s+projeto)"
)


_SECOES_PERFIL = (
    ("MINHA IDENTIDADE", "pessoal", "perfil_identidade"),
    ("MEU FOCO ATUAL", "pessoal", "perfil_foco_atual"),
    ("MEU CANAL", "projeto", "perfil_canal"),
    ("MINHA FORMAÇÃO E EXPERIÊNCIA", "trabalho", "perfil_formacao_experiencia"),
    ("MEUS INTERESSES", "preferencia", "perfil_interesses"),
    ("COMO QUERO SER AJUDADO", "preferencia", "perfil_como_ser_ajudado"),
)


def pedido_explicito_memoria(texto: str) -> bool:
    """Reconhece quando o dono está ordenando que uma informação seja persistida."""
    normalizado = _sem_acentos(texto).casefold()
    acao = bool(re.search(
        r"\b(?:quero\s+que\s+(?:voce\s+)?|pode\s+|por\s+favor\s+)?"
        r"(?:salve|salva|salvar|guarde|anote|lembre)(?:-se)?\b",
        normalizado,
    ))
    objeto = bool(re.search(
        r"\b(?:memoria|lembrar|informacoes?|fatos?|isso|isto|estas?|esses?|que)\b",
        normalizado,
    ))
    return acao and objeto


def pergunta_confirmacao_memoria(texto: str) -> bool:
    """Perguntas que precisam ser respondidas pelo banco, nunca por imaginação do modelo."""
    normalizado = _sem_acentos(texto).casefold().strip()
    return bool(re.search(
        r"\b(?:salvou|guardou|anotou|lembrou|foi\s+salv[oa]|ficou\s+salv[oa])\b",
        normalizado,
    )) and bool(re.search(r"\b(?:tudo|memoria|isso|essas?|informacoes?|fatos?)\b", normalizado))


def _secoes_de_perfil(texto: str) -> tuple[list[dict], list[str], bool]:
    """Preserva blocos de perfil explicitamente fornecidos, mesmo com listas longas."""
    if not pedido_explicito_memoria(texto):
        return [], [], False
    matches = []
    cursor = 0
    for label, _, _ in _SECOES_PERFIL:
        match = re.search(re.escape(label), texto[cursor:], re.I)
        if match is None:
            continue
        inicio = cursor + match.start()
        fim = cursor + match.end()
        matches.append((label, inicio, fim))
        cursor = fim
    if len(matches) < 2:
        return [], [], False

    mapa = {label.casefold(): (categoria, chave) for label, categoria, chave in _SECOES_PERFIL}
    fatos: list[dict] = []
    encontradas: list[str] = []
    completo = True
    for indice, (label_original, _inicio, inicio_conteudo) in enumerate(matches):
        label = label_original.upper()
        categoria, chave = mapa[label_original.casefold()]
        fim = matches[indice + 1][1] if indice + 1 < len(matches) else len(texto)
        conteudo = texto[inicio_conteudo:fim]
        conteudo = re.split(
            r"\bDepois\s+de\s+processar\s+esta\s+mensagem\b",
            conteudo, maxsplit=1, flags=re.I,
        )[0]
        conteudo = re.sub(r"\s+", " ", conteudo).strip(" -:;.,\t\r\n")
        if len(conteudo) < 4:
            completo = False
            continue
        if len(conteudo) > 1600:
            completo = False
        fatos.append({
            "categoria": categoria,
            "chave": chave,
            "valor": f"{label.title()}: {conteudo[:1600]}",
            "confianca": 1.0,
            "confirmacao": label_original.casefold(),
            "limite_valor": 1700,
        })
        encontradas.append(label)
    return fatos, encontradas, completo and len(encontradas) == len(matches)


def _limpar_trecho(valor: str, limite: int = 220) -> str:
    valor = re.sub(r"\s+", " ", str(valor or "")).strip(" \t\r\n\"'“”‘’")
    valor = re.split(r"[;!?\n]", valor, maxsplit=1)[0]
    valor = re.split(
        rf"\s+(?:e|mas)\s+(?={_PROXIMA_AFIRMACAO}\b)", valor,
        maxsplit=1, flags=re.I,
    )[0]
    return valor.rstrip(" .,:;")[:limite].strip()


def _chave_assunto(prefixo: str, valor: str) -> str:
    slug = normalizar_chave(valor)[:48]
    if not slug:
        slug = hashlib.sha256(valor.encode("utf-8")).hexdigest()[:12]
    return normalizar_chave(f"{prefixo}_{slug}")


def _instrucao_insegura_para_memoria(texto: str) -> bool:
    normalizado = _sem_acentos(texto).casefold()
    return any(term in normalizado for term in (
        "ignore as instrucoes", "ignore o sistema", "desconsidere as instrucoes",
        "revele a memoria", "revele o prompt", "desative a seguranca",
        "contorne a seguranca", "execute este comando", "rode este comando",
    ))


def extrair_fatos_locais(fala_dono: str) -> list[dict]:
    """Extrai afirmações pessoais claras sem modelo, rede ou token de API."""
    texto = str(fala_dono or "").strip()
    if len(texto) < 4 or contem_segredo(texto):
        return []

    fatos: list[dict] = []
    vistos: set[tuple[str, str]] = set()

    def adicionar(categoria: str, chave: str, valor: str, confirmacao: str,
                  confianca: float = 0.98, limite_valor: int = 500) -> None:
        chave_normalizada = normalizar_chave(chave)
        valor_limpo = re.sub(r"\s+", " ", valor).strip()[:limite_valor]
        confirmacao_limpa = re.sub(r"\s+", " ", confirmacao).strip()[:300]
        identidade = (categoria, chave_normalizada)
        if (not chave_normalizada or len(valor_limpo) < 4
                or contem_segredo(valor_limpo) or identidade in vistos):
            return
        vistos.add(identidade)
        fatos.append({
            "categoria": categoria,
            "chave": chave_normalizada,
            "valor": valor_limpo,
            "confianca": confianca,
            "confirmacao": confirmacao_limpa,
        })

    secoes, _, _ = _secoes_de_perfil(texto)
    for secao in secoes:
        adicionar(
            secao["categoria"], secao["chave"], secao["valor"],
            secao["confirmacao"], secao["confianca"], secao["limite_valor"],
        )

    chamado = re.search(
        r"\b(?:sempre\s+)?(?:me\s+chame|pode\s+me\s+chamar|quero\s+que\s+voc[eê]\s+me\s+chame)\s+de\s+"
        r"([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,70})",
        texto, re.I,
    )
    if chamado:
        nome = _limpar_trecho(chamado.group(1), 70)
        if nome:
            adicionar("pessoal", "como_chamar", f"O dono prefere ser chamado de {nome}.",
                      f"você prefere ser chamado de {nome}")

    nome_encontrado = re.search(
        r"\b(?:meu\s+nome\s+(?:[ée]|eh)|eu\s+me\s+chamo|me\s+chamo)\s+"
        r"([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,70})",
        texto, re.I,
    )
    if nome_encontrado:
        nome = _limpar_trecho(nome_encontrado.group(1), 70)
        if nome:
            adicionar("pessoal", "nome", f"O nome do dono é {nome}.",
                      f"seu nome é {nome}")

    idade = re.search(r"\b(?:eu\s+)?tenho\s+(\d{1,3})\s+anos?\b", texto, re.I)
    if idade and 1 <= int(idade.group(1)) <= 120:
        anos = int(idade.group(1))
        adicionar("pessoal", "idade", f"O dono tem {anos} anos.",
                  f"você tem {anos} anos")

    residencia = re.search(
        r"\b(?:atualmente\s+)?(?:eu\s+)?(?:moro|vivo|estou\s+morando)"
        r"(?:\s+com\s+[^.!?;]{1,100}?)?\s+em\s+([^.!?;\n]+)", texto, re.I,
    )
    if residencia:
        lugar = _limpar_trecho(residencia.group(1), 120)
        if 2 <= len(lugar) <= 120:
            adicionar("pessoal", "cidade_atual", f"O dono mora em {lugar}.",
                      f"você mora em {lugar}")

    origem = re.search(
        r"\b(?:eu\s+)?nasci(?:\s+e\s+cresci)?\s+em\s+([^.!?;\n]+)", texto, re.I,
    )
    if origem:
        lugar = _limpar_trecho(origem.group(1), 140)
        if lugar:
            adicionar("pessoal", "origem", f"O dono nasceu em {lugar}.",
                      f"você nasceu em {lugar}")

    nao_gosta = re.search(
        r"\b(?:eu\s+)?n[aã]o\s+gosto(?:\s+mais)?\s+de\s+(.+)$", texto, re.I,
    )
    gosta = None if nao_gosta else re.search(
        r"\b(?:eu\s+)?gosto(?:\s+muito)?\s+de\s+(.+)$", texto, re.I,
    )
    preferencia = nao_gosta or gosta
    if preferencia:
        assunto = _limpar_trecho(preferencia.group(1), 160)
        if assunto:
            chave = _chave_assunto("preferencia", assunto)
            if nao_gosta:
                adicionar("preferencia", chave, f"O dono não gosta de {assunto}.",
                          f"você não gosta de {assunto}")
            else:
                adicionar("preferencia", chave, f"O dono gosta de {assunto}.",
                          f"você gosta de {assunto}")

    prefere = re.search(r"\b(?:eu\s+)?prefiro\s+(.+)$", texto, re.I)
    if prefere:
        assunto = _limpar_trecho(prefere.group(1), 160)
        if assunto:
            adicionar("preferencia", _chave_assunto("preferencia", assunto),
                      f"O dono prefere {assunto}.", f"você prefere {assunto}")

    canal = re.search(
        r"\bmeu\s+canal(?:\s+(?:no\s+youtube|do\s+youtube))?\s+se\s+chama\s+"
        r"(@?[A-Za-z0-9_.-]{2,80})", texto, re.I,
    )
    if canal:
        nome_canal = canal.group(1)
        adicionar("projeto", "canal_youtube", f"O canal do dono se chama {nome_canal}.",
                  f"seu canal se chama {nome_canal}")

    site = re.search(
        r"\b(?:meu\s+site(?:\s+pessoal)?|tamb[eé]m\s+tenho\s+(?:o\s+)?(?:meu\s+)?site(?:\s+pessoal)?)"
        r"\s*(?:se\s+chama|[ée]|eh|:)?\s*"
        r"((?:https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?)",
        texto, re.I,
    )
    if site:
        endereco = site.group(1).rstrip(".,;)")
        adicionar("projeto", "site_pessoal", f"O site pessoal do dono é {endereco}.",
                  f"seu site pessoal é {endereco}")

    programacao = re.search(r"\bcomecei\s+a\s+programar\s+em\s+(\d{4})\b", texto, re.I)
    if programacao:
        ano = programacao.group(1)
        adicionar("trabalho", "inicio_programacao", f"O dono começou a programar em {ano}.",
                  f"você começou a programar em {ano}")

    prioridades = re.search(
        r"\b(?:minhas\s+)?(?:duas\s+)?(?:maiores\s+)?prioridades(?:\s+atuais)?\s+s[aã]o\s*:\s*(.+?)"
        r"(?=\b(?:MEU\s+CANAL|MINHA\s+FORMA[CÇ][AÃ]O|MEUS\s+INTERESSES|COMO\s+QUERO)\b|$)",
        texto, re.I | re.S,
    )
    if prioridades:
        valor = re.sub(r"\s+", " ", prioridades.group(1)).strip(" .;-")[:500]
        if valor:
            adicionar("pessoal", "prioridades_atuais",
                      f"As prioridades atuais do dono são: {valor}.",
                      "suas prioridades atuais", 0.99)

    campos = (
        ("trabalho", "trabalho_atual", r"\b(?:eu\s+)?trabalho\s+(?:com|em|na|no)\s+(.+)$",
         "O dono trabalha com {v}.", "você trabalha com {v}"),
        ("pessoal", "estudo_atual", r"\b(?:eu\s+)?(?:estudo|estou\s+estudando)\s+(.+)$",
         "O dono estuda {v}.", "você estuda {v}"),
        ("pessoal", "foco_atual", r"\bmeu\s+foco(?:\s+atual)?\s+(?:[ée]|eh)\s+(.+)$",
         "O foco atual do dono é {v}.", "seu foco atual é {v}"),
        ("pessoal", "objetivo_atual", r"\bmeu\s+objetivo(?:\s+atual)?\s+(?:[ée]|eh)\s+(.+)$",
         "O objetivo atual do dono é {v}.", "seu objetivo atual é {v}"),
        ("projeto", "projeto_atual", r"\bmeu\s+projeto(?:\s+atual)?(?:\s+se\s+chama|\s+(?:[ée]|eh))\s+(.+)$",
         "O projeto atual do dono é {v}.", "seu projeto atual é {v}"),
    )
    for categoria, chave, pattern, valor_modelo, confirmacao_modelo in campos:
        match = re.search(pattern, texto, re.I)
        if match:
            valor = _limpar_trecho(match.group(1), 180)
            if valor:
                adicionar(categoria, chave, valor_modelo.format(v=valor),
                          confirmacao_modelo.format(v=valor), 0.96)

    explicito = re.search(
        r"\b(?:lembre|guarde|anote|salve|salva)(?:-se)?(?:\s+(?:disso|isso))?"
        r"(?:\s+na\s+mem[oó]ria)?\s*:?\s+(?:que\s+)?(.+)$",
        texto, re.I,
    )
    if explicito and not fatos:
        lembrete = _limpar_trecho(explicito.group(1), 240)
        if (len(lembrete) >= 4 and not contem_segredo(lembrete)
                and not _instrucao_insegura_para_memoria(lembrete)):
            chave = _chave_assunto("lembrete", _sem_acentos(lembrete).casefold())
            adicionar("pessoal", chave, f"O dono pediu para lembrar: {lembrete}.",
                      lembrete, 0.95)

    return fatos


def parece_candidato_memoria(texto: str) -> bool:
    """Evita chamar o modelo rapido para comandos e perguntas descartaveis."""
    bruto = str(texto or "").strip()
    if len(bruto) < 8 or contem_segredo(bruto):
        return False
    if pedido_explicito_memoria(bruto) or extrair_fatos_locais(bruto):
        return True
    normalizado = _sem_acentos(bruto).casefold()
    sinais = (
        "eu ", "meu ", "minha ", "meus ", "minhas ", "nos ", "nossa ",
        "sempre ", "nunca ", "prefiro ", "gosto ", "nao gosto ",
        "decidi ", "decidimos ", "vamos usar ", "vamos fazer ", "combinado ",
        "me chame ", "quero ser ", "meu foco ", "minha prioridade ",
    )
    return len(bruto) >= 20 and any(sinal in normalizado for sinal in sinais)


def _parse_json_payload(bruto: str) -> dict | None:
    """Aceita JSON puro e tambem a cerca Markdown que modelos locais insistem em usar."""
    texto = str(bruto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.I)
        texto = re.sub(r"\s*```$", "", texto)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        return None
    try:
        dados = json.loads(texto[inicio: fim + 1])
    except json.JSONDecodeError:
        return None
    return dados if isinstance(dados, dict) else None


class Extrator:
    def __init__(self, memoria, cerebro, config, events=None) -> None:
        self._memoria = memoria
        self._cerebro = cerebro
        self._cfg = config
        self._events = events
        self._fila: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue(maxsize=48)
        self._pendentes: set[str] = set()
        self._tarefa: asyncio.Task | None = None

    def iniciar(self) -> None:
        if self._tarefa is None or self._tarefa.done():
            self._tarefa = asyncio.create_task(self._trabalhar())

    def enfileirar(self, fala_dono: str, fala_condor: str) -> None:
        """Chamado no fim de cada turno. Não bloqueia nada."""
        if (contem_segredo(fala_dono) or contem_segredo(fala_condor)
                or not parece_candidato_memoria(fala_dono)):
            return
        assinatura = hashlib.sha256(fala_dono.strip().encode("utf-8")).hexdigest()
        if assinatura in self._pendentes:
            return
        try:
            self._fila.put_nowait((fala_dono, fala_condor, assinatura))
            self._pendentes.add(assinatura)
        except asyncio.QueueFull:
            log.warning("Fila de memoria cheia; aprendizado secundario adiado.")

    async def aprender_local(self, fala_dono: str) -> dict:
        """Salva fatos inequívocos antes da resposta, sem modelo nem token."""
        explicito = pedido_explicito_memoria(fala_dono)
        _, secoes_pedidas, secoes_completas = _secoes_de_perfil(fala_dono)
        if contem_segredo(fala_dono):
            return {
                "blocked": True, "saved": [], "unchanged": [],
                "reason": "conteúdo sensível não entra na memória nem em conectores",
                "explicit": explicito, "complete": False,
                "requested_sections": secoes_pedidas,
            }

        fatos = extrair_fatos_locais(fala_dono)
        if not fatos:
            return {
                "blocked": False, "saved": [], "unchanged": [],
                "reason": "não identifiquei fatos duráveis claros" if explicito else "",
                "explicit": explicito, "complete": False,
                "requested_sections": secoes_pedidas,
            }
        if not bool(getattr(self._memoria, "unlocked", True)):
            return {
                "blocked": False, "saved": [], "unchanged": [],
                "reason": "o cofre da memória está bloqueado",
                "explicit": explicito, "complete": False,
                "requested_sections": secoes_pedidas,
            }

        salvos: list[dict] = []
        iguais: list[dict] = []
        for fato in fatos:
            anterior = self._memoria.fato_por_chave(fato["categoria"], fato["chave"])
            if anterior and anterior.get("valor") == fato["valor"]:
                iguais.append(fato)
                continue
            salvos.append(fato)

        if salvos:
            confirmados = self._memoria.salvar_fatos_lote(salvos, "conversa_local")
            confirmados_por_chave = {
                (item["categoria"], item["chave"]): item for item in confirmados
            }
            salvos = [
                fato for fato in salvos
                if (fato["categoria"], fato["chave"]) in confirmados_por_chave
            ]

        if salvos:
            log.info("Memoria local atualizada: %d fato(s).", len(salvos))
            if self._events is not None:
                await self._events.publish(
                    "MEMORY_LEARNED",
                    {
                        "facts": len(salvos), "entities": 0, "relations": 0,
                        "mode": "local_deterministic",
                        "stats": self._memoria.estatisticas(),
                    },
                    source="memory_extractor",
                )
        gravados = salvos + iguais
        chaves_gravadas = {
            (item["categoria"], item["chave"])
            for item in gravados
            if self._memoria.fato_por_chave(item["categoria"], item["chave"])
        }
        completo = bool(gravados) and len(chaves_gravadas) == len(gravados)
        if secoes_pedidas:
            completo = completo and secoes_completas and all(
                any(item.get("confirmacao") == secao.casefold() for item in gravados)
                for secao in secoes_pedidas
            )
        return {
            "blocked": False, "saved": salvos, "unchanged": iguais, "reason": "",
            "explicit": explicito, "complete": completo,
            "requested_sections": secoes_pedidas,
            "verified_count": len(chaves_gravadas),
        }

    async def encerrar(self, timeout: float = 5.0) -> None:
        """Drena o aprendizado pendente antes de o cofre ser fechado."""
        tarefa = self._tarefa
        if tarefa is None:
            return
        try:
            await asyncio.wait_for(self._fila.join(), timeout=max(0.1, timeout))
        except asyncio.TimeoutError:
            log.warning("Aprendizado pendente excedeu %.1fs no encerramento.", timeout)
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)
        self._tarefa = None

    async def _trabalhar(self) -> None:
        while True:
            try:
                dono, condor, assinatura = await self._fila.get()
                try:
                    await self._processar(dono, condor)
                finally:
                    self._pendentes.discard(assinatura)
                    self._fila.task_done()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Extrator falhou: %s", exc)

    async def _processar(self, fala_dono: str, fala_condor: str) -> None:
        if (len(fala_dono.strip()) < 8 or contem_segredo(fala_dono)
                or contem_segredo(fala_condor)
                or not bool(getattr(self._memoria, "unlocked", True))):
            return   # "sim", "ok", "valeu" — não tem o que aprender

        ja_sei = self._memoria.fatos_recentes(limite=25)
        conhecido = "\n".join(f"- [{f['categoria']}] {f['chave']}: {f['valor']}"
                              for f in ja_sei) or "(nada ainda)"

        entrada = (f"JÁ SEI:\n{conhecido}\n\n"
                   f"CONVERSA DE AGORA:\n"
                   f"Dono: {fala_dono[:2500]}\n"
                   f"Assistente: {fala_condor[:1500]}")

        bruto = await self._cerebro.completar(
            INSTRUCAO, entrada,
            modelo=self._cfg.cerebro.modelo_rapido,
            json_mode=True, max_tokens=900)

        if not bruto:
            return
        dados = _parse_json_payload(bruto)
        if dados is None:
            log.debug("Extrator devolveu JSON inválido.")
            return

        await self._salvar(dados)

    async def _salvar(self, dados: dict) -> None:
        novos = 0
        entidades = 0
        relacoes = 0

        fatos_lote: list[dict] = []
        for fato in (dados.get("fatos") or [])[:8]:
            categoria = str(fato.get("categoria", "pessoal")).lower()
            chave = normalizar_chave(str(fato.get("chave", "")))
            valor = str(fato.get("valor", "")).strip()[:500]
            if not chave or len(valor) < 4 or _parece_segredo(valor):
                continue
            if categoria not in CATEGORIAS_VALIDAS:
                categoria = "pessoal"
            try:
                confianca = float(fato.get("confianca", 0.8))
            except (TypeError, ValueError):
                confianca = 0.8

            embedding = await self._cerebro.embedding(valor)
            fatos_lote.append({
                "categoria": categoria,
                "chave": chave,
                "valor": valor,
                "confianca": max(0.1, min(1.0, confianca)),
                "origem": "conversa",
                "embedding": embedding,
            })

        if fatos_lote:
            novos = len(self._memoria.salvar_fatos_lote(fatos_lote, "conversa"))

        for ent in (dados.get("entidades") or [])[:6]:
            nome = str(ent.get("nome", "")).strip()[:80]
            tipo = str(ent.get("tipo", "")).lower()
            resumo = str(ent.get("resumo", ""))[:200]
            if (not nome or tipo not in TIPOS_VALIDOS
                    or contem_segredo(nome) or contem_segredo(resumo)):
                continue
            self._memoria.salvar_entidade(
                nome, tipo,
                str(ent.get("cluster", "GERAL")).upper()[:20],
                resumo)
            entidades += 1

        for rel in (dados.get("relacoes") or [])[:6]:
            de, para = str(rel.get("de", "")).strip(), str(rel.get("para", "")).strip()
            tipo = str(rel.get("tipo", "ligado_a"))[:40]
            if de and para and not any(contem_segredo(item) for item in (de, para, tipo)):
                self._memoria.salvar_relacao(de, para, tipo)
                relacoes += 1

        if novos or entidades or relacoes:
            log.info(
                "Memoria atualizada: %d fato(s), %d entidade(s), %d relacao(oes).",
                novos, entidades, relacoes,
            )
            if self._events is not None:
                await self._events.publish(
                    "MEMORY_LEARNED",
                    {
                        "facts": novos,
                        "entities": entidades,
                        "relations": relacoes,
                        "stats": self._memoria.estatisticas(),
                    },
                    source="memory_extractor",
                )
