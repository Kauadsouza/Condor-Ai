"""
Testes do Condor — rode antes de confiar numa mudança.

    python testes/rodar_testes.py

Não precisa de chave da OpenAI nem do Picovoice, e não gasta um centavo:
tudo aqui é o que dá pra verificar sem sair do PC. Não mexe no seu banco de
memória de verdade (usa um temporário) e não roda nada destrutivo.

Sai com código 1 se qualquer coisa falhar — dá pra usar em automação.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))

falhas: list[str] = []
total = 0


def checar(condicao: bool, descricao: str, detalhe: str = "") -> None:
    global total
    total += 1
    if condicao:
        print(f"  ok    {descricao}")
    else:
        print(f"  FALHA {descricao}" + (f"  ({detalhe})" if detalhe else ""))
        falhas.append(descricao)


def titulo(texto: str) -> None:
    print(f"\n\033[1m{texto}\033[0m" if sys.stdout.isatty() else f"\n{texto}")


# ══════════════════════════════════════════════════════════════════════
# 1. A trava de segurança
# ══════════════════════════════════════════════════════════════════════

def testar_classificador() -> None:
    from condor.actions.guard import classificar_caminho, classificar_comando

    titulo("TRAVA — comandos que DEVEM pedir senha")
    perigosos = [
        ("format C:", "destruir_sistema"),
        ("diskpart /s script.txt", "destruir_sistema"),
        (r"reg delete HKLM\Software\Teste /f", "destruir_sistema"),
        ("cipher /w:C", "destruir_sistema"),
        ("vssadmin delete shadows /all", "destruir_sistema"),
        (r"Remove-Item C:\ -Recurse -Force", "apagar_massa"),
        (r"Remove-Item -Recurse -Force C:\ ", "apagar_massa"),
        (r"remove-item -path 'C:\' -recurse", "apagar_massa"),
        (r"rm -r C:\ ", "apagar_massa"),
        (r"del /s /q C:\ ", "apagar_massa"),
        (r"Remove-Item -Recurse C:\Windows\System32", "apagar_massa"),
        (r"Remove-Item -Recurse -Force C:\Users\Fulano", "apagar_massa"),
        (r'shutil.rmtree("C:\\")', "apagar_massa"),
        (r"Get-ChildItem C:\ -Recurse | Remove-Item -Force", "apagar_massa"),
        ("shutdown /s /t 0", "desligar"),
        ("Restart-Computer -Force", "desligar"),
        ("Stop-Computer", "desligar"),
        ("Set-MpPreference -DisableRealtimeMonitoring $true", "rede_seguranca"),
        ("netsh advfirewall set allprofiles state off", "rede_seguranca"),
        ("netsh wlan delete profile name=casa", "rede_seguranca"),
        ("Set-NetFirewallProfile -Enabled False", "rede_seguranca"),
    ]
    for comando, esperado in perigosos:
        obtido = classificar_comando(comando)
        checar(obtido == esperado, f"{esperado:<17} {comando[:52]}",
               f"veio {obtido}")

    titulo("TRAVA — uso normal que NÃO pode ser barrado")
    inofensivos = [
        "dir",
        "Get-Process | Sort-Object CPU -Descending",
        "git status",
        "New-Item -ItemType Directory projeto",
        "Stop-Process -Name chrome -Force",
        r"Remove-Item C:\Users\Fulano\Downloads\lixo.txt",
        r"Remove-Item .\build -Recurse -Force",
        r"Remove-Item $env:TEMP\cache -Recurse",
        "Get-ChildItem *.tmp | Remove-Item -Force",
        "python -m pip install requests",
        "Get-Content data\\condor.log -Tail 20",
        "ipconfig /all",
    ]
    for comando in inofensivos:
        obtido = classificar_comando(comando)
        checar(obtido is None, f"livre             {comando[:52]}",
               f"barrou como {obtido}")

    titulo("TRAVA — caminhos")
    caminhos = [
        ("C:\\", False, "destruir_sistema"),
        ("C:\\Windows", False, "destruir_sistema"),
        ("C:\\Windows\\System32", True, "destruir_sistema"),
        (str(Path.home()), True, "apagar_massa"),
        (str(Path.home() / "Downloads"), False, None),
        (str(RAIZ / "data"), False, None),
    ]
    for caminho, recursivo, esperado in caminhos:
        obtido = classificar_caminho(caminho, recursivo)
        checar(obtido == esperado, f"{str(esperado):<17} {caminho}",
               f"veio {obtido}")


def testar_senha() -> None:
    from condor.actions.guard import _senha_confere

    titulo("SENHA — tolerância à transcrição de voz")
    # O Whisper devolve a frase inteira, com pontuação e caixa variada.
    aceitar = ["teste", "Teste.", "teste!", "A senha é teste", "a senha e teste",
               "senha teste", "TESTE", " teste ", "é teste"]
    recusar = ["testes", "outra coisa", "cancelar", "não sei", "", "test"]
    for dito in aceitar:
        checar(_senha_confere(dito, "teste"), f"aceita  {dito!r}")
    for dito in recusar:
        checar(not _senha_confere(dito, "teste"), f"recusa  {dito!r}")


def testar_fluxo_guarda() -> None:
    from condor.actions.guard import Guarda
    from condor.config import carregar_config

    titulo("GUARDA — o fluxo de autorização")
    guarda = Guarda(carregar_config())

    async def rodar() -> None:
        # Sem canal pra perguntar, a ação NÃO pode acontecer.
        checar(not await guarda.autorizar("apagar_massa", "sem canal"),
               "sem canal de senha -> barra (falha fechada)")

        async def certo(motivo, categoria):
            return "a senha é teste"
        guarda.registrar_pedido_senha(certo)
        checar(await guarda.autorizar("destruir_sistema", "format C:"),
               "senha certa -> libera")

        # Segunda vez na mesma categoria reaproveita a janela de 90s.
        vezes = {"n": 0}

        async def contando(motivo, categoria):
            vezes["n"] += 1
            return "teste"
        guarda.registrar_pedido_senha(contando)
        await guarda.autorizar("destruir_sistema", "outro comando")
        checar(vezes["n"] == 0, "mesma categoria em seguida -> não repergunta")

        async def errado(motivo, categoria):
            return "abacaxi"
        guarda.registrar_pedido_senha(errado)
        checar(not await guarda.autorizar("desligar", "shutdown"),
               "senha errada -> barra")

        async def calado(motivo, categoria):
            return None
        guarda.registrar_pedido_senha(calado)
        checar(not await guarda.autorizar("rede_seguranca", "firewall off"),
               "ninguém respondeu -> barra")

    asyncio.run(rodar())


# ══════════════════════════════════════════════════════════════════════
# 2. As ferramentas
# ══════════════════════════════════════════════════════════════════════

def testar_ferramentas() -> None:
    from condor.actions import executor as ex

    titulo("MÃOS — as ferramentas no PC")

    r = ex.executar_powershell("Write-Output 'condor-ok'")
    checar(r["ok"] and "condor-ok" in r["saida"], "powershell responde", r["saida"][:60])

    r = ex.executar_python("print(6 * 7)")
    checar(r["ok"] and "42" in r["saida"], "python executa", r["saida"][:60])

    r = ex.executar_python("nao_existe()")
    checar(not r["ok"] and "NameError" in r["saida"], "python devolve erro de verdade")

    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / "sub" / "arquivo.txt"
        conteudo = "acento: ação, coração, Kauã"
        r = ex.escrever_arquivo(str(alvo), conteudo)
        checar(r["ok"] and alvo.exists(), "escreve arquivo criando a pasta")

        r = ex.ler_arquivo(str(alvo))
        checar(r["saida"] == conteudo, "lê de volta com acento intacto")

        r = ex.escrever_arquivo(str(alvo), "\nmais uma linha", anexar=True)
        r = ex.ler_arquivo(str(alvo))
        checar("mais uma linha" in r["saida"], "anexa sem apagar o que tinha")

        r = ex.listar_pasta(str(Path(tmp) / "sub"))
        checar(r["ok"] and "arquivo.txt" in r["saida"], "lista a pasta")

        r = ex.copiar(str(alvo), str(Path(tmp) / "copia.txt"))
        checar(r["ok"] and (Path(tmp) / "copia.txt").exists(), "copia arquivo")

        r = ex.mover(str(Path(tmp) / "copia.txt"), str(Path(tmp) / "movido.txt"))
        checar(r["ok"] and (Path(tmp) / "movido.txt").exists(), "move arquivo")

        r = ex.deletar(str(alvo))
        checar(r["ok"] and not alvo.exists(), "apaga arquivo")

        r = ex.ler_arquivo(str(alvo))
        checar(not r["ok"], "avisa quando o arquivo não existe")

    r = ex.info_sistema()
    checar(r["ok"] and "CPU" in r["saida"] and "RAM" in r["saida"], "lê o estado da máquina")

    r = ex.listar_janelas()
    checar(r["ok"], "lista as janelas abertas")

    r = ex.escrever_clipboard("condor-clip")
    checar(r["ok"], "escreve no clipboard")
    r = ex.ler_clipboard()
    checar("condor-clip" in r["saida"], "lê do clipboard")


def testar_silencio() -> None:
    import condor.actions.executor as ex
    import condor.session as sessao

    titulo("SILÊNCIO — nada pode piscar na tela")
    CREATE_NO_WINDOW = 0x08000000
    checar(ex.SEM_JANELA == CREATE_NO_WINDOW, "executor usa CREATE_NO_WINDOW")
    checar(ex._startupinfo() is not None, "executor esconde a janela no STARTUPINFO")

    fonte = inspect.getsource(ex._rodar)
    checar("creationflags=SEM_JANELA" in fonte, "todo subprocesso nasce escondido")

    fonte_janela = inspect.getsource(sessao.Sessao._abrir_janela)
    checar("0x08000000" in fonte_janela, "a janela também abre sem console")
    checar("pythonw" in fonte_janela, "a janela roda por pythonw, não python")


# ══════════════════════════════════════════════════════════════════════
# 3. O cérebro
# ══════════════════════════════════════════════════════════════════════

def testar_esquemas() -> None:
    from condor.brain import tools

    titulo("CÉREBRO — as ferramentas declaradas pro modelo")
    nomes = [e["function"]["name"] for e in tools.ESQUEMAS]
    checar(len(nomes) == len(set(nomes)), "nenhum nome de ferramenta duplicado")
    checar(all(len(n) <= 64 and n.replace("_", "").isalnum() for n in nomes),
           "todos os nomes são válidos pra API")
    checar(all(e["function"].get("description") for e in tools.ESQUEMAS),
           "toda ferramenta tem descrição")

    try:
        json.dumps(tools.ESQUEMAS)
        checar(True, "os schemas serializam em JSON")
    except Exception as exc:
        checar(False, "os schemas serializam em JSON", str(exc))

    especiais = {"buscar_memoria"}
    checar(not (set(nomes) - set(tools.FUNCOES) - especiais),
           "toda ferramenta declarada tem implementação")
    checar(not (set(tools.FUNCOES) - set(nomes)),
           "nenhuma implementação órfã")
    checar(not (set(nomes) - set(tools.ROTULOS)),
           "toda ferramenta tem rótulo na interface")

    # O schema tem que bater com a assinatura real da função, senão o modelo
    # manda um argumento que estoura em TypeError na hora de executar.
    divergencias = []
    for esquema in tools.ESQUEMAS:
        f = esquema["function"]
        fn = tools.FUNCOES.get(f["name"])
        if not fn:
            continue
        aceita = set(inspect.signature(fn).parameters)
        declarados = set(f["parameters"]["properties"])
        if declarados - aceita:
            divergencias.append(f"{f['name']}: sobra {declarados - aceita}")
        exigidos = {
            n for n, p in inspect.signature(fn).parameters.items()
            if p.default is inspect.Parameter.empty and n != "contexto"
        }
        if exigidos - declarados:
            divergencias.append(f"{f['name']}: falta {exigidos - declarados}")
    checar(not divergencias, "schema bate com a assinatura das funções",
           "; ".join(divergencias))


def testar_prompt_e_custo() -> None:
    from condor.brain.client import calcular_custo
    from condor.brain.persona import montar_prompt

    titulo("CÉREBRO — prompt e custo")
    p = montar_prompt("Fulano", "- [pessoal] Torce pro Flamengo", modo_voz=True)
    checar("AGORA:" in p, "o prompt carrega a data real (senão ele inventa)")
    checar("ENTRADA POR VOZ" in p, "avisa quando a entrada veio do microfone")
    checar("Flamengo" in p, "a memória relevante entra no prompt")
    checar("Fulano" in p, "ele sabe o nome do dono")
    checar(len(p) < 6000, "o prompt não está gigante", f"{len(p)} chars")

    checar(calcular_custo("gpt-4o", 1_000_000, 0) == 2.50, "preço de entrada do gpt-4o")
    checar(calcular_custo("gpt-4o", 0, 1_000_000) == 10.00, "preço de saída do gpt-4o")
    checar(calcular_custo("modelo-que-nao-existe", 1_000_000, 0) > 0,
           "modelo desconhecido não zera o contador")


def testar_poda() -> None:
    from condor.session import Sessao

    titulo("SESSÃO — poda do histórico")
    s = Sessao.__new__(Sessao)
    s.historico = [{"role": "user", "content": f"m{i}"} for i in range(28)]
    s.historico += [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
        {"role": "tool", "tool_call_id": "b", "content": "ok"},
        {"role": "assistant", "content": "pronto"},
    ]
    s._podar_historico(maximo=6)
    checar(len(s.historico) <= 8, "corta o histórico", f"{len(s.historico)} mensagens")
    # Mensagem 'tool' sem o 'assistant' que a pediu faz a API recusar o pedido.
    checar(s.historico[0]["role"] != "tool", "nunca deixa mensagem de ferramenta órfã")

    s2 = Sessao.__new__(Sessao)
    s2.historico = [{"role": "user", "content": "só uma"}]
    s2._podar_historico(maximo=30)
    checar(len(s2.historico) == 1, "histórico curto passa intacto")


# ══════════════════════════════════════════════════════════════════════
# 4. A memória
# ══════════════════════════════════════════════════════════════════════

def testar_memoria() -> None:
    from condor.memory.db import Memoria

    titulo("MEMÓRIA — banco, busca e grafo")
    with tempfile.TemporaryDirectory() as tmp:
        m = Memoria(Path(tmp) / "teste.db")
        m.inicializar()
        checar(True, "o banco inicializa")

        m.abrir_sessao()
        checar(m.sessao_atual > 0, "abre uma sessão")

        m.salvar_fato("pessoal", "time", "Ele torce pro Flamengo desde criança")
        m.salvar_fato("trabalho", "stack", "Trabalha com Python e PowerShell")
        m.salvar_fato("rotina", "academia", "Treina de manhã, seis da manhã")
        checar(m.estatisticas()["fatos"] == 3, "grava fatos")

        # Chave repetida CORRIGE o fato em vez de duplicar.
        m.salvar_fato("pessoal", "time", "Na verdade torce pro Vasco")
        checar(m.estatisticas()["fatos"] == 3, "fato repetido atualiza, não duplica")
        checar("Vasco" in m.fatos_recentes()[0]["valor"], "a correção prevaleceu")

        achados = m.buscar_fatos("Vasco")
        checar(any("Vasco" in f["valor"] for f in achados), "busca textual (FTS5) acha")

        achados = m.buscar_fatos("academia treino")
        checar(any("Treina" in f["valor"] for f in achados), "acha por outra palavra da frase")

        m.salvar_entidade("Flamengo", "projeto", "PESSOAL", "time")
        m.salvar_entidade("Python", "ferramenta", "TRABALHO", "linguagem")
        m.salvar_relacao("Flamengo", "Python", "ligado_a")
        g = m.grafo()
        checar(len(g["nos"]) == 2 and len(g["arestas"]) == 1, "monta o grafo")

        m.salvar_entidade("Python", "ferramenta", "TRABALHO", "linguagem")
        checar(m.estatisticas()["nos"] == 2, "entidade repetida não duplica")

        m.salvar_turno("user", "e aí condor")
        m.salvar_turno("assistant", "fala")
        h = m.historico(limite=10)
        checar(len(h) == 2 and h[0]["role"] == "user", "histórico volta na ordem certa")

        m.registrar_acao("executar_powershell", "dir", "ok", True)
        m.registrar_acao("deletar", "x.txt", "falhou", False)
        acoes = m.acoes_recentes()
        checar(len(acoes) == 2, "audita as ações")
        checar(sum(1 for a in acoes if not a["sucesso"]) == 1, "distingue falha de sucesso")

        m.registrar_uso("gpt-4o", 1000, 500, 0.0075)
        custo = m.custo_hoje()
        checar(custo["hoje_usd"] > 0 and custo["hoje_tokens"] == 1500, "contabiliza o custo")

        alvo = m.fatos_recentes()[0]["id"]
        checar(m.esquecer_fato(alvo), "esquece um fato")
        checar(m.estatisticas()["fatos"] == 2, "o fato sumiu mesmo")

        m.fechar_sessao("resumo de teste")
        checar(m.sessao_atual == 0, "fecha a sessão")


def testar_embedding() -> None:
    from condor.memory.db import _desempacotar, _empacotar, _similaridade

    titulo("MEMÓRIA — embeddings")
    vetor = [0.1, -0.25, 0.7, 0.0, 0.33]
    volta = _desempacotar(_empacotar(vetor))
    checar(all(abs(a - b) < 1e-6 for a, b in zip(vetor, volta)),
           "o vetor sobrevive à ida e volta pro banco")
    checar(abs(_similaridade([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-6, "vetor igual = 1.0")
    checar(abs(_similaridade([1, 0, 0], [0, 1, 0])) < 1e-6, "vetor ortogonal = 0.0")
    checar(_similaridade([1, 0], []) == 0.0, "vetor vazio não estoura")
    checar(_similaridade([1, 0], [1, 0, 0]) == 0.0, "tamanho diferente não estoura")


# ══════════════════════════════════════════════════════════════════════

def main() -> int:
    print("=" * 68)
    print("  TESTES DO CONDOR")
    print("=" * 68)

    testar_classificador()
    testar_senha()
    testar_fluxo_guarda()
    testar_ferramentas()
    testar_silencio()
    testar_esquemas()
    testar_prompt_e_custo()
    testar_poda()
    testar_memoria()
    testar_embedding()

    print("\n" + "=" * 68)
    if falhas:
        print(f"  {total - len(falhas)}/{total} passaram — {len(falhas)} FALHA(S):")
        for f in falhas:
            print(f"    - {f}")
        print("=" * 68)
        return 1
    print(f"  {total}/{total} passaram. Tudo certo.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
