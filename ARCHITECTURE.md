# Arquitetura

```text
ARTX Hub /hub
  -> sistemas ARTX independentes
  -> aba Condor (assistente organizacional)
     -> cria atividades do Hub
     -> abre sistemas ARTX
     -> nao recebe memoria, arquivos ou comandos do PC

Aplicativo Condor -> janela nativa -> /ui
  -> sessao local HttpOnly de 4 h + Host/Origin/Client exatos
  -> limites de corpo, frequencia, conexoes e tentativas de autenticacao
  -> frase valida ativa o perfil operacional unico do dono
  -> aba Projetos
     -> catalogo de projetos locais
     -> ficha interna de cada projeto
        -> informacoes e prototipo
        -> Condor X (primeiro projeto)
  -> Sessao Condor
     -> modo offline deterministico
     -> conector local por loopback ou conector externo opcional (planejamento)
        -> PolicyEngine local
           -> sessao autenticada do dono
              -> ferramentas especificas

Cofre AES-GCM
  -> chaves opcionais
  -> chave da memoria
  -> identidade Ed25519

SQLite em RAM
  -> snapshot AES-GCM em ~/.condor/memory
  -> notas e tarefas locais do Hub
  -> modulos e progresso do Condor X
  -> layouts e execucoes M01 do Propulsion Placement Lab

Auditoria hash-chain + manifesto de codigo assinado

Modelos locais
  -> qwen3:4b-instruct (planejamento)
  -> qwen3-vl:2b (visao autorizada)
  -> Faster Whisper small (STT em CPU)
  -> Piper pt_BR-faber-medium (TTS em CPU)
```

O pacote `condor/security` nao chama IA. Essa separacao impede que uma resposta
do modelo mude permissao, desbloqueie o dono ou amplie o catalogo de ferramentas.

## Condor Core

O aplicativo operacional agora converge pelas seguintes camadas centrais:

```text
OWNER autenticado
       |
Condor Core Identity v1        <- estavel, versionada, nao editavel pelo modelo
       |
Memoria local cifrada          <- Owner / Project / conversas recentes
       |
World State + Episodes         <- fonte / confianca / validade / historico
       |
Durable Task Engine            <- checkpoints e retomada apos reinicio
       |
Context Builder                <- somente contexto relevante e sem segredos
       |
Model Router                   <- Local / OpenAI / Claude
       |
Local Image Engine             <- stable-diffusion.cpp, sem nuvem
       |
Cognitive Engine temporario    <- raciocina, mas nao possui a identidade
       |
Ferramentas tipadas + Policy   <- permissao e auditoria independentes
       |
Resposta do Condor
```

`condor/brain/identity.py` e a fonte versionada da identidade persistente, do
protocolo de verdade e dos modos cognitivos. A camada diferencia `FACT`,
`CALCULATION`, `ESTIMATE`, `ASSUMPTION`, `HYPOTHESIS` e `UNKNOWN`; ativa
diretrizes deterministicas para pesquisa, engenharia, ensino, codigo, debug,
Condor X e red team; e preserva os mesmos limites em todos os provedores.

O Core estavel nao e memoria aprendida. Preferencias confirmadas entram como
`OWNER MEMORY`; fatos tecnicos e de projeto entram como `PROJECT MEMORY`. O
modelo recebe somente os itens recuperados para o pedido atual. Trocar de
modelo nao troca identidade, memoria, permissoes ou relacao com o dono.

No modo Condor X, a identidade exige dados ausentes como `DATA REQUIRED`, separa
os niveis L0 a L6 e proibe usar texto generativo como substituto de physics
engine, CFD, FEA, dinamica 6-DoF, incendio, flutter ou validacao profissional.
Essas regras orientam a resposta; os bloqueios reais continuam nas camadas de
politica, seguranca e ferramentas do runtime.

```text
UI / Voz / Mobile / Dispositivos
              |
          Condor Core
   +----------+----------+------------+
   |          |          |            |
Context    Event Bus   AI Gateway  Orchestrator
Engine        |          |            |
   |      Project      Provider   ferramentas IA
   |       Engine   local/externo      |
   +----------+----------+------------+
              |
         Device Bridge
             |
      Action Safety Layer
```

- `ContextEngine`: estado estruturado do projeto, regiao, peca, arquivo,
  dispositivo e modo atual, sem segredos ou biometria no contrato da IA;
- `EventBus`: eventos persistidos no snapshot cifrado e transmitidos em tempo
  real pela conexao WebSocket existente;
- `AIGateway`: ponto unico para o provedor atual e para futuros provedores;
- `Web Research`: no provedor OpenAI, `web_search` roda dentro da Responses API
  e devolve citacoes/URLs; no provedor local, `buscar_web` e `ler_site` formam um
  fallback publico. Conteudo de pagina permanece dado nao confiavel e nunca
  amplia permissoes do Condor;
- `CondorOrchestrator`: liga a IA ao estado real de Projetos, Programacao,
  Laboratorio, Memoria e Dispositivos. Toda operacao valida o cofre, a permissao
  da capacidade e os limites de entrada antes de alterar o snapshot cifrado;
- `ProjectEngine`: projetos, pecas, rascunhos, versoes e integracao explicita;
- `DeviceBridge`: contratos modulares para Serial, Bluetooth e Wi-Fi;
- `ActionSafetyLayer`: classificacao independente de nivel 0 a 5. Atuadores e
  acoes perigosas permanecem bloqueados nesta versao.
- Camera Bridge e analise visual geral estao desativadas por politica do Owner.
  A camera fisica so pode ser aberta pelo fluxo local e visivel de cadastro ou
  autenticacao facial; nao existe captura de fundo nem envio para nuvem.

Uma peca nasce com `status=draft` e `integrated=0`. Rascunhos e versoes isoladas
nao alteram o modelo principal. No editor 3D, a acao explicita **Salvar no Corpo
X** cria a versao e integra a geometria atual. Existe somente um modelo 3D
parametrico ativo por regiao; salvar outro naquela regiao substitui a geometria
ativa sem apagar o historico nem impedir outros componentes integrados.
O mapa humano e um contrato de dados em seis camadas: silhueta, estrutura,
ossos, articulacoes, eixos de movimento e pontos tecnicos. Maos registram cada
dedo, suas falanges e articulacoes separadamente.

Cada regiao abre o `modeler-3d.js`. Ele gera uma superficie organica oca com
`BufferGeometry`, formada por perfis transversais parametrizados; nao monta a
peca com cubos, esferas ou capsulas. O snapshot registra apenas parametros,
camadas e ate 128 pontos tecnicos, fica no banco cifrado e pode gerar um STL
local. O servidor limita cada snapshot a 220 KB e rejeita valores JSON invalidos.
Os valores iniciais sao somente uma forma visual editavel, nunca medidas
corporais confirmadas.

O corpo completo tambem e renderizado em 3D com a mesma funcao de malha usada
no editor regional. O layout e recalculado pelos comprimentos e larguras salvos:
regioes integradas aparecem solidas e regioes sem modelo continuam em malha
translucida apenas como referencia.

As regioes complexas nao reutilizam a casca tubular dos membros. A cabeca tem
perfil continuo de cranio, face e mandibula; cada mao combina palma, polegar e
quatro dedos; o ombro usa um perfil de deltoide; e o pe usa uma malha unica
inspirada em tenis, com calcanhar, peito do pe, bico elevado e sola continua,
sem dedos expostos ou pecas sobrepostas. Todas essas partes continuam sendo superficies
parametricas organicas mescladas em uma unica geometria regional. Linhas sutis
marcam somente a frente e um emblema `C` extrudado identifica o torax. O
enquadramento deriva do limite real da montagem para nao cortar extremidades.

A camada visual robotica e procedural segue a mesma divisao regional do modelo.
Cada regiao usa uma carenagem parametrica unica e continua, sem placas ou pecas
3D sobrepostas a superficie. Linhas sem volume identificam a frente; pescoco,
cotovelos, joelhos e maos revelam a base grafite. As geometrias continuam locais,
selecionaveis e reconstruidas a partir dos parametros salvos, sem introduzir
especificacoes fisicas nao registradas.

O Design Studio reutiliza o `CondorBody3D` e o mesmo canvas WebGL da montagem do
corpo. `design-studio-3d.js` adiciona asas, estrutura dorsal, piloto conceitual e
volumes abstratos em camadas procedurais separadas; `design-studio.js` coordena
modo, selecao, inspector, pose e Change Impact. A geometria de asa e relativa e
nao entra silenciosamente nas engines: ate existir um contrato aerodinamico
validado, Flow Preview, estrutura e efeitos de missao permanecem `ASSUMPTION` ou
`DATA REQUIRED`.

```text
CX-M01 Design Studio (viewport + inspector)
                    |
        condor-x-design-studio-v1
                    |
       layout.designStudio no cofre
                    |
     Propulsion Placement Lab / engines
```

Eventos locais sincronizam as duas interfaces, mas nao criam uma nova fronteira
de permissao. `SAVE` continua passando pelo endpoint Condor X, pela sessao do
dono e pelo snapshot AES-GCM. Cada requisicao de analise leva uma revisao; uma
resposta antiga e ignorada quando houve edicao, save ou run mais recente.

O Propulsion Placement Lab vive somente na ficha do Condor X. A interface envia
layouts para `/api/condor-x/propulsion/*`; o servidor normaliza o contrato e
orquestra as engines em `condor/engine`. Massa e CG alimentam inercia e momentos;
esses resultados alimentam placement, controle, falhas, missao e safety index.
Layouts e runs ficam no mesmo SQLite em RAM com snapshot AES-GCM. Nenhum endpoint
do Hub e nenhum Device Bridge recebe essas fontes abstratas. A
`ActionSafetyLayer` continua bloqueando qualquer acao fisica com propulsao.

```text
Condor X Propulsion UI / 3D
            |
  /api/condor-x/propulsion
            |
     PropulsionLabEngine
   +--------+---------+-----------+
   |        |         |           |
 Mass/CG  Inertia  Thrust/Moment  Placement/Thermal
                         |
                  Control Allocation
                         |
                 Failure + Mission M01
                         |
                 Safety + Evidence
```

Na interface, o corpo permanece dentro de Projetos e o fluxo de pecas acontece
na propria regiao selecionada. Programacao concentra o editor com deteccao
automatica de linguagem e buffer cifrado por projeto, descoberta e conexao
Serial/Arduino explicita pelo Device Bridge e o estado visual de voz e gestos.
Camera Bridge nao aparece nessa area; nao existem abas paralelas de
Desenvolvimento, Corpo ou Dispositivos. Laboratorio organiza experimentos e
Sistema mostra permissoes, contexto ativo e eventos sem duplicar explicacoes.
Chat, push-to-talk e ativacao por voz entram pela mesma `Sessao`, portanto usam
o mesmo `AIGateway`, contexto e orquestrador. O provedor nao recebe acesso geral
ao processo: ele escolhe somente ferramentas tipadas do catalogo; comandos
fisicos, atuadores e operacoes destrutivas continuam sujeitos a politica e
confirmacao independente.

O `Recall` coloca no prompt de sistema somente fatos duraveis confirmados.
Os ultimos turnos mantem continuidade como mensagens `user`/`assistant`, mas
texto bruto antigo nunca e promovido a instrucao de sistema; uma busca historica
explicita continua disponivel na interface local. O snapshot completo permanece
cifrado. Um extrator deterministico registra imediatamente fatos pessoais
inequivocos, e o extrator generativo pode enriquecer informacoes mais sutis em
segundo plano. Fontes da internet nao viram fatos pessoais automaticamente.

Adaptadores dependentes do sistema ficam nas bordas. O servidor, cofre,
memoria, politica, identidade, auditoria e protocolo da interface usam recursos
portateis de Python e formatos abertos.

## Estado e evolucao

1. concluido: conector generativo local compativel com Responses API;
2. concluido: STT, TTS, push-to-talk e visao totalmente locais;
3. concluido: ARTX Hub local com assistente Condor e catalogo de projetos no aplicativo;
4. concluido: aplicativo Condor em janela propria, separado do Hub e portavel entre Windows e Linux;
5. concluido: referencia humana dividida em regioes, sem medidas corporais presumidas;
6. concluido: modelador 3D parametrico por regiao, versoes cifradas e exportacao STL;
7. concluido: montagem 3D completa recomposta automaticamente pelas regioes salvas;
8. concluido: CX-M01 Design Studio com Concept A, asas relativas, pose, A/B/C abstratos e estado cifrado compartilhado;
9. concluido: Propulsion Placement Lab abstrato L1/L2, layouts cifrados, falhas e M01;
10. futuro: importacao de CFD, FEA e dados experimentais com origem verificavel;
11. futuro: segundo equipamento Condor em hardware proprio via WireGuard;
12. futuro: sincronizacao cifrada ponta a ponta entre identidades autorizadas;
13. regra permanente: modulos fisicos apenas inertes e seguros. O projeto nao inclui dispositivo
   vestivel com chama, gas pressurizado ou agente incendiario.
