# Modelo de seguranca do Condor

## Fronteiras

O modelo de IA e tratado como planejador nao confiavel. Ele nao ganha shell,
Python arbitrario, instalacao de pacotes nem poder de mudar a propria politica.
Cada ferramenta passa por uma decisao deterministica local.

Dados privados em repouso usam AES-256-GCM. A frase do dono e verificada por
Scrypt e nao e armazenada. A identidade do dispositivo usa Ed25519. A auditoria
forma uma cadeia SHA-256 e o codigo tem um manifesto assinado.

## Sessao autenticada do dono

Antes da frase secreta correta, nenhuma ferramenta do computador e liberada.
Depois da autenticacao, o perfil operacional do dono permanece ativo ate o
bloqueio, a parada de emergencia ou o encerramento do servidor. A sessao aplica
o perfil e o modo de simulacao gravados no `config.yaml`; ela nao reescreve essa
escolha. O modelo nao consegue ativar essa sessao. Captura de voz nunca
desbloqueia nem retoma o Condor.

A politica classifica o risco, limita pastas e bloqueia shell, Python e
instalacao arbitrarios. Um conjunto de ferramentas continua exigindo a frase
secreta mesmo com a sessao aberta, porque o planejador le conteudo nao confiavel
da internet e uma instrucao escondida numa pagina nao pode virar arquivo gravado
sem o dono ver: `escrever_arquivo`, `deletar`, `mover`, `baixar` e `fechar_app`
(lista em `condor/actions/guard.py`, `SEMPRE_CONFIRMA`). As demais operacoes do
catalogo passam direto durante a sessao. Exclusoes continuam recuperaveis pela
lixeira privada e alteracoes de arquivo mantem versoes locais.

A trava de pastas usa uma unica funcao de resolucao (`condor.paths.resolver_alvo`)
para a politica e para o executor. Enquanto cada lado normalizava por conta
propria, `%USERPROFILE%` e `%APPDATA%` escapavam do sandbox.

## Rede

O servidor aceita somente `127.0.0.1`, `localhost` ou `::1`. Requisicoes exigem
cookie HttpOnly aleatorio com validade de quatro horas, origem local exata e Host
local. Isso bloqueia inclusive ataques entre portas diferentes do loopback.
WebSocket aplica as mesmas regras, aceita no maximo quatro conexoes e limita
tamanho e frequencia das mensagens.

A primeira sessao de cada execucao exige um segredo de boot gravado em
`~/.condor/security/ui-token`, que a janela do Condor le do disco e envia em
`X-Condor-Token`. Cabecalho de identidade da interface e forjavel por qualquer
programa da maquina; ler um arquivo do perfil do dono, nao. O Hub em `/hub`
renova a sessao apresentando o cookie ja estabelecido, sem precisar do arquivo.
Isso protege contra outro processo abrir sessao sozinho e ler a memoria; nao
protege contra codigo malicioso rodando com a mesma conta de usuario, que le o
arquivo do mesmo jeito.

Requisicoes de API tem limite de tamanho, frequencia de leitura e frequencia de
escrita. Tentativas de frase secreta recebem espera exponencial de ate cinco
minutos. A politica de conteudo bloqueia scripts externos, objetos, formularios
fora da origem e captura de tela, camera, USB, serial e Bluetooth pelo navegador.
Respostas privadas nunca sao armazenadas em cache nem indexadas.

STT, TTS e visao usam modelos locais. O push-to-talk envia o audio apenas para
`127.0.0.1`; capturas de tela continuam passando pela politica local antes de
serem analisadas. Voz e imagem nunca aprovam operacoes sensiveis.

Fatos antigos da memoria e aprendizado automatico por conector ficam desligados
por padrao. Assim, o historico cifrado nao e anexado a chamadas externas sem uma
escolha consciente no arquivo de configuracao.

Leituras e downloads web rejeitam localhost, rede privada, enderecos reservados
e redirecionamentos para esses destinos. A recusa acontece com o socket ja
conectado, olhando o endereco real do outro lado — nao numa consulta DNS feita
antes, que um servidor hostil poderia responder diferente na hora da conexao
(DNS rebinding). Downloads tem limite de 100 MB.

Instaladores de executaveis usam releases fixadas, checksum SHA-256 conhecido e
validacao Authenticode antes de copiar qualquer binario para o runtime. Modelos
baixados diretamente tambem usam hashes fixos; conteudo XML vindo da internet e
processado por um parser que bloqueia entidades externas e expansoes perigosas.
O launcher `Condor.exe` e compilado localmente a partir do codigo C# versionado;
o repositorio nao distribui um executavel do Condor sem assinatura de publicador.

## Execucao local e parada de emergencia

Ferramentas nao recebem shell arbitrario. Nomes de aplicativo e janela aceitam
somente caracteres controlados; no Windows os valores atravessam variaveis de
ambiente, sem interpolacao no PowerShell. Fechamento de aplicativo compara o
nome exato do processo por uma biblioteca portavel.

Teclado sintetizado contorna qualquer trava de arquivo, entao as combinacoes que
abrem lancador de comando ficam bloqueadas: tecla Windows sozinha, `win+r`,
`win+s`, `win+q`, `win+x`, `win+i`, `win+u` e `ctrl+shift+esc`. Atalhos comuns
como `win+d`, `alt+tab` e `ctrl+c` seguem disponiveis. Isto fecha o caminho
curto; digitacao em uma janela ja aberta pelo dono continua sendo possivel.

A auditoria e ancorada: o ultimo hash da cadeia e a contagem de eventos ficam
assinados com a chave Ed25519 do dispositivo, que mora no cofre cifrado. O
encadeamento sozinho revelava edicao no meio do arquivo, mas nao revelava o log
ser apagado e reconstruido do zero. Eventos gravados com o cofre bloqueado nao
podem ser assinados na hora; a ancora prova o prefixo ate o ponto assinado e o
encadeamento cobre o resto.

O interruptor de emergencia encerra voz e sessao, silencia o microfone, bloqueia
a memoria e fecha o cofre. Retomar exige a frase do dono e mantem o cofre
bloqueado ate um novo desbloqueio consciente.

## O que ainda depende do dono

- usar uma frase longa e unica;
- manter o sistema e Python atualizados;
- revisar dependencias antes de atualizar versoes principais;
- nao liberar a porta 7777 no roteador ou firewall;
- verificar o alerta de integridade depois de qualquer atualizacao legitima;
- manter uma copia cifrada da pasta `~/.condor` se desejar recuperacao.

O pedido de apagar o banco antigo sem backup foi respeitado. Isso remove os
arquivos no nivel do sistema de arquivos; nao promete apagamento forense dos
blocos fisicos de SSD.
