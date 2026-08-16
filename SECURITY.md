# Modelo de seguranca do Condor

## Fronteiras

O modelo de IA e tratado como planejador nao confiavel. Ele nao ganha shell,
Python arbitrario, instalacao de pacotes nem poder de mudar a propria politica.
Cada ferramenta passa por uma decisao deterministica local.

Dados privados em repouso usam AES-256-GCM. A frase do dono e verificada por
Scrypt e nao e armazenada. A identidade do dispositivo usa Ed25519. A auditoria
forma uma cadeia SHA-256 e o codigo tem um manifesto assinado.

## Aprovacoes

Uma aprovacao contem o hash exato da ferramenta e de todos os argumentos. Ela
expira, vale uma vez e nao autoriza uma acao parecida. Captura de voz nunca e
aceita como aprovacao.

## Rede

O servidor aceita somente `127.0.0.1`, `localhost` ou `::1`. Requisicoes exigem
cookie HttpOnly aleatorio, origem local e Host local. WebSocket aplica as mesmas
regras. A politica de conteudo bloqueia scripts externos e objetos; frames sao
permitidos somente na mesma origem para o Hub incorporar a interface do Condor.

STT, TTS e visao usam modelos locais. O push-to-talk envia o audio apenas para
`127.0.0.1`; capturas de tela continuam passando pela politica local antes de
serem analisadas. Voz e imagem nunca aprovam operacoes sensiveis.

Fatos antigos da memoria e aprendizado automatico por conector ficam desligados
por padrao. Assim, o historico cifrado nao e anexado a chamadas externas sem uma
escolha consciente no arquivo de configuracao.

Leituras e downloads web rejeitam localhost, rede privada, enderecos reservados
e redirecionamentos para esses destinos. Downloads tem limite de 100 MB.

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
