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
