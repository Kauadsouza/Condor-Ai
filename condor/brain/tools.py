"""
Catálogo de ferramentas que o modelo pode chamar (function calling nativo).

Cada entrada tem o schema que vai pra OpenAI e a função Python que executa.
Os nomes estão em português de propósito: o modelo raciocina em português com
o Condor, e ferramenta com nome na mesma língua reduz erro de escolha.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from condor.actions import executor as ex

log = logging.getLogger("condor.ferramentas")


def _f(nome: str, descricao: str, propriedades: dict, obrigatorios: list[str]) -> dict:
    del obrigatorios
    return {
        "type": "function",
        "function": {
            "name": nome,
            "description": descricao,
            "parameters": {
                "type": "object",
                "properties": propriedades,
                # A Responses API com strict=True exige todas as propriedades
                # em required. Campos conceitualmente opcionais usam valor
                # vazio/false, que os executores do Condor ja normalizam.
                "required": list(propriedades),
                "additionalProperties": False,
            },
        },
    }


_TXT = {"type": "string"}
_NUM = {"type": "integer"}
_REAL = {"type": "number"}
_BOOL = {"type": "boolean"}


ESQUEMAS: list[dict] = [
    # ── Arquivos ──────────────────────────────────────────────────────────
    _f("ler_arquivo",
       "Lê o conteúdo de um arquivo de texto, código ou config.",
       {"caminho": {**_TXT, "description": "Caminho completo ou relativo. Aceita ~ e %USERPROFILE%."}},
       ["caminho"]),

    _f("escrever_arquivo",
       "Cria ou sobrescreve um arquivo com o conteúdo dado. Cria as pastas do caminho "
       "se não existirem. Pra só acrescentar no fim, use anexar=true.",
       {"caminho": _TXT,
        "conteudo": {**_TXT, "description": "Conteúdo completo do arquivo."},
        "anexar": {**_BOOL, "description": "true acrescenta no fim em vez de sobrescrever."}},
       ["caminho", "conteudo"]),

    _f("listar_pasta",
       "Lista o que tem dentro de uma pasta, com tamanho dos arquivos.",
       {"caminho": {**_TXT, "description": "Pasta a listar. Ex: '~/Downloads'."}},
       ["caminho"]),

    _f("buscar_arquivos",
       "Procura arquivos pelo nome no PC. Sem raiz definida, varre Desktop, "
       "Documentos, Downloads e a pasta do Condor.",
       {"padrao": {**_TXT, "description": "Parte do nome ou padrão glob, ex: 'contrato' ou '*.pdf'."},
        "raiz": {**_TXT, "description": "Pasta onde procurar. Vazio = pastas do usuário."}},
       ["padrao"]),

    _f("deletar",
       "Apaga um arquivo ou pasta. Pasta com conteúdo exige recursivo=true. "
       "Apagar coisa grande ou de sistema vai pedir a senha do dono.",
       {"caminho": _TXT,
        "recursivo": {**_BOOL, "description": "true pra apagar pasta com tudo dentro."}},
       ["caminho"]),

    _f("mover", "Move ou renomeia arquivo/pasta.",
       {"origem": _TXT, "destino": _TXT}, ["origem", "destino"]),

    _f("copiar", "Copia arquivo ou pasta pra outro lugar.",
       {"origem": _TXT, "destino": _TXT}, ["origem", "destino"]),

    _f("baixar", "Baixa um arquivo da internet e salva no PC.",
       {"url": _TXT, "destino": {**_TXT, "description": "Onde salvar, com nome do arquivo."}},
       ["url", "destino"]),

    _f("ler_pdf", "Extrai o texto de um PDF.", {"caminho": _TXT}, ["caminho"]),

    # ── Apps, janelas, sistema ────────────────────────────────────────────
    _f("abrir",
       "Abre um programa, arquivo, pasta ou site. Aceita nome de app ('spotify', "
       "'calculadora'), caminho ou endereço ('youtube.com').",
       {"alvo": _TXT}, ["alvo"]),

    _f("fechar_app", "Fecha um programa que está aberto, pelo nome do processo.",
       {"nome": {**_TXT, "description": "Nome do processo, ex: 'chrome', 'spotify'."}},
       ["nome"]),

    _f("listar_janelas", "Lista os programas abertos agora, com o título da janela.",
       {}, []),

    _f("focar_janela", "Traz uma janela pra frente pelo título (pedaço basta).",
       {"titulo": _TXT}, ["titulo"]),

    _f("info_sistema",
       "Estado da máquina agora: CPU, RAM, disco, bateria, tempo ligado e os "
       "programas que mais consomem.", {}, []),

    # ── Tela, mouse, teclado ──────────────────────────────────────────────
    _f("screenshot",
       "Tira uma foto da tela e VÊ o que está nela. Use quando o dono perguntar "
       "sobre algo que está na tela dele, ou antes de clicar em algo pra saber onde clicar.",
       {}, []),

    _f("clicar", "Clica com o mouse numa coordenada da tela.",
       {"x": _NUM, "y": _NUM,
        "botao": {**_TXT, "enum": ["left", "right", "middle"]},
        "duplo": _BOOL},
       ["x", "y"]),

    _f("digitar", "Digita um texto na janela que está em foco agora.",
       {"texto": _TXT}, ["texto"]),

    _f("atalho", "Aperta uma combinação de teclas. Ex: 'ctrl+c', 'alt+tab', 'win+d', 'enter'.",
       {"teclas": _TXT}, ["teclas"]),

    _f("ler_clipboard", "Lê o que está copiado na área de transferência.", {}, []),

    _f("escrever_clipboard", "Coloca um texto na área de transferência.",
       {"texto": _TXT}, ["texto"]),

    # ── Mundo lá fora ─────────────────────────────────────────────────────
    _f("buscar_web",
       "Busca na internet. Use SEMPRE que precisar de informação atual: notícia, "
       "preço, cotação, documentação, algo que aconteceu depois do seu treino.",
       {"consulta": _TXT}, ["consulta"]),

    _f("ler_site", "Abre uma URL e lê o texto da página inteira.",
       {"url": _TXT}, ["url"]),

    # ── Memória ───────────────────────────────────────────────────────────
    _f("buscar_memoria",
       "Procura no seu banco de memória o que você já aprendeu sobre o dono e sobre "
       "conversas passadas. Use quando ele citar algo de antes que não está na "
       "referência do prompt.",
       {"consulta": {**_TXT, "description": "O que procurar. Ex: 'projeto do cliente', 'time que ele torce'."}},
       ["consulta"]),
]

# Ferramentas do proprio Condor. Diferente das ferramentas do PC, estas nunca
# acessam implementacoes globais: o servidor injeta um orquestrador autenticado
# com memoria, contexto, projetos e dispositivos daquela execucao.
INTERNAS = frozenset({
    "condor_estado",
    "condor_abrir_projeto",
    "condor_selecionar_regiao",
    "condor_criar_rascunho",
    "condor_salvar_codigo",
    "condor_historico_codigo",
    "condor_restaurar_codigo",
    "condor_criar_experimento",
    "condor_atualizar_experimento",
    "condor_registrar_memoria",
    "condor_buscar_dispositivos",
    "condor_conectar_dispositivo",
    "condor_desconectar_dispositivo",
})

ESQUEMAS.extend([
    _f("condor_estado",
       "Le o contexto, projeto, codigo, experimentos, dispositivos e permissoes atuais do Condor.",
       {}, []),
    _f("condor_abrir_projeto", "Abre um projeto existente e o torna o contexto ativo.",
       {"project_id": _TXT}, ["project_id"]),
    _f("condor_selecionar_regiao", "Seleciona uma regiao existente dentro do projeto ativo.",
       {"project_id": _TXT, "region_id": _TXT}, ["project_id", "region_id"]),
    _f("condor_criar_rascunho",
       "Cria um registro de componente em uma regiao, sem inventar dimensoes ou capacidade fisica.",
       {"project_id": _TXT, "region_id": _TXT, "name": _TXT, "type": _TXT, "notes": _TXT},
       ["project_id", "region_id", "name"]),
    _f("condor_salvar_codigo",
       "Salva codigo no workspace cifrado do projeto. A linguagem e identificada automaticamente e uma versao recuperavel e criada.",
       {"project_id": _TXT, "name": _TXT, "content": _TXT},
       ["project_id", "content"]),
    _f("condor_historico_codigo", "Lista as revisoes recuperaveis do codigo de um projeto.",
       {"project_id": _TXT}, ["project_id"]),
    _f("condor_restaurar_codigo", "Restaura uma revisao anterior como uma nova revisao do projeto.",
       {"project_id": _TXT, "revision": _NUM}, ["project_id", "revision"]),
    _f("condor_criar_experimento",
       "Cria no Laboratorio um experimento proposto, ligado ao projeto atual.",
       {"project_id": _TXT, "title": _TXT, "objective": _TXT}, ["project_id", "title"]),
    _f("condor_atualizar_experimento",
       "Move um experimento entre proposed, testing e done sem inventar resultado.",
       {"experiment_id": _TXT, "status": {**_TXT, "enum": ["proposed", "testing", "done"]}},
       ["experiment_id", "status"]),
    _f("condor_registrar_memoria",
       "Registra um fato duravel confirmado pelo dono na memoria cifrada. Nunca use para senhas, chaves ou tokens.",
       {"category": {**_TXT, "enum": ["pessoal", "trabalho", "preferencia", "rotina", "projeto", "tecnico"]},
        "key": _TXT, "value": _TXT, "confidence": _REAL},
       ["category", "key", "value"]),
    _f("condor_buscar_dispositivos", "Procura portas Arduino e seriais sem executar comando no hardware.",
       {}, []),
    _f("condor_conectar_dispositivo",
       "Abre uma conexao serial autorizada, sem enviar comando nem firmware.",
       {"port": _TXT, "baud_rate": _NUM, "project_id": _TXT}, ["port", "baud_rate"]),
    _f("condor_desconectar_dispositivo", "Fecha uma conexao serial aberta pelo Device Bridge.",
       {"device_id": _TXT}, ["device_id"]),
])

# Shell, codigo arbitrario e instalacao em tempo de execucao nao ficam
# disponiveis para a IA. Manutencao manual continua possivel fora do Condor.
# ── Ligação nome → função ────────────────────────────────────────────────────

FUNCOES: dict[str, Callable[..., dict]] = {
    "ler_arquivo": ex.ler_arquivo,
    "escrever_arquivo": ex.escrever_arquivo,
    "listar_pasta": ex.listar_pasta,
    "buscar_arquivos": ex.buscar_arquivos,
    "deletar": ex.deletar,
    "mover": ex.mover,
    "copiar": ex.copiar,
    "baixar": ex.baixar,
    "ler_pdf": ex.ler_pdf,
    "abrir": ex.abrir,
    "fechar_app": ex.fechar_app,
    "listar_janelas": ex.listar_janelas,
    "focar_janela": ex.focar_janela,
    "info_sistema": ex.info_sistema,
    "screenshot": ex.screenshot,
    "clicar": ex.clicar,
    "digitar": ex.digitar,
    "atalho": ex.atalho,
    "ler_clipboard": ex.ler_clipboard,
    "escrever_clipboard": ex.escrever_clipboard,
    "buscar_web": ex.buscar_web,
    "ler_site": ex.ler_site,
}

# Como cada ferramenta aparece na interface enquanto roda.
ROTULOS = {
    "ler_arquivo": "lendo arquivo",
    "escrever_arquivo": "escrevendo arquivo",
    "listar_pasta": "olhando a pasta",
    "buscar_arquivos": "procurando arquivos",
    "deletar": "apagando",
    "mover": "movendo",
    "copiar": "copiando",
    "baixar": "baixando",
    "ler_pdf": "lendo PDF",
    "abrir": "abrindo",
    "fechar_app": "fechando",
    "listar_janelas": "vendo o que está aberto",
    "focar_janela": "trazendo janela",
    "info_sistema": "checando a máquina",
    "screenshot": "olhando a tela",
    "clicar": "clicando",
    "digitar": "digitando",
    "atalho": "usando atalho",
    "ler_clipboard": "lendo o clipboard",
    "escrever_clipboard": "copiando",
    "buscar_web": "buscando na web",
    "ler_site": "lendo a página",
    "buscar_memoria": "lembrando",
    "condor_estado": "lendo o Condor",
    "condor_abrir_projeto": "abrindo projeto",
    "condor_selecionar_regiao": "selecionando regiao",
    "condor_criar_rascunho": "criando rascunho",
    "condor_salvar_codigo": "versionando codigo",
    "condor_historico_codigo": "vendo revisoes",
    "condor_restaurar_codigo": "restaurando codigo",
    "condor_criar_experimento": "criando experimento",
    "condor_atualizar_experimento": "atualizando experimento",
    "condor_registrar_memoria": "registrando memoria",
    "condor_buscar_dispositivos": "procurando dispositivos",
    "condor_conectar_dispositivo": "conectando dispositivo",
    "condor_desconectar_dispositivo": "desconectando dispositivo",
}


async def executar(nome: str, argumentos: dict, contexto: dict | None = None) -> dict:
    """Roda a ferramenta fora do laço de eventos — nenhuma delas é async e
    várias bloqueiam (subprocess, rede), então iriam travar a UI."""
    contexto = contexto or {}

    if nome == "buscar_memoria":
        recall = contexto.get("recall")
        if recall is None:
            return {"ok": False, "saida": "Memória indisponível."}
        return await recall.buscar_para_ferramenta(argumentos.get("consulta", ""))

    if nome in INTERNAS:
        orchestrator = contexto.get("orchestrator")
        if orchestrator is None:
            return {"ok": False, "saida": "Orquestrador do Condor indisponivel."}
        return await orchestrator.execute(nome, argumentos)

    fn = FUNCOES.get(nome)
    if fn is None:
        return {"ok": False, "saida": f"Ferramenta desconhecida: {nome}"}

    try:
        return await asyncio.to_thread(lambda: fn(**argumentos))
    except TypeError as exc:
        return {"ok": False, "saida": f"Argumentos errados pra {nome}: {exc}"}
    except Exception as exc:
        log.exception("Falha na ferramenta %s", nome)
        return {"ok": False, "saida": f"{type(exc).__name__}: {exc}"}
