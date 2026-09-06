const root = document.getElementById('cxEngineeringHub');

if (root) {
  const MATURITY_STAGES = ['CONCEITO', 'MODELO PRELIMINAR', 'EVIDÊNCIA', 'REVISÃO', 'REVISADO NO ESCOPO'];
  const CLAIM_BOUNDARIES = Object.freeze({
    validatedDigitalTwin: false,
    cfdCompleted: false,
    feaCompleted: false,
    sixDofCompleted: false,
    fireModelCompleted: false,
    flutterCompleted: false,
    propulsionTechnologySelected: false,
    safeFlightDemonstrated: false
  });

  const WORKSPACES = {
    DIGITAL_TWIN: {
      code: 'CX-ENG-01 · MODELO DIGITAL',
      title: 'Modelo Digital Conceitual',
      status: 'NÃO É UM DIGITAL TWIN VALIDADO',
      modelLevel: 'M1',
      evidenceLevel: 'E1',
      stageIndex: 1,
      validated: false,
      question: 'Como garantir que geometria, massas, missão, propulsão e evidências descrevem exatamente a mesma versão do CX-M01?',
      current: 'Há um corpo 3D, asas, estrutura dorsal, volumes abstratos, regiões paramétricas e triagens L1/L2. Isso organiza hipóteses; ainda não reproduz nem acompanha a física de uma aeronave real.',
      required: [
        'CAD controlado, lista de componentes e revisão identificada',
        'Massa, centro de gravidade e inércia medidos por configuração',
        'Referências rastreáveis para aero, estrutura, energia, térmico e propulsão',
        'Sistema de coordenadas, unidades, condições ambientais e incertezas'
      ],
      outputs: [
        'Baseline único e versionado do sistema',
        'Rastreabilidade entre entrada, resultado, evidência e revisão',
        'Aviso de resultado desatualizado quando o modelo mudar',
        'Mapa honesto das lacunas de cada disciplina'
      ],
      evidence: [
        'Fonte, data, versão e responsável por cada dado',
        'Hash da configuração analisada',
        'Correlação entre o modelo e medições físicas controladas',
        'Revisão independente limitada ao escopo declarado'
      ],
      ownerWork: 'Organizar requisitos, versões e decisões; cobrar a origem de cada valor; impedir que desenhos, hipóteses e resultados de versões diferentes sejam misturados.',
      professionals: ['Engenheiro de sistemas', 'Responsável por configuração', 'Especialistas de cada disciplina', 'Equipe de testes e instrumentação'],
      dependencies: ['Todas as demais áreas', 'Registro de evidências', 'Controle de configuração'],
      canSay: 'O Condor X possui uma base digital conceitual para organizar o estudo do CX-M01.',
      cannotSay: 'Que existe um digital twin validado, uma réplica fiel em tempo real ou uma aeronave fisicamente comprovada.',
      next: 'Criar uma baseline imutável por revisão e um registro de evidência com fonte, unidade, data, configuração e responsável.',
      relatedMode: 'DESIGN',
      relatedLabel: 'ABRIR INTEGRAÇÃO 3D'
    },
    CFD_AERO: {
      code: 'CX-ENG-02 · AERODINÂMICA / CFD',
      title: 'Aerodinâmica e CFD',
      status: 'CFD NÃO EXECUTADO',
      modelLevel: 'M1',
      evidenceLevel: 'E0',
      stageIndex: 0,
      validated: false,
      question: 'As asas, o corpo e a propulsão geram sustentação, arrasto e controle adequados em cada condição da missão?',
      current: 'Existe geometria visual e uma animação simplificada de fluxo. Ela ajuda a enxergar o conceito, mas não resolve as equações do escoamento e não produz coeficientes aerodinâmicos validados.',
      required: [
        'Geometria fechada, congelada e identificada',
        'Velocidade, altitude, densidade, viscosidade, ângulos e rajadas',
        'Domínio, condições de contorno e interação com a propulsão',
        'Malha, modelo de turbulência, solver, versão e critérios de convergência'
      ],
      outputs: [
        'Futuramente: CL, CD e CM por condição definida',
        'Futuramente: pressão, velocidade, separação e esteira',
        'Futuramente: interação asa, corpo e propulsão',
        'Sempre: método, configuração, convergência e incerteza junto do resultado'
      ],
      evidence: [
        'Independência de malha e convergência registrada',
        'Verificação numérica e repetibilidade',
        'Correlação com túnel de vento ou ensaio apropriado',
        'Revisão de especialista em aerodinâmica'
      ],
      ownerWork: 'Definir as perguntas e condições de voo, manter a geometria correta, organizar arquivos e comparar somente casos equivalentes; não escolher parâmetros do solver por adivinhação.',
      professionals: ['Aerodinamicista', 'Especialista em CFD', 'Engenheiro de ensaios aerodinâmicos'],
      dependencies: ['Modelo digital versionado', 'Propulsão caracterizada', 'Condições da missão'],
      canSay: 'Há uma prévia visual de fluxo e uma lista estruturada do que falta para uma análise aerodinâmica.',
      cannotSay: 'Que a asa sustenta o veículo, que o arrasto é aceitável, que o conceito é estável ou que a autonomia foi demonstrada.',
      next: 'Fechar uma matriz de casos aerodinâmicos e o contrato de importação de resultados antes de conectar qualquer solver externo.',
      relatedMode: 'AERO',
      relatedLabel: 'VER PRÉVIA AERODINÂMICA'
    },
    FEA_STRUCTURE: {
      code: 'CX-ENG-03 · ESTRUTURAS / FEA',
      title: 'Estruturas e FEA',
      status: 'FEA NÃO EXECUTADA',
      modelLevel: 'M1',
      evidenceLevel: 'E0',
      stageIndex: 0,
      validated: false,
      question: 'Por onde as cargas passam e quais tensões, deformações, modos de falha e margens existem em cada caso?',
      current: 'O Condor mostra geometria e caminhos de carga apenas visuais. Não há malha estrutural, materiais certificados, contatos, juntas ou solução por elementos finitos.',
      required: [
        'Geometria estrutural, materiais e propriedades rastreáveis',
        'Juntas, fixações, contatos, restrições e tolerâncias',
        'Casos de carga de voo, pouso, rajada e falha',
        'Malha, solver, convergência e fatores adotados'
      ],
      outputs: [
        'Futuramente: tensão, deformação e deslocamento',
        'Futuramente: flambagem, modos próprios e fadiga',
        'Futuramente: margem por componente e caso de carga',
        'Resultado sempre vinculado à geometria e ao material analisados'
      ],
      evidence: [
        'Convergência de malha e checagens manuais independentes',
        'Certificados e ensaios de material',
        'Ensaios de cupom, componente e conjunto',
        'Revisão formal de engenheiro estrutural'
      ],
      ownerWork: 'Manter materiais, revisões, juntas e casos de carga organizados; garantir que cada resultado aponta para a peça correta; registrar dúvidas para o engenheiro estrutural.',
      professionals: ['Engenheiro estrutural', 'Especialista em materiais', 'Engenheiro de fabricação', 'Equipe de testes estruturais'],
      dependencies: ['Cargas aerodinâmicas', 'Massa e inércia', 'Geometria e processo de fabricação'],
      canSay: 'A estrutura e os caminhos de carga estão mapeados como temas de estudo.',
      cannotSay: 'Que a estrutura suporta voo, impacto, fadiga ou pouso; um mapa colorido futuro também não será autorização de fabricação.',
      next: 'Criar um catálogo controlado de casos de carga e o contrato do modelo estrutural antes de importar qualquer FEA.',
      relatedMode: 'STRUCTURE',
      relatedLabel: 'VER ESTRUTURA CONCEITUAL'
    },
    SIX_DOF: {
      code: 'CX-ENG-04 · DINÂMICA DE VOO',
      title: 'Dinâmica de Voo e Controle 6-DoF',
      status: 'SEM MODELO 6-DOF',
      modelLevel: 'M2',
      evidenceLevel: 'E1',
      stageIndex: 0,
      validated: false,
      question: 'O sistema permanece controlável ao longo do tempo durante decolagem, transição, cruzeiro, falhas e pouso?',
      current: 'As engines atuais somam forças, momentos e autoridade estática a partir das entradas informadas. Não calculam trajetória no tempo, estabilidade completa, sensores, atuadores ou leis de controle verificadas.',
      required: [
        'Massa, centro de gravidade e tensor completo de inércia',
        'Coeficientes e derivadas aerodinâmicas por configuração',
        'Mapas, resposta, atraso e saturação dos propulsores',
        'Sensores, atuadores, leis de controle, vento e contato com o solo'
      ],
      outputs: [
        'Futuramente: posição, velocidade, atitude e taxas no tempo',
        'Futuramente: estabilidade, controle, transição e resposta a falhas',
        'Futuramente: saturações, margens e envelope definido',
        'Hoje: somente equilíbrio e autoridade estática simplificados'
      ],
      evidence: [
        'Equações, referenciais e unidades verificados',
        'Casos de trim e testes unitários de conservação',
        'Implementação independente para comparação',
        'SIL/HIL e correlação progressiva com ensaios controlados'
      ],
      ownerWork: 'Descrever as fases, perturbações e falhas que precisam ser estudadas; manter entradas e resultados rastreáveis; deixar a modelagem e revisão das leis de controle com profissionais qualificados.',
      professionals: ['Engenheiro de dinâmica de voo', 'Engenheiro de controle', 'Especialista em aviônica', 'Engenheiro de ensaios'],
      dependencies: ['Aerodinâmica', 'Massa e inércia', 'Propulsão', 'Sensores e atuadores'],
      canSay: 'O Condor possui uma triagem estática de forças, momentos e alocação de controle para entradas informadas.',
      cannotSay: 'Que consegue decolar, pairar, transicionar, permanecer estável, cruzar ou pousar com segurança.',
      next: 'Definir referenciais, vetor de estado, equações, entradas e casos de teste de um futuro modelo 6-DoF — sem chamar a triagem atual de voo.',
      relatedMode: 'MISSION',
      relatedLabel: 'VER FASES DA MISSÃO'
    },
    FIRE_THERMAL: {
      code: 'CX-ENG-05 · TÉRMICO / INCÊNDIO',
      title: 'Térmico e Incêndio',
      status: 'SEM MODELO DE INCÊNDIO',
      modelLevel: 'M2',
      evidenceLevel: 'E1',
      stageIndex: 0,
      validated: false,
      question: 'Como o calor evolui, alcança o corpo e pode iniciar ou propagar falhas térmicas e incêndio em cada cenário?',
      current: 'Existe uma triagem abstrata por potência informada, distância e resposta térmica concentrada. As zonas visuais representam intensidade conceitual; não são raios físicos de perigo nem um modelo de queimadura ou incêndio.',
      required: [
        'Fontes de calor no tempo, materiais, contatos e isolamento',
        'Geometria térmica, fluxo de ar e sistema de resfriamento',
        'Química e arquitetura da energia, BMS e modos de falha',
        'Ignição, propagação, gases, toxicidade e limites de exposição humana'
      ],
      outputs: [
        'Futuramente: temperatura e fluxo de calor no tempo',
        'Futuramente: propagação e contenção por cenário definido',
        'Futuramente: tempo disponível para detecção e resposta',
        'Hoje: potência informada, folgas geométricas e lacunas'
      ],
      evidence: [
        'Sensores calibrados e propriedades térmicas rastreáveis',
        'Calorimetria e ensaios específicos de materiais e energia',
        'Correlação do modelo com ensaios protegidos',
        'Revisão de especialista térmico e de segurança contra incêndio'
      ],
      ownerWork: 'Catalogar fontes de calor, materiais, distâncias e cenários de falha; nunca converter a esfera visual em distância segura; organizar evidências para especialistas.',
      professionals: ['Engenheiro térmico', 'Especialista em energia/baterias', 'Especialista em incêndio', 'Especialista em proteção humana'],
      dependencies: ['Energia', 'Propulsão', 'Materiais', 'Fluxo aerodinâmico'],
      canSay: 'Há uma triagem térmica abstrata que ajuda a identificar onde faltam dados e onde investigar primeiro.',
      cannotSay: 'Que não haverá queimadura, fogo, fumaça, toxicidade, thermal runaway ou propagação de falha.',
      next: 'Separar cenários de perigo e montar uma rede térmica inicial; incêndio continua bloqueado até existir método e ensaio próprios.',
      relatedMode: 'THERMAL',
      relatedLabel: 'VER TRIAGEM TÉRMICA'
    },
    FLUTTER: {
      code: 'CX-ENG-06 · AEROELASTICIDADE',
      title: 'Flutter e Aeroelasticidade',
      status: 'SEM ANÁLISE DE FLUTTER',
      modelLevel: 'M0',
      evidenceLevel: 'E0',
      stageIndex: 0,
      validated: false,
      question: 'A flexão e a torção das asas podem se acoplar ao ar e às excitações até gerar uma oscilação instável?',
      current: 'Nenhuma análise de flutter ou aeroelasticidade está implementada. CFD e FEA isolados, quando existirem, também não provarão ausência de flutter.',
      required: [
        'Modos, rigidez, amortecimento e distribuição de massa',
        'Aerodinâmica não estacionária por configuração',
        'Folgas, dobradiças, balanceamento e excitações da propulsão',
        'Envelope de velocidade, altitude, densidade e configuração da asa'
      ],
      outputs: [
        'Futuramente: frequência e amortecimento por velocidade',
        'Futuramente: modos acoplados e sensibilidades',
        'Futuramente: limite previsto com incerteza declarada',
        'Nenhuma velocidade-limite será inventada nesta tela'
      ],
      evidence: [
        'Modelo modal estrutural correlacionado',
        'Ensaio de vibração em solo',
        'Método aeroelástico verificado',
        'Revisão especializada e expansão de envelope controlada'
      ],
      ownerWork: 'Garantir que a configuração da asa e a distribuição de massa estejam registradas; organizar o plano de evidências; não definir envelope de velocidade sem análise especializada.',
      professionals: ['Engenheiro de aeroelasticidade', 'Engenheiro estrutural', 'Aerodinamicista', 'Equipe de ensaios de voo'],
      dependencies: ['FEA modal', 'Aerodinâmica não estacionária', 'Massa e rigidez', 'Configuração da asa'],
      canSay: 'Flutter foi reconhecido como uma disciplina crítica e está explicitamente bloqueado por falta de modelo e evidência.',
      cannotSay: 'Que a asa está livre de flutter ou que existe um envelope de velocidade seguro.',
      next: 'Planejar o modelo modal e o ensaio de vibração em solo antes de qualquer expansão de envelope.',
      relatedMode: 'STRUCTURE',
      relatedLabel: 'VER GEOMETRIA DA ASA'
    },
    PROPULSION_QUALIFICATION: {
      code: 'CX-ENG-07 · PROPULSÃO',
      title: 'Arquitetura e Qualificação da Propulsão',
      status: 'TECNOLOGIA NÃO SELECIONADA',
      modelLevel: 'M2',
      evidenceLevel: 'E1',
      stageIndex: 1,
      validated: false,
      question: 'Qual candidato oferece massa, volume, empuxo, controle, calor, consumo e falhas compatíveis com a missão e a integração?',
      current: 'O Placement Lab compara fontes abstratas em posições candidatas e recalcula massa, CG, forças, momentos, controle estático, calor, energia e falhas simplificadas. Conceitos A, B e C não são motores escolhidos.',
      required: [
        'Tecnologia e configuração exatas de cada candidato',
        'Massa, volume, empuxo contínuo/máximo e resposta medidos',
        'Mapas de potência, eficiência, calor, ruído e vibração',
        'Interfaces, arrasto de instalação, falhas e condições ambientais'
      ],
      outputs: [
        'Hoje: comparação paramétrica e triagem de posicionamento L2',
        'Futuramente: mapa operacional qualificado por condição',
        'Futuramente: limites de fase e restrições de integração',
        'Futuramente: decisão de avançar um candidato para novo estudo'
      ],
      evidence: [
        'Dados brutos de bancada com instrumentos calibrados',
        'Repetibilidade, incerteza e configuração do artigo testado',
        'Curvas contínuas, transientes e falhas por ambiente',
        'Revisão independente de propulsão, elétrica, térmica e segurança'
      ],
      ownerWork: 'Comparar candidatos com os mesmos critérios, registrar a origem de todos os dados e manter “dados necessários” onde não há medição; não escolher tecnologia por aparência.',
      professionals: ['Engenheiro de propulsão', 'Engenheiro elétrico/energia', 'Engenheiro térmico', 'Equipe de bancada e segurança'],
      dependencies: ['Missão', 'Energia', 'Aerodinâmica', 'Estrutura', 'Térmico', 'Controle'],
      canSay: 'Existem candidatos abstratos e uma triagem L2 para comparar efeitos de posicionamento com as entradas fornecidas.',
      cannotSay: 'Que uma tecnologia foi escolhida, integrada, qualificada, certificada ou aprovada para voo.',
      next: 'Criar uma ficha de dados formal por candidato e um plano de ensaio de bancada protegido, sem teste preso ao corpo.',
      relatedMode: 'PROPULSION',
      relatedLabel: 'ABRIR PLACEMENT LAB',
      openLab: true
    },
    FLIGHT_SAFETY: {
      code: 'CX-ENG-08 · SEGURANÇA DE VOO',
      title: 'Segurança de Voo Humano',
      status: 'VOO HUMANO BLOQUEADO',
      modelLevel: 'M1',
      evidenceLevel: 'E0',
      stageIndex: 0,
      validated: false,
      question: 'Quais perigos podem ferir uma pessoa e quais evidências, mitigações e autorizações seriam exigidas antes de qualquer voo?',
      current: 'Há volumes conceituais de proteção, retirada estática de unidades e índices heurísticos de triagem. Eles servem para priorizar pendências; não medem sobrevivência e não aprovam um gate de segurança.',
      required: [
        'Conceito de operação e registro formal de perigos',
        'FHA, FMEA, FTA, causas comuns e taxas justificadas',
        'Recuperação, aborto, impacto, resgate, fatores humanos e emergência',
        'Requisitos regulatórios, evidências de teste e decisões externas'
      ],
      outputs: [
        'Registro de perigos e objetivos de segurança',
        'Rastreabilidade entre perigo, requisito, mitigação e evidência',
        'Pendências e decisão humana por gate claramente registrada',
        'Autorização permanece externa ao Condor'
      ],
      evidence: [
        'Ensaios progressivos não tripulados e configuração rastreável',
        'Mitigações verificadas e falhas testadas',
        'Revisão de segurança independente',
        'Aceite regulatório e autorização específica quando aplicável'
      ],
      ownerWork: 'Manter o registro de perigos vivo, cobrar evidências e parar o avanço quando faltar uma prova; nunca usar uma pontuação do Condor como autorização de teste humano.',
      professionals: ['Engenheiro de segurança e certificação', 'Engenheiro-chefe', 'Engenheiro de ensaios de voo', 'Piloto de testes qualificado', 'Autoridade aeronáutica'],
      dependencies: ['Todas as disciplinas', 'Plano de testes', 'Revisões independentes', 'Autorizações externas'],
      canSay: 'Os perigos e dados ausentes podem ser organizados e acompanhados por gates de revisão.',
      cannotSay: 'Que uma pessoa pode decolar, transicionar, cruzar ou pousar com segurança; esta tela não é autorização de voo.',
      next: 'Abrir um registro formal de perigos ligado aos requisitos e iniciar contato com especialistas e autoridade competente antes de planejar teste humano.',
      relatedMode: 'SAFETY',
      relatedLabel: 'VER VOLUME DE SEGURANÇA'
    }
  };

  const nav = root.querySelector('#cxEngineeringNav');
  const code = root.querySelector('#cxEngineeringCode');
  const title = root.querySelector('#cxEngineeringTitle');
  const status = root.querySelector('#cxEngineeringStatus');
  const levels = root.querySelector('#cxEngineeringLevels');
  const question = root.querySelector('#cxEngineeringQuestion');
  const maturity = root.querySelector('#cxEngineeringMaturity');
  const cards = root.querySelector('#cxEngineeringCards');
  const claims = root.querySelector('#cxEngineeringClaims');
  const next = root.querySelector('#cxEngineeringNext');
  const actions = root.querySelector('#cxEngineeringActions');

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function list(items) {
    return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
  }

  function card(label, content, note = '', extraClass = '') {
    const body = Array.isArray(content) ? list(content) : `<p>${escapeHtml(content)}</p>`;
    return `<section class="cx-engineering-card ${extraClass}"><header><strong>${escapeHtml(label)}</strong><span>${escapeHtml(note)}</span></header>${body}</section>`;
  }

  function renderWorkspace(key, moveFocus = false) {
    const workspace = WORKSPACES[key] || WORKSPACES.DIGITAL_TWIN;
    code.textContent = workspace.code;
    title.textContent = workspace.title;
    status.textContent = workspace.status;
    levels.textContent = `MODELO ${workspace.modelLevel} · EVIDÊNCIA ${workspace.evidenceLevel}`;
    question.textContent = workspace.question;
    next.textContent = workspace.next;

    maturity.innerHTML = MATURITY_STAGES.map((label, index) => {
      const state = index < workspace.stageIndex ? 'reached' : index === workspace.stageIndex ? 'current' : '';
      return `<span class="${state}">${index + 1}. ${escapeHtml(label)}</span>`;
    }).join('');

    cards.innerHTML = [
      card('O QUE EXISTE HOJE', workspace.current, 'VERDADE ATUAL'),
      card('DADOS NECESSÁRIOS', workspace.required, 'SEM VALORES INVENTADOS', 'warning'),
      card('O QUE PODERÁ ENTREGAR', workspace.outputs, 'SOMENTE NO ESCOPO'),
      card('EVIDÊNCIA PARA AVANÇAR', workspace.evidence, 'FONTE + MÉTODO + REVISÃO'),
      card('SEU TRABALHO NESTA ÁREA', workspace.ownerWork, 'ORGANIZAR + COBRAR PROVAS'),
      card('QUEM PRECISA PARTICIPAR', workspace.professionals, 'REVISÃO PROFISSIONAL'),
      card('DEPENDÊNCIAS', workspace.dependencies, 'OUTRAS ÁREAS')
    ].join('');

    claims.innerHTML = `
      <section class="cx-engineering-claim"><strong>PODE AFIRMAR AGORA</strong><p>${escapeHtml(workspace.canSay)}</p></section>
      <section class="cx-engineering-claim deny"><strong>NÃO PODE AFIRMAR</strong><p>${escapeHtml(workspace.cannotSay)}</p></section>
    `;

    const secondaryAction = workspace.openLab
      ? '<button type="button" class="secondary" data-cx-engineering-action="STUDIO">VER VOLUMES NO STUDIO</button>'
      : '';
    actions.innerHTML = `<button type="button" data-cx-engineering-action="RELATED">${escapeHtml(workspace.relatedLabel)}</button>${secondaryAction}`;

    nav.querySelectorAll('[data-cx-workspace]').forEach((button) => {
      const active = button.dataset.cxWorkspace === key;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
    });

    root.dataset.activeWorkspace = key;
    window.dispatchEvent(new CustomEvent('condor-x-area-changed', {
      detail: {
        area: key,
        validationState: 'NOT_VALIDATED',
        modelLevel: workspace.modelLevel,
        evidenceLevel: workspace.evidenceLevel,
        claimBoundaries: CLAIM_BOUNDARIES
      }
    }));

    if (moveFocus) title.focus?.({ preventScroll: true });
  }

  function openRelated(action) {
    const key = root.dataset.activeWorkspace || 'DIGITAL_TWIN';
    const workspace = WORKSPACES[key];
    if (!workspace) return;

    if (workspace.openLab && action === 'RELATED') {
      const lab = document.getElementById('cxPropulsionLab');
      lab?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      window.dispatchEvent(new Event('condor-x-resize'));
      return;
    }

    const studio = document.getElementById('cxDesignStudio');
    const mode = action === 'STUDIO' ? 'PROPULSION' : workspace.relatedMode;
    document.querySelector(`#cxDesignStudio [data-cx-mode="${mode}"]`)?.click();
    studio?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.dispatchEvent(new Event('condor-x-resize'));
  }

  nav.addEventListener('click', (event) => {
    const button = event.target.closest('[data-cx-workspace]');
    if (!button) return;
    renderWorkspace(button.dataset.cxWorkspace);
  });

  nav.addEventListener('keydown', (event) => {
    if (!['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    const buttons = [...nav.querySelectorAll('[data-cx-workspace]')];
    const currentIndex = Math.max(0, buttons.indexOf(document.activeElement));
    let nextIndex = currentIndex;
    if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = buttons.length - 1;
    else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % buttons.length;
    else nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;
    event.preventDefault();
    buttons[nextIndex].focus();
    renderWorkspace(buttons[nextIndex].dataset.cxWorkspace);
  });

  actions.addEventListener('click', (event) => {
    const button = event.target.closest('[data-cx-engineering-action]');
    if (button) openRelated(button.dataset.cxEngineeringAction);
  });

  document.getElementById('cxOpenEngineeringHub')?.addEventListener('click', () => {
    root.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  window.addEventListener('condor-x-area-request', (event) => {
    const area = String(event.detail?.area || '').toUpperCase();
    const aliases = {
      OVERVIEW: 'DIGITAL_TWIN',
      STUDIO: 'DIGITAL_TWIN',
      AERO: 'CFD_AERO',
      STRUCTURE: 'FEA_STRUCTURE',
      FLIGHT_CONTROL: 'SIX_DOF',
      THERMAL_FIRE: 'FIRE_THERMAL',
      PROPULSION: 'PROPULSION_QUALIFICATION',
      SAFETY: 'FLIGHT_SAFETY'
    };
    const key = WORKSPACES[area] ? area : aliases[area];
    if (!key) return;
    renderWorkspace(key);
    root.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  renderWorkspace('DIGITAL_TWIN');
}
