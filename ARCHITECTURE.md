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
UI / Voz / Mobile / Dispositivos
              |
          Condor Core
   +----------+----------+
   |          |          |
Context    Event Bus   AI Gateway
Engine        |          |
   |      Project      Provider
   |       Engine       local
   |          |
   +---- Device Bridge
             |
      Action Safety Layer
```

- `ContextEngine`: estado estruturado do projeto, regiao, peca, arquivo,
  dispositivo e modo atual, sem segredos ou biometria no contrato da IA;
- `EventBus`: eventos persistidos no snapshot cifrado e transmitidos em tempo
  real pela conexao WebSocket existente;
- `AIGateway`: ponto unico para o provedor atual e para futuros provedores;
- `ProjectEngine`: projetos, pecas, rascunhos, versoes e integracao explicita;
- `DeviceBridge`: contratos modulares para Serial, Bluetooth e Wi-Fi;
- `ActionSafetyLayer`: classificacao independente de nivel 0 a 5. Atuadores e
  acoes perigosas permanecem bloqueados nesta versao.
- `CameraBridge`: fontes RTSP/ONVIF/HTTP/MJPEG da rede privada, quadros
  processados pelo modelo de visao local sem armazenamento e alertas de
  possivel presenca humana transmitidos pelo Event Bus. Nao ha reconhecimento
  facial nem envio de imagem para nuvem.

Uma peca nasce com `status=draft` e `integrated=0`. Criar versoes nao altera o
modelo principal. Somente a acao explicita `INTEGRAR AO MODELO` muda esse estado.
O mapa humano e um contrato de dados em seis camadas: silhueta, estrutura,
ossos, articulacoes, eixos de movimento e pontos tecnicos. Maos registram cada
dedo, suas falanges e articulacoes separadamente.

Na interface, o corpo permanece dentro de Projetos e o fluxo de pecas acontece
na propria regiao selecionada. Programacao concentra editor, descoberta
Serial/Arduino, Device Bridge, estado real de voz/gestos e Camera Bridge; nao
existem abas paralelas de Desenvolvimento, Corpo ou Dispositivos.

Adaptadores dependentes do sistema ficam nas bordas. O servidor, cofre,
memoria, politica, identidade, auditoria e protocolo da interface usam recursos
portateis de Python e formatos abertos.

## Estado e evolucao

1. concluido: conector generativo local compativel com Responses API;
2. concluido: STT, TTS, push-to-talk e visao totalmente locais;
3. concluido: ARTX Hub local com assistente Condor e catalogo de projetos no aplicativo;
4. concluido: aplicativo Condor em janela propria, separado do Hub e portavel entre Windows e Linux;
5. concluido: digital twin exclusivamente humano de alta fidelidade, com referencia de 1,80 m e 85 kg;
6. concluido: marca luminosa C como identidade permanente do Condor X no torax;
7. futuro: segundo equipamento Condor em hardware proprio via WireGuard;
8. futuro: sincronizacao cifrada ponta a ponta entre identidades autorizadas;
9. regra permanente: modulos fisicos apenas inertes e seguros. O projeto nao inclui dispositivo
   vestivel com chama, gas pressurizado ou agente incendiario.
