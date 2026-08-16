# Como usar o Condor

## Primeiro acesso

1. Execute o instalador correspondente ao PC.
2. Abra o atalho **Condor** criado na Area de Trabalho ou no menu de aplicativos.
3. O aplicativo abre diretamente a interface completa em uma janela propria.
   O Hub em `http://127.0.0.1:7777/hub/index.html` inclui um assistente Condor
   para criar atividades e abrir sistemas, mas nao recebe memoria, arquivos ou
   acoes do PC.
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

- **Hub:** o Condor organiza atividades e abre os sistemas ARTX. Ele nao altera
  o PC e nao recebe a memoria local.
- **Aplicativo Condor:** conversa, voz, memoria, projetos e diagnostico. E a
  unica interface operacional do computador.
- **Projetos:** mostra o catalogo local. Ao abrir um card, o aplicativo exibe
  a ficha completa daquele projeto, suas informacoes e seu prototipo. O Condor
  X e o primeiro projeto cadastrado.
- **Acesso:** depois da frase correta, o perfil completo do dono e ativado
  automaticamente. Nao existe seletor de autonomia.

## Modos de uso

- Sem chaves: comandos locais deterministas, data/hora, informacoes do sistema,
  consulta de memoria e arquivos permitidos.
- Com conector de IA: conversa e planejamento com ferramentas limitadas pela
  politica local.
- Com voz local: clique no orbe, fale e clique novamente. Faster Whisper e
  Piper processam tudo no PC. A ativacao passiva por palavra e opcional; se for
  configurada, exige um modelo `condor*.ppn` e nao aceita nome alternativo.

## Seguranca pratica

- Nenhuma ferramenta do PC funciona antes da frase secreta ser validada.
- Depois da entrada, a sessao do dono opera sem pedir a frase a cada acao.
- Voz nunca desbloqueia a sessao nem retoma o interruptor de emergencia.
- `PARAR CONDOR` bloqueia imediatamente todas as ferramentas.
- Para retomar, e obrigatorio digitar a frase secreta.
- Exclusoes feitas pelo assistente vao para `~/.condor/trash`.
- Alteracoes em arquivos existentes criam versoes em `~/.condor/versions`.

O perfil e sempre `admin` para a sessao autenticada, mas continua limitado ao
catalogo de ferramentas especificas e as pastas autorizadas. Shell arbitrario,
Python arbitrario e instalacao livre de pacotes permanecem bloqueados. As
pastas iniciais permitidas sao Desktop, Documents, Downloads e a propria pasta
do codigo. Isso pode ser ajustado em
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

Nao exponha a porta 7777 na rede. O nucleo completo permanece no loopback.

## Ver no celular sem instalar aplicativo

1. Deixe o PC e o celular conectados a mesma rede Wi-Fi privada.
2. Abra o aplicativo Condor no PC e clique em **CELULAR**.
3. No navegador do celular, digite o endereco mostrado pelo Condor.
4. Digite o codigo de oito numeros exibido no PC.

O endereco da porta `7778` e um espelho separado e somente leitura. Ele mostra
estado tecnico e projetos, incluindo o prototipo 3D, mas nao oferece conversa,
memoria, arquivos, senha, cofre nem controle do PC. O codigo muda quando o
nucleo do Condor reinicia e cinco erros de pareamento bloqueiam novas tentativas
por dez minutos.

Para visualizar fora da mesma rede, siga `deploy/wireguard/README.md` e mantenha
o nucleo em loopback. Nunca encaminhe a porta `7777` pelo roteador.
