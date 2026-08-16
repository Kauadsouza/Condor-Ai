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
Depois da autenticacao, o perfil operacional unico do dono permanece ativo ate
o bloqueio, a parada de emergencia ou o encerramento do servidor. O modelo nao
consegue ativar essa sessao. Captura de voz nunca desbloqueia nem retoma o
Condor.

A politica ainda classifica o risco, limita pastas e bloqueia shell, Python e
instalacao arbitrarios. Durante a sessao autenticada, operacoes do catalogo nao
pedem a frase novamente; exclusoes continuam recuperaveis pela lixeira privada
e alteracoes de arquivo mantem versoes locais.

## Rede

O servidor aceita somente `127.0.0.1`, `localhost` ou `::1`. Requisicoes exigem
cookie HttpOnly aleatorio com validade de quatro horas, origem local exata e Host
local. A emissao da sessao tambem exige a identidade da interface (`desktop-ui`
ou `hub-local`). Isso bloqueia inclusive ataques entre portas diferentes do
loopback. WebSocket aplica as mesmas regras, aceita no maximo quatro conexoes e
limita tamanho e frequencia das mensagens.

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
e redirecionamentos para esses destinos. Downloads tem limite de 100 MB.

## Execucao local e parada de emergencia

Ferramentas nao recebem shell arbitrario. Nomes de aplicativo e janela aceitam
somente caracteres controlados; no Windows os valores atravessam variaveis de
ambiente, sem interpolacao no PowerShell. Fechamento de aplicativo compara o
nome exato do processo por uma biblioteca portavel.

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
