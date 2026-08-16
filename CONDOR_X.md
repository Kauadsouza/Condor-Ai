# Condor X — digital twin e engenharia segura

Condor X e um projeto de pesquisa modular. A versao atual e um **digital twin
inerte** dentro do laboratorio da aba Condor no ARTX Hub. Ela serve para organizar requisitos,
ergonomia, telemetria e prototipos de baixa energia antes de qualquer objeto
fisico.

## Referencia humana do digital twin

- altura normalizada no modelo: **1,80 m** do piso ao topo da cabeca;
- massa corporal de referencia: **85 kg**;
- silhueta organica com cranio, face, pescoco, claviculas, tronco, cintura,
  quadril, articulacoes, maos, dedos, pernas e pes;
- medidas servem para visualizacao e planejamento ergonomico inicial; nao
  substituem escaneamento corporal, prova de ajuste ou validacao profissional.

## Limites permanentes

- sem armas, emissores, laminas, chama ou agente incendiario;
- sem gas pressurizado, propulsao corporal ou sistema de voo;
- sem atuador de alta forca preso ao corpo;
- sem bateria artesanal vestivel ou celula sem BMS certificado;
- sem teste humano antes de revisao mecanica, eletrica e ergonomica profissional;
- o Condor nao pode remover estes limites nem aprovar o proprio teste.

## Arquitetura modular

| Modulo | Escopo permitido | Primeiro prototipo |
|---|---|---|
| Capacete | HUD, audio, camera e ventilacao | suporte de bancada sem vedacao |
| Torso | computador, IMU e telemetria | placa inerte impressa em 3D |
| Bracos | sensores de gesto e feedback leve | bracelete sem motor |
| Pernas | ergonomia e medicao de movimento | marcadores e IMUs externas |
| Energia | fonte certificada e fusivel | fonte de bancada, fora do corpo |
| Software | digital twin, logs e simulacao | ja integrado ao Hub local |

## Portoes de evolucao

1. **Conceito:** desenho, requisito, massa estimada e risco.
2. **Simulacao:** digital twin, colisao, calor teorico e falhas.
3. **Bancada:** modulo inerte, alimentacao externa limitada e botao fisico de corte.
4. **Nao vestivel:** testes repetidos em suporte, com registro de falhas.
5. **Revisao profissional:** eletrica, mecanica, incendio e ergonomia.
6. **Vestivel passivo:** somente estrutura sem motor e com retirada imediata.

No painel, um modulo de risco alto permanece bloqueado. Avancar a barra e
registrar progresso nao autoriza fabricacao nem teste fisico.
