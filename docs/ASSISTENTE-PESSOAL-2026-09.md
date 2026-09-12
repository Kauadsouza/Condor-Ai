# Condor pessoal: fortalecer o sistema existente

Revisão de 12 de setembro de 2026. Substitui a proposta de interface de 9 de setembro.

## Interface e capacidades

A interface original volta a ser a entrada do aplicativo e do Hub local: Chat, Projetos, Programação, Laboratório, Memória, CELL e Sistema. O visual, o pet e os módulos existentes são preservados. O endereço experimental redireciona para a interface completa.

As melhorias do núcleo permanecem: streaming nativo do Ollama com ferramentas, contexto local padrão de 8192, formato de resposta adequado a texto/voz, recuperação de erros e inicialização no login do Windows. O sistema continua oferecendo os provedores e chaves na aba Sistema; o uso externo envia contexto ao provedor escolhido.

A aba Chat passa a expor conversa contínua. O controle solicita permissão persistente pelo fluxo existente do Sistema, fecha a captura ao bloquear/desconectar e pausa após silêncio sem fala. Uma permissão atrasada do navegador não reabre o microfone após o bloqueio. A reprodução usa a saída de som configurada no Windows. Esc encerra a captura contínua; não representa cancelamento de uma tarefa já enviada ao núcleo.

O chat preserva texto digitado sem conexão e descarta a fila pendente quando a conexão cai, evitando reenviar ações automaticamente. A aba Memória mantém seu mapa e oferece consulta paginada ao histórico cifrado, inclusive mensagens arquivadas pela interface experimental. A limpeza definitiva continua sendo uma ação separada e explícita do chat.

Sistema mantém a seleção de modelos e permissões e recebe os controles de janela residente e de validação da atualização pelo dono. Bloqueio de sessão limpa as janelas conectadas. Cofre, memória e credenciais existentes são preservados.

## iPhone, relógio e fone

O iPhone 12 segue como alvo. A inspeção do código confirma que o visualizador móvel é somente leitura, o Bluetooth é descoberta e os comandos efetivos de DeviceBridge usam adaptador serial identificado. Detectar um aparelho não concede controle sobre ele. A fundação CELL/cloud compartilha chat e notas quando configurada; não executa ações nativas em apps iOS.

Relógio e fone estão pendentes por decisão do dono: ainda não existem aparelhos para configurar ou validar.

Para integrar iPhone com ações reais, ainda é necessário implementar um aplicativo/atalhos específicos e transporte privado autenticado, com cadastro revogável por aparelho, escopos de ação, expiração, proteção contra repetição e auditoria. Não expor a API de controle do Windows publicamente. App Intents e Atalhos são os pontos oficiais de integração da Apple:

- https://developer.apple.com/documentation/appintents
- https://support.apple.com/guide/shortcuts/run-shortcuts-from-apple-watch-apd5888b0858/ios

## Critérios de evolução

Uma experiência inspirada em Jarvis exige conversa com memória verificável, ações com resultado confirmado, voz com interrupção e recuperação, conectores reais por aparelho e segurança independente do modelo. Esta entrega fortalece o sistema existente; não declara autonomia universal, controle iOS implementado ou produto comercial pronto.

Próximos trabalhos: implementar e testar as primeiras ações iOS; avaliar qualidade/latência de diálogos longos e do roteamento de ferramentas; melhorar recuperação de tarefas interrompidas; distribuir atualizações assinadas; executar testes prolongados de voz com hardware disponível.

## Verificação e publicação

Testes Python: `python testes/rodar_testes.py` e `python testes/test_assistant.py`. Testes de ciclo de voz sem hardware: `node --test testes/voice_lifecycle.cjs`. O CI também verifica dependências e análise de segurança.

A revisão visual usa estado temporário separado do cofre do dono, incluindo um fato de teste e conversa com o modelo local. A instalação local exige desbloqueio normal e validação da assinatura pelo dono na aba Sistema. Não enviar a palavra de acesso em mensagens.

O Hub possui build web e exportação local separados. O Condor é instalado no Windows; não publicar seu servidor de controle no Vercel. Publicação em GitHub e deploy web devem ser verificados pelo SHA e pela URL da execução, não apenas pelo início do comando.
