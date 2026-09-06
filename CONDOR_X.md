# Condor X — digital twin e engenharia segura

Condor X e um projeto de pesquisa modular dentro da ficha da aba **Projetos**
do aplicativo local Condor. Ele oferece uma referencia humana dividida por
regioes e um editor 3D para construir e versionar conceitos antes de qualquer
objeto fisico.

## Referencia humana e editor 3D

- silhueta de navegacao com cabeca, pescoco, tronco, bracos, maos, pernas e pes;
- cada ombro, braco, cotovelo, antebraco, mao, coxa, joelho, canela e pe abre
  seu proprio ambiente de modelagem;
- a malha e uma superficie parametrica organica, nao uma composicao de formas
  geometricas basicas;
- comprimento, larguras, profundidades, volume, espessura, folga, assimetria e
  torcao podem ser ajustados por controle deslizante ou valor numerico exato em
  milimetros;
- sensores, juntas, atuadores, controladores, cabos e fixacoes podem ser
  marcados como pontos tecnicos, sem afirmar que o componente fisico existe;
- modelos e versoes ficam no snapshot cifrado e podem ser exportados em STL;
- **Salvar no Corpo X** preserva a versao e aplica a mesma malha regional ao
  corpo 3D completo; somente um modelo 3D fica ativo por regiao, sem apagar versoes;
- o corpo completo se reorganiza conforme os comprimentos e larguras salvos;
  partes solidas sao salvas e partes em malha translucida sao apenas referencia;
- a cabeca possui perfil de cranio, face, mandibula e orelhas, em vez de uma
  forma arredondada generica;
- cada mao possui palma, polegar e quatro dedos separados; cada pe e uma peca
  fechada com leitura de calcado, sem dedos aparentes;
- ombros usam um perfil proprio de deltoide e se conectam ao torax com menos
  separacao visual;
- linhas tecnicas discretas identificam a face frontal, enquanto um emblema `C`
  tridimensional permanece no centro do torax;
- a linguagem visual da montagem usa uma carenagem branca perolada continua
  sobre juntas grafite, sem placas ou pecas 3D coladas sobre a superficie;
- peitoral, abdomen, quadril, ombros, bracos, maos, coxas, joelhos, canelas e
  calcados permanecem selecionaveis separadamente e usam apenas linhas frontais sem volume;
- o enquadramento 3D acompanha os limites reais do corpo para manter cabeca,
  maos, dedos e pes totalmente visiveis;
- os valores iniciais sao apenas uma previa visual. O Condor nao presume altura,
  massa nem medida corporal real.

## Limites permanentes

- sem armas, emissores, laminas, chama ou agente incendiario;
- sem gas pressurizado, propulsao corporal fisica ou sistema de voo executavel;
- a simulacao de propulsao permanece abstrata e digital: nenhuma engine fornece
  combustao, compressor, ignicao, tanque, tubulacao, valvula, montagem ou
  recomendacao de construcao;
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
| Software | digital twin, logs e simulacao | integrado ao aplicativo Condor |

## Portoes de evolucao

1. **Conceito:** desenho, requisito, massa estimada e risco.
2. **Simulacao:** digital twin, colisao, calor teorico e falhas.
3. **Bancada:** modulo inerte, alimentacao externa limitada e botao fisico de corte.
4. **Nao vestivel:** testes repetidos em suporte, com registro de falhas.
5. **Revisao profissional:** eletrica, mecanica, incendio e ergonomia.
6. **Vestivel passivo:** somente estrutura sem motor e com retirada imediata.

No painel, um modulo de risco alto permanece bloqueado. Avancar a barra e
registrar progresso nao autoriza fabricacao nem teste fisico.

## Limite do modelo digital

O editor produz uma malha conceitual e exportavel. Ele ainda nao substitui um
CAD mecanico certificado, escaneamento corporal, analise estrutural, simulacao
termica, tolerancias de fabricacao ou revisao profissional. A letra **C** no
mapa corporal e apenas identidade visual do Condor X.

## CX-M01 Design Studio

O **Design Studio** e agora a entrada principal do Condor X. Ele apresenta o
CX-M01 Concept A como uma hipotese de **compact personal aircraft**: corpo
externo continuo, piloto distinguivel no modo Safety, asas rigidas funcionais,
estrutura dorsal estreita e volumes de energia e propulsao integrados ao
formato. A leitura visual deve ser `corpo + asas + estrutura dorsal`, e nao uma
pessoa carregando motores externos.

O modelo nao copia uma aeronave existente. O estudo das referencias oficiais
foi limitado a principios: transicao para cruzeiro sustentado pela asa e
redundancia (Joby), empuxo vetorial em volume compacto (CycloTech) e uso da
propulsao para aumentar a sustentacao da asa antes de reduzir sua demanda no
cruzeiro (Electra). Joby, CycloTech e Electra nao definem a forma, a escala nem
a tecnologia final do Condor.

O Studio oferece:

- vistas traseira, frontal, lateral e 3/4 no mesmo canvas 3D do corpo;
- selecao e edicao relativa de envergadura, cordas, sweep, dihedral, twist e
  pre-visualizacao de dobra, com espelhamento bilateral;
- Flight Pose de 0 a 90 graus aplicado ao conjunto inteiro, sem deformar a
  anatomia ou afirmar dinamica de voo;
- modos Design, Aero, Structure, Mass/CG, Energy, Propulsion, Thermal, Safety e
  Mission;
- Flow Preview explicitamente rotulado como visualizacao simplificada, nunca
  CFD; load paths e calor permanecem placeholders/assumptions sem dados;
- tres candidatos `PROPULSION CONCEPT A/B/C`. Eles reorganizam apenas volumes
  compactos abstratos; massa, empuxo, tecnologia, consumo, calor, arrasto,
  controle e autonomia continuam **DATA REQUIRED**;
- painel Change Impact, Mission M01 e uma comparacao que nao declara vencedor
  enquanto os candidatos nao tiverem entradas equivalentes e verificaveis;
- acesso preservado ao modelador parametrico regional e ao Placement Lab como
  ferramentas avancadas.

O estado `condor-x-design-studio-v1` acompanha o layout do Placement Lab e so e
persistido pela acao **SAVE** no mesmo snapshot local cifrado. Assim, o viewport,
o inspector, as engines e o historico usam uma fonte de verdade compartilhada.
Respostas de analise fora de ordem sao descartadas para nao sobrescrever uma
edicao mais recente.

**MISSION M01 — 2 HOURS ENDURANCE** permanece um requisito de pesquisa. A
interface nao converte esse alvo em resultado e nao presume que a asa, a fonte
de energia ou qualquer candidato de propulsao consiga cumpri-lo.

## Propulsion Placement Lab

O **Propulsion Placement Lab** e um ambiente exclusivo do Condor X para comparar
fontes abstratas de empuxo no digital twin. Ele nao escolhe uma posicao pela
aparencia e nao declara uma instalacao segura. As 19 `CANDIDATE PROPULSION ZONES`
sao volumes de simulacao, avaliados novamente quando a unidade, a massa ou outro
dado do layout muda.

Cada layout mantem unidades com massa, posicao e orientacao tridimensionais,
empuxo, comando, curva de consumo, calor, envelope, grupo de controle,
redundancia, estado e confianca. Campo sem fonte fica como **DATA REQUIRED**. A
decisao passa a `INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT` quando os
dados minimos nao existem; o sistema nao preenche especificacoes fisicas.

As engines locais recalculam em cascata:

1. massa total, propulsion COM e vehicle CG;
2. contribuicoes pontuais `Ixx`, `Iyy` e `Izz`;
3. vetores de forca, center of thrust e momentos X/Y/Z;
4. autoridade de lift, forward, roll, pitch e yaw;
5. mixer limitado, saturacao e erro de demanda;
6. placement score, exposicao humana, envelopes e colisao;
7. arrasto de instalacao e indice termico abstrato;
8. falha de uma unidade e falhas de grupos comuns;
9. fases TAKEOFF, TRANSITION, CRUISE e LANDING da M01;
10. energia, redundancia, safety index e cadeia de evidencia.

A interface permite manter Layout A, Layout B e outros layouts, mover uma unidade
por zona, arrasta-la no plano do modelo 3D, espelhar esquerda/direita, comparar
resultados e registrar uma execucao M01 no snapshot cifrado. `PROPULSION ZONES`,
`THRUST VECTORS`, `MOMENT VIEW`, fluxo, volumes termicos e load paths sao
visualizacoes conceituais derivadas do resultado das engines.

Todo resultado importante registra `SOURCE`, `METHOD`, `ASSUMPTIONS`,
`CONFIDENCE` e `MODEL LEVEL`. A versao atual usa L1/L2. CFD, FEA, wind tunnel,
bench test e flight test sao origens futuras; o Condor X nao simula esses niveis
sem dados externos reais.

## Centro de Engenharia

O **Centro de Engenharia** divide as lacunas de validacao do CX-M01 em oito
telas internas: Modelo Digital, Aerodinamica/CFD, Estruturas/FEA, Dinamica de
Voo 6-DoF, Termico/Incendio, Flutter/Aeroelasticidade, Propulsao e Seguranca de
Voo. Ele e um mapa de prontidao e evidencias; nao adiciona solvers ficticios.

Cada area mostra, separadamente:

- a pergunta que a disciplina precisa responder;
- o que realmente existe no Condor hoje;
- os dados ainda necessarios;
- as saidas que so poderao existir no futuro e dentro de um escopo definido;
- as evidencias exigidas para avancar;
- o trabalho de organizacao do responsavel pelo projeto;
- os profissionais que precisam analisar ou revisar;
- as dependencias, o proximo passo seguro e as alegacoes bloqueadas.

Os niveis de **modelo** (`M0` a `M5`) e de **evidencia** (`E0` a `E5`) sao
independentes. Uma triagem M2 com entrada manual E1 nao se transforma em
validacao fisica. Mesmo uma analise futura revisada permanece limitada a sua
configuracao, metodo, condicao e incerteza; ela nao certifica automaticamente o
sistema completo.

O estado inicial e deliberadamente fechado: oito areas mapeadas, zero areas
validadas. As seguintes alegacoes permanecem falsas ate existirem capacidades,
evidencias e revisoes externas correspondentes:

- digital twin validado;
- CFD, FEA, dinamica 6-DoF, incendio ou flutter concluidos;
- tecnologia de propulsao selecionada ou aprovada;
- decolagem, transicao, cruzeiro ou pouso humano demonstrados como seguros.

Os botoes de cada tela podem abrir o modo visual relacionado no Design Studio
ou o Placement Lab. Navegar entre areas nao muda a geometria, nao cria um
resultado de engenharia e nao autoriza construcao, teste vestivel ou voo.
