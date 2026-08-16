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
- perfis de autonomia, simulacao e pastas permitidas;
- aprovacoes sensiveis exatas, digitadas, temporarias e de uso unico;
- interruptor de emergencia;
- exclusao recuperavel pela lixeira privada do Condor;
- ferramentas de shell, Python arbitrario e instalacao automatica fora do
  catalogo da IA;
- modo local deterministico quando nenhuma IA estiver conectada;
- conector generativo local por loopback, sem login externo, para qualquer
  servidor compativel com a Responses API;
- ARTX Hub original servido localmente em `/hub`, mantendo Site, Videos, SAT e
  University Path independentes;
- aba exclusiva do Condor dentro do Hub como demonstracao limitada, sem acesso
  a conversa, memoria, arquivos ou acoes do PC;
- aplicativo Condor em janela propria, aberto pelo atalho do sistema e com
  conversa, memoria, projetos, diagnostico e controle local de autonomia;
- Condor X como unico projeto atual do laboratorio, com digital twin 3D e
  modulos corporais clicaveis;
- voz privada com Faster Whisper e Piper, incluindo push-to-talk no navegador;
- visao privada com `qwen3-vl:2b` para capturas autorizadas;
- conector opcional pela Responses API, sempre com `store=false`;
- memoria antiga e aprendizado por conector desligados por padrao, para fatos
  pessoais nao sairem do PC sem escolha explicita;
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

Quando `modelo_local` esta preenchido, o conector local tem prioridade sobre a
chave externa. O servidor local escolhido precisa implementar a Responses API.
Neste PC, o perfil validado usa `qwen3:4b-instruct` e `qwen3-vl:2b`; os pesos ficam em
`~/.condor/models`, fora do repositorio e sob controle local.

VPN nao aumenta a seguranca de um programa que roda em um unico PC. Por isso,
esta versao escuta somente no proprio computador. A pasta `deploy/wireguard`
deixa a ligacao privada preparada para quando existir um segundo computador ou
servidor que tambem seja seu.

## Instalar

Requer Python 3.11 ou superior.

Windows (PowerShell):

```powershell
.\scripts\install.ps1
.\scripts\install_local_ai.ps1
# Em outro terminal, apenas se o modelo ainda nao estiver instalado:
.\scripts\run_local_ai.ps1
.\scripts\pull_local_model.ps1
# Depois, o comando abaixo inicia Condor e a IA local juntos:
.\scripts\run.ps1
```

O instalador cria o atalho **Condor** na Area de Trabalho. Ele inicia o nucleo
local quando necessario e abre diretamente o aplicativo, sem passar pelo Hub.

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

No primeiro acesso, crie uma frase secreta com pelo menos 12 caracteres. Nao
existe recuperacao por Microsoft, Google, celular ou por uma empresa externa.
Guarde essa frase fora do PC.

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
