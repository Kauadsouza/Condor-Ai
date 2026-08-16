# Arquitetura

```text
ARTX Hub /hub
  -> sistemas ARTX independentes
  -> aba Condor (demonstracao sem operacoes)
     -> visao da inteligencia
     -> laboratorio
        -> Condor X (unico projeto atual)

Aplicativo Condor -> janela nativa -> /ui
  -> sessao local HttpOnly de 4 h + Host/Origin/Client exatos
  -> limites de corpo, frequencia, conexoes e tentativas de autenticacao
  -> controle local de autonomia
  -> Sessao Condor
     -> modo offline deterministico
     -> conector local por loopback ou conector externo opcional (planejamento)
        -> PolicyEngine local
           -> aprovacao exata do dono
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
do modelo mude permissao, valide a propria acao ou fabrique uma aprovacao.

Adaptadores dependentes do sistema ficam nas bordas. O servidor, cofre,
memoria, politica, identidade, auditoria e protocolo da interface usam recursos
portateis de Python e formatos abertos.

## Estado e evolucao

1. concluido: conector generativo local compativel com Responses API;
2. concluido: STT, TTS, push-to-talk e visao totalmente locais;
3. concluido: ARTX Hub original local, aba demonstrativa do Condor e digital twin do Condor X;
4. concluido: aplicativo Condor em janela propria, separado do Hub e portavel entre Windows e Linux;
5. em refinamento: digital twin exclusivamente humano de alta fidelidade, com referencia de 1,80 m e 85 kg;
6. concluido: marca luminosa C como identidade permanente do Condor X no torax;
7. futuro: segundo equipamento Condor em hardware proprio via WireGuard;
8. futuro: sincronizacao cifrada ponta a ponta entre identidades autorizadas;
9. regra permanente: modulos fisicos apenas inertes e seguros. O projeto nao inclui dispositivo
   vestivel com chama, gas pressurizado ou agente incendiario.
