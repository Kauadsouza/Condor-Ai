# CONDOR — câmera amiga, gestos, aba Programação e segurança · Especificação e plano

> Especificação + plano juntos, para uma aprovação só (pedido do dono: "tire as
> dúvidas, aprove o plano e execute sem perguntar"). Execução por subagentes em
> paralelo (superpowers: subagent-driven-development + dispatching-parallel-agents).

## O que o dono pediu (palavras dele, resumidas)

- Sistema: tirar **Eventos recentes**, o card de **treino** (os 👍/👎 do chat ficam — o
  treino "vai sendo feito com o tempo"), o card **Contexto ativo** e a **faixa do topo
  do chat**. A validação de atualização fica **só com o campo da palavra de acesso**.
  Menos texto explicativo.
- Câmera: o CONDOR **olha quando eu pedir, nunca o tempo todo**, e interage como um
  amigo ("analisa minha roupa, fala se está boa").
- Gestos: consertar e usar para **controlar o CONDOR e o PC**.
- Programação: sem "dispositivos presentes"; **Pesquisar dispositivos → eu escolho →
  conecta**; só o conectado aparece. Com Arduino: **o CONDOR dentro da aba** (texto,
  voz, pet), escreve o código no editor e **eu clico Enviar**.
- Segurança: rodar a auditoria **insecure-defaults (Trail of Bits)** no CONDOR e corrigir;
  validar que ele **falha fechado**. Testar a interface com o **agent-browser (Vercel)**.

Suposições minhas (corrija se estiver errado):
- O export do treino sai da tela mas **continua existindo pela API**; quando for treinar,
  eu te dou o comando (ou volto um botão pequeno).
- "Validação" = o formulário "VALIDAR ATUALIZAÇÃO INSTALADA" da aba Sistema.

## Design

### A. Sistema e chat mais limpos
- Remover do `index.html`: card Eventos recentes, card Treino (+ `training.js`), card
  Contexto ativo e a faixa `PROJETO · REGIÃO · PEÇA · DISPOSITIVO` do chat.
- Card de integridade: só `palavra de acesso` + botão **VALIDAR**, sem parágrafos.
- Encurtar textos longos da aba Programação/Sistema (ex.: "O INVENTÁRIO CONTINUA ATIVO",
  "CAPACIDADES DETECTÁVEIS").

### B. Câmera amiga (uma foto por pedido)
- Nova ferramenta interna do cérebro `condor_olhar_camera(pedido)`. Aparece para o modelo
  local quando você fala de câmera/roupa/"me vê"/"olha isso"/"como estou".
- Fluxo: servidor pede à janela `camera.capturar` pelo WebSocket → a janela abre a
  câmera física, tira **uma** foto, **desliga na hora** e devolve → o CONDOR analisa com o
  **qwen3-vl local** (mesmo usando API no chat, a imagem nunca sai do PC) → responde como
  amigo, com opinião honesta e gentil.
- Aviso visível "📷 câmera usada agora" no chat. Nada é salvo.
- Travas: permissão `camera` (você libera uma vez em "sempre"), recusa se a trava facial
  ou os gestos estiverem com a câmera aberta, tempo limite de 15 s.
- Persona "amigo": comenta roupa/visual/ambiente com sinceridade, sem inventar o que não
  dá pra ver.

### C. Gestos de verdade
- Trocar o detector por **MediaPipe GestureRecognizer** (Google, roda na própria janela,
  21 pontos da mão, a imagem não sai do navegador). Arquivos locais em
  `condor/ui/vendor/mediapipe/` com SHA-256 conferido.
- Mapeamento:
  | Gesto | Ação |
  |---|---|
  | ✋ mão aberta (segurar ~0,5 s) | CONDOR ouve (liga o microfone) |
  | ✊ punho | CONDOR para de falar |
  | 👍 polegar pra cima | tocar/pausar música |
  | 👉 deslizar direita/esquerda | próxima/anterior (música e slide) |
  | ☝️ dedo pra cima + subir/descer | rolar a tela |
  | ✌️ vitória + subir/descer | volume |
- Anti-disparo: gesto precisa segurar ~350 ms e cada ação tem ~800 ms de intervalo.
- Ações do PC por um endpoint novo com **lista fechada** (`/api/gestures/action`): o
  navegador nunca manda teclas livres. Nova permissão `gesture_pc_control`.
- Continua funcionando com a janela em segundo plano (opção), e o detector antigo fica só
  como reserva.

### D. Aba Programação com o CONDOR dentro
- **Pesquisar dispositivos** (botão) → lista portas/placas encontradas (nome, porta, placa)
  → **Conectar**. Card "dispositivos presentes" e varredura automática a cada 4 s saem.
  Só o dispositivo conectado aparece, com **Desconectar**.
- **Enviar** grava no dispositivo escolhido (`/api/programming/arduino/run` com porta/placa
  escolhidas); mantém a confirmação e a permissão `arduino_upload`.
- **CONDOR na aba**: mini-chat com texto e microfone (e o pet reagindo). Você pede ("faz o
  LED piscar a cada 1 s"), o CONDOR escreve o sketch para a placa conectada, o código cai
  no editor, e **você clica Enviar**. O CONDOR nunca grava sozinho no Arduino.
- O editor recarrega quando o CONDOR salva código.

### E. Segurança
- Rodar o workflow `insecure-defaults:audit-pipeline` no repositório inteiro.
- Corrigir tudo que for confirmado (segredos com valor padrão, credenciais padrão,
  interruptores que falham aberto, cripto fraca, permissões amplas, vazamento de debug).
- Checagem "falha fechado": sem cofre/sessão/segredo, toda rota sensível tem que negar
  (teste automatizado percorrendo as rotas).
- A câmera, os gestos no PC e o mini-chat nascem com essas travas.

### F. Teste da interface com agent-browser
- Instalar `agent-browser` (npm, global).
- Subir um **CONDOR de teste isolado** (pasta de dados temporária, porta 7790 — seu CONDOR e
  sua memória não são tocados), abrir com o segredo de boot na URL e verificar:
  Sistema limpo, faixa do chat fora, Programação (pesquisar/conectar simulados, mini-chat),
  visualizador de imagem, cores do orbe. Prints conferidos.

### G. Entrega
- Todas as suítes verdes; instalador refeito; **atualizar o app instalado** (fecha o CONDOR
  ~5 min, memória intocada); commits **só em seu nome** e push para o GitHub.

## Plano de execução

Tarefas B, C e D mexem em partes diferentes e rodam **em paralelo**, cada uma num
subagente em cópia isolada do repositório (git worktree); depois eu junto e reviso.

1. **A — limpeza** (eu): remove cards/faixa, encurta textos, atualiza testes que fixam
   esses elementos. *Verifica:* suítes verdes.
2. **E1 — auditoria** (em paralelo com 3-5): roda o insecure-defaults, gera o relatório.
3. **B — câmera amiga** (subagente, worktree): ferramenta + ponte WebSocket com futuro e
   tempo limite + script de captura única + persona + testes (permissão, recusa com câmera
   ocupada, nenhuma imagem guardada, roteamento das frases).
4. **C — gestos** (subagente, worktree): vendorizar MediaPipe com hash, reescrever
   `gestures.js`, endpoint de ação com lista fechada, `rolar()`/volume, permissão, testes da
   lista fechada e do anti-disparo.
5. **D — Programação** (subagente, worktree): pesquisar/conectar/desconectar, envio ao alvo
   escolhido, mini-chat com `contexto: programacao` que põe o código no editor, recarga do
   editor, testes.
6. **Juntar** B/C/D no main, resolver conflitos, suítes completas.
7. **E2 — corrigir achados** da auditoria + teste "falha fechado".
8. **Revisão independente** (subagente revisor) de tudo; corrigir o que ele confirmar.
9. **F — agent-browser** no CONDOR de teste; corrigir o que aparecer.
10. **G — entrega**: instalador, atualizar o app, commits em seu nome, push, CI verde.

## Fora do escopo (continua pendente)
- API paga (você ainda vai configurar).
- Treino real no Colab (fica "com o tempo" pelos 👍/👎).
