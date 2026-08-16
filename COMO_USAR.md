# Como usar o Condor

## Primeiro acesso

1. Execute o instalador correspondente ao PC.
2. Abra o atalho **Condor** criado na Area de Trabalho ou no menu de aplicativos.
3. O aplicativo abre diretamente a interface completa em uma janela propria.
   O Hub em `http://127.0.0.1:7777/hub/index.html` e apenas uma demonstracao
   limitada, sem conversa, memoria, arquivos ou acoes do PC.
4. Crie o cofre com seu nome e uma frase secreta exclusiva.
5. Chaves externas sao opcionais e ficam cifradas no cofre.

Se quiser conhecer o visual antes disso, use `VER A INTERFACE PRIMEIRO`. Esse
modo e somente uma previa: conversa, memoria e acoes continuam bloqueadas ate o
cofre ser criado. O aviso no topo permite voltar para a configuracao.

Neste PC, a IA local ja foi validada com `qwen3:4b-instruct`. Depois da primeira
instalacao, `scripts/run.ps1` inicia o Condor e a IA local juntos. No Linux, use
`scripts/run.sh` e um Ollama instalado localmente.

O Condor nunca pede conta do Windows nem vinculacao com celular.

## Hub e aplicativo

- **Hub:** mostra a identidade, o laboratorio e o digital twin do Condor X.
  Seus controles sao demonstrativos e nao alteram o PC.
- **Aplicativo Condor:** conversa, voz, memoria, projetos, diagnostico e
  controle de autonomia. E a unica interface operacional.
- **Controle local:** dentro do aplicativo, escolha observador, assistente,
  operador ou administrador. A mudanca exige a frase secreta.

## Modos de uso

- Sem chaves: comandos locais deterministas, data/hora, informacoes do sistema,
  consulta de memoria e arquivos permitidos.
- Com conector de IA: conversa e planejamento com ferramentas limitadas pela
  politica local.
- Com voz local: clique no orbe, fale e clique novamente. Faster Whisper e
  Piper processam tudo no PC. A ativacao passiva por palavra e opcional; se for
  configurada, exige um modelo `condor*.ppn` e nao aceita nome alternativo.

## Seguranca pratica

- Acoes de alteracao pedem a frase secreta na interface.
- Voz nunca aprova acao sensivel.
- `PARAR CONDOR` bloqueia imediatamente todas as ferramentas.
- Para retomar, e obrigatorio digitar a frase secreta.
- Exclusoes feitas pelo assistente vao para `~/.condor/trash`.
- Alteracoes em arquivos existentes criam versoes em `~/.condor/versions`.

Perfis:

- `observer`: observa; nao altera o PC.
- `assistant`: revisa leituras e confirma alteracoes.
- `operator`: leituras permitidas fluem; alteracoes continuam confirmadas.
- `admin`: maior autonomia dentro das capacidades especificas; operacoes
  criticas continuam confirmadas e shell arbitrario continua bloqueado.

O padrao e `assistant`. As pastas iniciais permitidas sao Desktop, Documents,
Downloads e a propria pasta do codigo. Isso pode ser ajustado em
`~/.condor/config.yaml` com o Condor fechado.

## Trocar de Windows para Linux

1. Copie o repositorio do Condor.
2. Copie a pasta privada `~/.condor` por um meio cifrado sob seu controle.
3. Instale no Linux com `bash scripts/install.sh`.
4. Inicie com `bash scripts/run.sh` e use a mesma frase secreta.

O instalador Linux tambem cria o aplicativo **Condor** no menu do ambiente
grafico e, quando existir, na pasta Desktop.

Os dados nao dependem do Registro do Windows, Credential Manager, DPAPI ou
conta Microsoft. Integracoes de interface grafica variam por sistema: abrir
arquivos e aplicativos e portatil; focar uma janela especifica exige um
adaptador do ambiente grafico instalado.

## VPN

Nao exponha a porta 7777 na rede. Enquanto o Condor estiver em um PC so, deixe
o servidor no loopback. Quando houver outro equipamento seu, siga o modelo em
`deploy/wireguard/README.md` e mantenha a aplicacao no loopback ou em um proxy
local autenticado dentro do tunel.
