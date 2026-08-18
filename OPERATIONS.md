# Operacao local

## Componentes

- `127.0.0.1:7777`: Condor, ARTX Hub e APIs privadas no mesmo processo;
- `127.0.0.1:11434`: Ollama local, nunca exposto pelo Condor;
- `qwen3:4b-instruct`: conversa e ferramentas;
- `qwen3-vl:2b`: leitura local de capturas autorizadas;
- Faster Whisper small: fala para texto em CPU;
- Piper `pt_BR-faber-medium`: texto para voz em CPU;
- `~/.condor`: configuracao, pesos e estado privado.

O Hub e exportado como arquivos estaticos e montado em `/hub`. A aba Condor do
Hub organiza atividades, mas nao recebe controle operacional do PC. O aplicativo
Condor abre `/ui` em uma janela propria; apenas essa interface oferece conversa,
memoria e ferramentas locais. O cookie de sessao e HttpOnly e vale para as duas
interfaces porque elas usam a mesma origem local.

## Comandos

```powershell
.\scripts\build_hub.ps1
.\scripts\run.ps1
.\scripts\install_app_shortcut.ps1
.\.venv\Scripts\python.exe .\scripts\doctor.py
.\scripts\install_autostart.ps1
```

```bash
sh scripts/build_hub.sh
sh scripts/run.sh
sh scripts/install_app_shortcut.sh
.venv/bin/python scripts/doctor.py
sh scripts/install_autostart.sh
```

O instalador de inicializacao do Windows cria apenas um atalho no Startup do
usuario. No Linux, cria um servico systemd do usuario. Nenhum dos dois exige
conta de nuvem.

## Recuperacao

O pedido de remover os dados antigos sem backup foi mantido: o Condor nao cria
uma copia externa automatica. O codigo pode ser reinstalado pelos scripts e os
modelos podem ser baixados novamente. O cofre e a memoria cifrada so podem ser
recuperados com uma copia feita conscientemente pelo dono e a frase secreta.

Em um notebook Windows novo, baixe o repositorio privado e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_new_windows_pc.ps1
```

Esse fluxo restaura o programa e os modelos, mas cria um estado privado vazio.
Para manter memoria e configuracoes antigas, transporte `~/.condor` somente por
um meio cifrado e nunca inclua essa pasta no repositorio.

Nao abra as portas 7777 ou 11434 no roteador. WireGuard somente sera ativado
quando existir outro equipamento proprio e houver autorizacao para gerar as
chaves nesse equipamento.
