# Condor 2.0

Condor e um assistente pessoal local, portavel e controlado pelo proprio dono.
O mesmo codigo roda em Windows e Linux; configuracoes e dados privados ficam em
`~/.condor` (ou no caminho definido por `CONDOR_HOME`). O nucleo nao usa conta
Microsoft, celular, nuvem obrigatoria nem servico de login externo.

## O que esta pronto

- servidor FastAPI apenas em `127.0.0.1`, protegido por sessao local e politica
  de origem;
- interface local autocontida, sem CDN;
- cofre AES-256-GCM com chave derivada por Scrypt;
- memoria SQLite somente em RAM durante o uso e snapshot cifrado em disco;
- identidade Ed25519 propria do dispositivo;
- manifesto assinado para detectar alteracoes no codigo;
- auditoria encadeada por hash;
- perfil operacional unico depois da autenticacao e pastas permitidas;
- sessao do dono bloqueada ate a palavra de acesso ser validada;
- interruptor de emergencia;
- exclusao recuperavel pela lixeira privada do Condor;
- ferramentas de shell, Python arbitrario e instalacao automatica fora do
  catalogo da IA;
- modo local deterministico quando nenhuma IA estiver conectada;
- conector generativo local por loopback, sem login externo, para qualquer
  servidor compativel com a Responses API;
- ARTX Hub original servido localmente em `/hub`, mantendo Site, Videos, SAT e
  University Path independentes;
- aba Condor no Hub como assistente de organizacao, capaz de criar atividades
  e abrir os sistemas ARTX, sem receber memoria, arquivos ou acoes do PC;
- aplicativo Condor em janela propria, aberto pelo atalho do sistema e com
  conversa, memoria, projetos e diagnostico, sem seletor de autonomia;
- inicializador nativo no Windows com a identidade `ARTX.Condor.Local`, logo
  propria no executavel, no Menu Iniciar, no atalho e na barra de tarefas;
- visualizacao movel separada na porta `7778`, restrita a rede privada,
  pareada por codigo e limitada a estado sanitizado e projetos somente leitura;
- aba **Projetos** como catalogo local: cada card abre sua propria ficha com
  informacoes e prototipo; o Condor X e o primeiro projeto, com digital twin
  corporal clicavel e modelador 3D parametrico em cada regiao;
- editor de malha organica com comprimento, largura, profundidade, espessura,
  folga, assimetria e torcao; pontos tecnicos, historico cifrado de versoes e
  exportacao STL funcionam localmente;
- campos numericos preservam as medidas exatas em milimetros; **Salvar no Corpo
  X** versiona a regiao e recompõe o corpo 3D completo com a nova geometria;
- cabeca, maos, ombros e pes usam geradores proprios: cranio com mandibula,
    palma com cinco dedos, deltoide continuo e pe fechado inspirado em tenis,
    com bico arredondado, peito do pe inclinado e sola continua;
- a montagem visual usa carenagem branca perolada continua e juntas grafite,
  sem placas 3D sobrepostas, mantendo cada zona selecionavel;
- voz privada com Faster Whisper e Piper, incluindo push-to-talk no navegador;
- visao privada com `qwen3-vl:2b` para capturas autorizadas;
- conectores selecionaveis **OpenAI**, **Claude** e **Local**; chaves externas
  ficam no cofre, OpenAI usa Responses API com `store=false` e Claude usa a
  Messages API oficial;
- pesquisa atual pela ferramenta hospedada `web_search` da Responses API,
  com URLs citadas extraidas e exibidas como fontes clicaveis na conversa;
- fallback publico local para busca e leitura de paginas, com bloqueio de
  loopback/LAN, redirecionamentos privados, consultas contendo segredo e
  resultados sem relacao suficiente com a pesquisa;
- memoria unica do Condor obrigatoria para OpenAI, Claude e Local: conversas e
  fatos continuam no banco cifrado local e so o contexto relevante entra no pedido;
- orquestrador interno da IA ligado a Projetos, Programacao, Laboratorio,
  Memoria e Device Bridge; chat e voz usam o mesmo contexto e as mesmas
  permissoes, sem shell ou Python arbitrario;
- buffer de codigo versionado e recuperavel: alteracoes feitas pelo dono ou
  pela IA criam revisoes no snapshot cifrado antes de substituir o estado atual;
- fluxo Arduino real na aba **Programacao**: seleciona porta e placa, salva o
  buffer, compila com Arduino CLI e somente grava/verifica quando a compilacao
  termina sem erro; o alvo fisico exige confirmacao visual no botao **RUN**;
- palavra de ativacao passiva opcional e exclusivamente **Condor**; o clique no
  orbe funciona sem chave ou conta externa.

## Limites honestos

O Condor e independente na identidade, memoria, politica, interface, voz,
visao e execucao. Os modelos instalados neste PC funcionam sem internet depois
do download inicial. Sem um modelo generativo, o modo deterministico continua
disponivel.

Para um modelo no proprio PC, configure em `~/.condor/config.yaml`:

```yaml
cerebro:
  endpoint_local: http://127.0.0.1:11434/v1
  modelo_local: nome-do-modelo-instalado
```

No modo `auto`, quando `modelo_local` esta preenchido, o conector local tem
prioridade sobre a chave externa. O servidor local escolhido precisa implementar
a Responses API. Em **Sistema > Conectar IA**, o dono pode selecionar
explicitamente OpenAI, Claude ou Local, manter modelos separados e testar todos
os conectores configurados sem editar o arquivo manualmente. O painel mostra
configurado, aguardando teste, conectado ou falha para cada provedor; qualquer
falha tambem aparece em **Diagnostico**.
Neste PC, o perfil validado usa `qwen3:4b-instruct` e `qwen3-vl:2b`; os pesos ficam em
`~/.condor/models`, fora do repositorio e sob controle local.

### Conectar APIs externas

Abra **Sistema > Conectar IA**, selecione **OpenAI**, **Claude** ou **Local**,
escolha o modelo nas listas fechadas e cole somente a chave do provedor desejado.
Como o dono ja entrou no Condor, nenhuma segunda confirmacao aparece nessa tela.
As chaves entram diretamente no cofre local
cifrado, nunca aparecem novamente na interface e nao devem ser enviadas ao chat
nem ao GitHub. O botao **Salvar e testar** valida todos os conectores configurados
antes de mostrar o provedor selecionado como conectado.

OpenAI, Claude e Local usam a mesma memoria do Condor. Conversas e fatos duraveis
ficam no banco cifrado local; o conector recebe apenas os trechos relacionados ao
pedido atual, nunca o banco inteiro. A pesquisa web nao vira
automaticamente memoria pessoal, e segredos, chaves, tokens e senhas sao
rejeitados antes da gravacao.

Quando a pergunta depende de informacao atual ou verificavel, o Condor pesquisa,
prioriza fontes primarias, compara fontes importantes e mantem tres origens
separadas na resposta: memoria pessoal, internet e inferencia. Links consultados
aparecem abaixo da mensagem e nao sao lidos em voz alta.

O clique para falar funciona com o STT/TTS local. A ativacao passiva pela palavra
**Condor** exige a chave Picovoice e um arquivo de palavra-chave `condor*.ppn`;
a chave tambem pode ser guardada em **Conectar IA**.

O nucleo completo continua escutando somente no proprio computador, em
`127.0.0.1:7777`. A visualizacao opcional do celular usa outro servidor em
`7778`, sem rotas de comando, memoria, arquivos ou cofre. Para acesso fora da
mesma rede Wi-Fi, use o modelo em `deploy/wireguard`; nunca publique a porta
`7777` na internet.

## Instalar

Requer Python 3.11 ou superior.

### Notebook Windows novo

1. Entre na sua conta do GitHub e baixe o repositorio privado
   `Kauadsouza/Condor-Ai` como ZIP ou clone com Git.
2. Extraia o ZIP em uma pasta permanente.
3. Abra o PowerShell nessa pasta e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_new_windows_pc.ps1
```

Esse instalador unico cria o ambiente Python, instala as dependencias, o Arduino
CLI com suporte oficial a placas AVR, baixa os modelos locais de voz, conversa
e visao, executa os testes e cria o atalho
**Condor** na Area de Trabalho. Os downloads iniciais sao grandes; depois disso,
o Condor pode usar os modelos sem internet.

O repositorio recupera o aplicativo, mas nao contem a pasta privada
`~/.condor`, a palavra de acesso, memoria, configuracoes de camera nem chaves. Em um
notebook novo, o primeiro acesso cria um cofre vazio. Para preservar o estado
antigo, copie `~/.condor` separadamente usando um armazenamento cifrado sob seu
controle; nunca envie essa pasta ao GitHub.

### Instalacao manual no Windows

```powershell
.\scripts\install.ps1
.\scripts\install_local_ai.ps1
.\scripts\install_arduino_cli.ps1
# Em outro terminal, apenas se o modelo ainda nao estiver instalado:
.\scripts\run_local_ai.ps1
.\scripts\pull_local_model.ps1
# Depois, o comando abaixo inicia Condor e a IA local juntos:
.\scripts\run.ps1
```

O instalador cria o atalho **Condor** na Area de Trabalho. Ele inicia o nucleo
local quando necessario e abre diretamente o aplicativo, sem passar pelo Hub.
O modelo local abre somente no proprio PC, com contexto de 32 mil tokens; o
diagnostico final exige uma resposta real do modelo antes de aprovar a instalacao.

Linux:

```bash
bash scripts/install.sh
# Em outro terminal, apenas se o modelo ainda nao estiver instalado:
bash scripts/run_local_ai.sh
bash scripts/pull_local_model.sh
# Depois, o comando abaixo inicia Condor e a IA local juntos:
bash scripts/run.sh
```

O instalador cria **Condor** no menu de aplicativos Linux e, quando existir,
na pasta Desktop.

No primeiro acesso, crie uma palavra de acesso com pelo menos 12 caracteres. Nao
existe recuperacao por Microsoft, Google, celular ou por uma empresa externa.
Guarde essa palavra fora do PC.

## Testar

```powershell
.\.venv\Scripts\python.exe testes\rodar_testes.py
```

ou, no Linux:

```bash
.venv/bin/python testes/rodar_testes.py
```

Os testes nao usam microfone, tela, rede nem API paga.

## Estado privado

Estrutura padrao:

```text
~/.condor/
  config.yaml
  security/vault.json
  security/owner.json
  security/code-manifest.json
  memory/condor.memory.enc
  audit/actions.jsonl
  trash/
  versions/
  logs/
  wake/condor*.ppn
```

Para usar um volume proprio:

```powershell
$env:CONDOR_HOME = "D:\MeuCofre\Condor"
```

```bash
export CONDOR_HOME="/mnt/meu-cofre/condor"
```

Veja [SECURITY.md](SECURITY.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[COMO_USAR.md](COMO_USAR.md), [OPERATIONS.md](OPERATIONS.md) e
[CONDOR_X.md](CONDOR_X.md).
