# 🦅 CONDOR

Assistente pessoal com acesso total ao seu PC. Fica dormindo no fundo do
Windows até você chamar pelo nome. Aí ele acorda, escuta, resolve e volta a
dormir sozinho.

Cérebro: **GPT-4o** (API da OpenAI).
Memória: **SQLite na sua máquina** — ele aprende sobre você e nunca esquece.

---

## Como funciona no dia a dia

```
   DORMINDO ──── você fala "Condor, ..." ────► ACORDADO
      ▲                                            │
      └────────── 2 min sem te ouvir ──────────────┘
```

1. Ele fica ouvindo o microfone o tempo todo, **localmente**, esperando a
   palavra de chamada. Dormindo não gasta um centavo de API.
2. Você fala **"Condor"** e emenda o pedido. Ele grava até você parar de falar.
3. A janela abre, ele pensa, age no PC se precisar e responde falando.
4. Passados 2 minutos sem você chamar de novo, a janela fecha e ele dorme.

Todo pedido começa chamando o nome dele. É isso que separa "estou falando com
o Condor" de "estou falando na sala".

---

## O que ele faz no PC

Acesso total, de verdade. Nenhuma janela preta piscando na tela — todo
processo filho nasce escondido.

| | |
|---|---|
| **Shell** | qualquer comando PowerShell |
| **Código** | executa Python na hora |
| **Arquivos** | ler, escrever, criar, mover, copiar, apagar, procurar no PC inteiro |
| **Programas** | abrir, fechar, listar e trazer janelas pra frente |
| **Tela** | tira print e **enxerga** o que tem nela |
| **Mouse e teclado** | clicar, digitar, atalhos |
| **Web** | buscar e ler páginas |
| **Sistema** | CPU, RAM, disco, bateria, processos |
| **Memória** | consultar tudo que já aprendeu sobre você |

---

## A única trava

Ele faz tudo sozinho, sem pedir licença. **Exceto** quatro coisas, que exigem
sua senha falada em voz alta:

- destruir o sistema (`format`, `diskpart`, apagar o registro)
- apagar arquivos em massa (remoção recursiva de pasta grande ou raiz de disco)
- desligar ou reiniciar o PC
- mexer em firewall, antivírus ou redes salvas

Ele fala *"isso vai apagar arquivos em massa, me diz a senha"*, você responde
falando (ou digita na janela). Errou ou ficou quieto, a ação não acontece.

Toda ação — liberada ou barrada — fica registrada em `data/auditoria.log`.

Senha inicial: `teste`. Troque em `.env` (`CONDOR_SENHA`).

---

## Memória

Ele aprende sozinho. Depois de cada conversa, um modelo barato relê o que foi
dito e decide o que vale guardar pra sempre: quem você é, no que trabalha, o
que prefere, sua rotina, seus projetos, o que vocês combinaram.

Nada disso é regra fixa — é julgamento do modelo, e por isso não enche o banco
de lixo.

Guardado em `data/condor.db` (SQLite, na sua máquina):

| tabela | o que é |
|---|---|
| `fatos` | o que ele sabe sobre você, com busca por texto e por significado |
| `entidades` / `relacoes` | pessoas, projetos e lugares, e como se ligam (o grafo da tela Memória) |
| `conversas` | histórico completo, por sessão |
| `acoes` | auditoria de tudo que ele rodou no PC |
| `uso_api` | quanto cada chamada custou |

---

## Instalação

Veja **[COMO_USAR.md](COMO_USAR.md)** — passo a passo, do zero, incluindo como
pegar a chave da OpenAI e como treinar a palavra "Condor".

Resumo:

```bash
pip install -r requirements.txt
```

Preencha o `.env`, depois dois cliques em `condor_launcher.pyw`.

---

## Estrutura

```
condor/
├── config.py          configuração (data/config.yaml + .env)
├── session.py         o ciclo dormir/acordar
├── server.py          FastAPI + WebSocket
├── brain/
│   ├── client.py      OpenAI: streaming e loop de ferramentas
│   ├── tools.py       as 26 ferramentas que o modelo pode chamar
│   └── persona.py     quem ele é
├── actions/
│   ├── executor.py    as mãos: shell, arquivos, mouse, tela, web
│   └── guard.py       a trava por senha + auditoria
├── memory/
│   ├── db.py          SQLite com FTS5 e embeddings
│   ├── recall.py      o que entra na conversa
│   └── extractor.py   o que vale guardar pra sempre
├── voice/
│   ├── wake.py        a escuta local sempre ligada
│   ├── stt.py         transcrição
│   └── tts.py         a voz dele
└── ui/                a interface (HUD)
```

---

## Privacidade — leia

A versão antiga rodava um modelo local e nada saía do PC. **Esta não.**

Vai pra OpenAI: o que você fala depois de chamar ele, as respostas, e os fatos
da memória que forem relevantes pro pedido (entram como contexto).

**Não** vai: o áudio enquanto ele está dormindo (o detector é local), nem o
conteúdo do seu PC que ele não precisou abrir pra te responder.

Seu banco de memória, os logs e a auditoria ficam só na sua máquina.

---

## Custo

Você paga por uso à OpenAI. O contador na tela mostra o gasto do dia.
Dormindo, o custo é zero — é por isso que a sessão fecha sozinha.
