import { CondorPropulsion3D } from './modeler-3d.js';

const root = document.getElementById('cxPropulsionLab');

if (root && !root.dataset.ready) {
  root.dataset.ready = 'true';
  const $ = (id) => document.getElementById(id);
  const tabs = $('cxPropulsionLayoutTabs'); const vehicleFields = $('cxPropulsionVehicleFields');
  const unitList = $('cxPropulsionUnitList'); const unitFields = $('cxPropulsionUnitFields');
  const zoneGrid = $('cxPropulsionZoneGrid'); const dashboard = $('cxPropulsionDashboard');
  const viewportState = $('cxPropulsionViewportState');
  const decision = $('cxPropulsionDecision'); const missing = $('cxPropulsionMissing');
  const failures = $('cxPropulsionFailures'); const mission = $('cxPropulsionMission');
  const control = $('cxPropulsionControl'); const evidence = $('cxPropulsionEvidence'); const delta = $('cxPropulsionDelta');
  let metadata = { candidateZones: [], controlGroups: [] }; let layouts = []; let layout = null; let analysis = null;
  let previousAnalysis = null; let selectedUnitId = null; let analyzeTimer = 0; let bodyParts = [];
  let analyzeRevision = 0; let loadPromise = null;
  const toggles = { zones: true, vectors: true, moments: true, flow: false, thermal: false, loadPaths: false };
  const viewer = new CondorPropulsion3D($('cxPropulsionViewport'), {
    onUnitSelect: (id) => selectUnit(id),
    onUnitMove: (id, position) => moveUnit(id, position, 'FREE_POSITION'),
  });

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const number = (value) => value === '' || value == null ? null : Number(value);
  const slug = (value) => String(value || '').normalize('NFKD').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-|-$/g, '').toLowerCase().slice(0, 70) || `layout-${Date.now()}`;
  const value = (input) => input == null ? '' : input;
  // Contrato interno: DATA REQUIRED continua sendo null; a apresentação é PT-BR.
  const format = (input, unit = '') => input == null ? 'DADOS NECESSÁRIOS' : `${Number(input).toLocaleString('pt-BR', { maximumFractionDigits: 3 })}${unit}`;

  const displayLabels = {
    ACTIVE: 'ATIVA', INACTIVE: 'INATIVA', FAILED: 'COM FALHA', DATA_REQUIRED: 'DADOS NECESSÁRIOS', LOW: 'BAIXA', MEDIUM: 'MÉDIA', HIGH: 'ALTA',
    NOT_EVALUATED: 'NÃO AVALIADA', FAVORABLE: 'FAVORÁVEL', COMPROMISES: 'COM COMPENSAÇÕES', HIGH_RISK: 'ALTO RISCO', REJECTED: 'REJEITADA',
    PASS: 'ATENDIDA', FAIL: 'NÃO ATENDIDA', INSUFFICIENT_DATA: 'DADOS INSUFICIENTES', CONTROL_AUTHORITY_INSUFFICIENT: 'AUTORIDADE DE CONTROLE INSUFICIENTE',
    RECOVERABLE: 'RECUPERÁVEL', DEGRADED: 'DEGRADADA', CRITICAL: 'CRÍTICA', UNRECOVERABLE: 'IRRECUPERÁVEL',
    NONE: 'NENHUMA', BALANCED: 'EQUILIBRADA', CENTRALIZED: 'CENTRALIZADA', DISTRIBUTED: 'DISTRIBUÍDA', DORSAL_DOMINANT: 'DOMINANTE DORSAL',
    LATERAL_DISTRIBUTED: 'DISTRIBUÍDA LATERALMENTE', WING_ASSISTED: 'ASSISTIDA PELAS ASAS', HYBRID: 'HÍBRIDA',
    MINIMUM_MASS: 'MENOR MASSA', MINIMUM_DRAG: 'MENOR ARRASTO', MINIMUM_PILOT_HEAT: 'MENOR CALOR SOBRE O PILOTO', MINIMUM_ENERGY: 'MENOR CONSUMO DE ENERGIA',
    MAXIMUM_CONTROL: 'MÁXIMO CONTROLE', MAXIMUM_REDUNDANCY: 'MÁXIMA REDUNDÂNCIA', MAXIMUM_ENDURANCE: 'MÁXIMA AUTONOMIA',
    PRIMARY: 'PRINCIPAL', SECONDARY: 'SECUNDÁRIO', CONTROL: 'CONTROLE', CRUISE: 'CRUZEIRO', TRANSITION: 'TRANSIÇÃO', EMERGENCY: 'EMERGÊNCIA',
    TAKEOFF: 'DECOLAGEM', LANDING: 'POUSO', MODELED: 'MODELADO', INSUFFICIENT_DATA_OR_AUTHORITY: 'DADOS OU AUTORIDADE DE CONTROLE INSUFICIENTES',
    INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT: 'DADOS INSUFICIENTES PARA DETERMINAR A CONFIGURAÇÃO DE PROPULSÃO',
    CANDIDATE_FOR_FURTHER_SIMULATION: 'CANDIDATA A SIMULAÇÕES ADICIONAIS', PARETO_CANDIDATES: 'CANDIDATAS DE PARETO', INSUFFICIENT_ALLOWED_ZONES: 'ZONAS PERMITIDAS INSUFICIENTES',
  };
  const display = (input) => displayLabels[String(input || '').toUpperCase()] || String(input || '').replaceAll('_', ' ');
  const zoneLabels = {
    'PZ-DORSAL-CENTER': 'DORSAL · CENTRO', 'PZ-DORSAL-LEFT': 'DORSAL · ESQUERDA', 'PZ-DORSAL-RIGHT': 'DORSAL · DIREITA',
    'PZ-SHOULDER-LEFT': 'OMBRO · ESQUERDA', 'PZ-SHOULDER-RIGHT': 'OMBRO · DIREITA',
    'PZ-TORSO-LATERAL-LEFT': 'TRONCO LATERAL · ESQUERDA', 'PZ-TORSO-LATERAL-RIGHT': 'TRONCO LATERAL · DIREITA',
    'PZ-PELVIS-LEFT': 'PELVE · ESQUERDA', 'PZ-PELVIS-RIGHT': 'PELVE · DIREITA',
    'PZ-UPPER-LEG-LEFT': 'COXA · ESQUERDA', 'PZ-UPPER-LEG-RIGHT': 'COXA · DIREITA',
    'PZ-LOWER-LEG-LEFT': 'PERNA INFERIOR · ESQUERDA', 'PZ-LOWER-LEG-RIGHT': 'PERNA INFERIOR · DIREITA',
    'PZ-FOOT-LEFT': 'PÉ · ESQUERDA', 'PZ-FOOT-RIGHT': 'PÉ · DIREITA',
    'PZ-WING-ROOT-LEFT': 'RAIZ DA ASA · ESQUERDA', 'PZ-WING-ROOT-RIGHT': 'RAIZ DA ASA · DIREITA',
    'PZ-WING-MID-LEFT': 'MEIO DA ASA · ESQUERDA', 'PZ-WING-MID-RIGHT': 'MEIO DA ASA · DIREITA',
    UNPLACED: 'NÃO POSICIONADA', FREE_POSITION: 'POSIÇÃO LIVRE',
  };
  const zoneLabel = (input) => zoneLabels[input] || String(input || '').replace('PZ-', '').replaceAll('-', ' ');
  function commonModeLabel(input) {
    const value = String(input || '');
    if (value === 'LEFT_SIDE') return 'LADO ESQUERDO';
    if (value === 'RIGHT_SIDE') return 'LADO DIREITO';
    if (value.startsWith('REDUNDANCY_')) return `REDUNDÂNCIA · ${value.slice(11).replaceAll('_', ' ')}`;
    if (value.endsWith('_GROUP')) return `GRUPO · ${display(value.slice(0, -6))}`;
    return display(value);
  }
  const evidenceLabels = {
    'Simplified Condor X abstract model': 'Modelo abstrato simplificado do Condor X',
    'Coupled recalculation: mass -> CG -> inertia -> thrust/moments -> placement/thermal/aero -> control/failure -> mission/safety': 'Recálculo acoplado: massa → CG → inércia → empuxo/momentos → posicionamento/térmico/aerodinâmica → controle/falha → missão/segurança',
    'Abstract propulsion only': 'Apenas propulsão abstrata', 'Configured inputs remain authoritative': 'As entradas configuradas permanecem determinantes',
    'No CFD, FEA or experimental validation': 'Sem validação por CFD, FEA ou experimento',
  };
  const evidenceLabel = (input) => evidenceLabels[input] || display(input);
  const layoutLabel = (input) => String(input || '').replace(/^AUTO LAYOUT /i, 'CONFIGURAÇÃO AUTOMÁTICA ').replace(/^LAYOUT /i, 'CONFIGURAÇÃO ');
  const missingLabels = {
    'VEHICLE DRY MASS': 'Massa seca do veículo', 'DRY CG X': 'CG seco no eixo X', 'DRY CG Y': 'CG seco no eixo Y', 'DRY CG Z': 'CG seco no eixo Z',
    'ENERGY CAPACITY': 'Capacidade de energia', 'ENERGY RESERVE': 'Reserva de energia', 'WING AREA': 'Área alar', 'LIFT COEFFICIENT': 'Coeficiente de sustentação',
    'BODY DRAG AREA': 'Área de arrasto do corpo', 'AIR DENSITY': 'Densidade do ar', 'CRUISE SPEED': 'Velocidade de cruzeiro',
    'CG ENVELOPE RADIUS': 'Raio permitido do envelope do CG',
    'ENERGY STORAGE ZONE': 'Zona de armazenamento de energia', 'AT LEAST ONE ABSTRACT PROPULSION UNIT': 'Pelo menos uma unidade abstrata de propulsão',
    'M01 PHASE DURATIONS MUST SUM TO TARGET': 'A soma das fases M01 deve corresponder à meta de 02:00:00',
    PLACEMENT: 'Posicionamento', MASS: 'Massa', 'MAX THRUST': 'Empuxo máximo', 'CONTINUOUS THRUST': 'Empuxo contínuo', 'POWER COMMAND': 'Comando de potência',
    'MINIMUM STABLE OUTPUT': 'Saída mínima estável', 'RESPONSE TIME': 'Tempo de resposta',
    'THERMAL OUTPUT': 'Potência térmica', 'THERMAL RADIUS': 'Raio térmico', 'FRONTAL AREA': 'Área frontal', 'DRAG COEFFICIENT': 'Coeficiente de arrasto',
    'THERMAL RESISTANCE': 'Resistência térmica', 'THERMAL TIME CONSTANT': 'Constante de tempo térmica', 'COOLING EFFECTIVENESS': 'Eficácia do resfriamento',
    'OPERATIONAL LIMIT': 'Limite operacional', 'STRUCTURAL SUPPORT': 'Suporte estrutural', 'MAINTENANCE ACCESS': 'Acesso de manutenção',
    'ENERGY CONSUMPTION CURVE': 'Curva de consumo de energia', 'INSTALLATION ENVELOPE': 'Envelope de instalação', 'SERVICE ENVELOPE': 'Envelope de manutenção',
    'CONTROL GROUP': 'Grupo de controle', 'REDUNDANCY GROUP': 'Grupo de redundância', CONFIDENCE: 'Confiança da entrada',
  };
  function missingLabel(input) {
    if (missingLabels[input]) return missingLabels[input];
    const phase = String(input).match(/^M01 (TAKEOFF|TRANSITION|CRUISE|LANDING) DURATION$/);
    if (phase) return `Duração M01 · ${display(phase[1])}`;
    const unit = String(input).match(/^(.+?) (PLACEMENT|MASS|MAX THRUST|CONTINUOUS THRUST|POWER COMMAND|MINIMUM STABLE OUTPUT|RESPONSE TIME|THERMAL OUTPUT|THERMAL RADIUS|THERMAL RESISTANCE|THERMAL TIME CONSTANT|COOLING EFFECTIVENESS|OPERATIONAL LIMIT|FRONTAL AREA|DRAG COEFFICIENT|STRUCTURAL SUPPORT|MAINTENANCE ACCESS|ENERGY CONSUMPTION CURVE|INSTALLATION ENVELOPE|SERVICE ENVELOPE|CONTROL GROUP|REDUNDANCY GROUP|CONFIDENCE)$/);
    if (unit) return `${unit[1]} · ${missingLabels[unit[2]]}`;
    return display(input);
  }

  function broadcastState() {
    window.dispatchEvent(new CustomEvent('condor-propulsion-state', {
      detail: { layout: layout ? clone(layout) : null, analysis: analysis ? clone(analysis) : null },
    }));
  }

  function commandResult(action, ok, message) {
    window.dispatchEvent(new CustomEvent('condor-propulsion-command-result', { detail: { action, ok, message } }));
  }

  async function request(url, options = {}) {
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.erro || 'Falha no Propulsion Placement Lab.');
    return data;
  }

  function blankUnit(index) {
    return {
      id: `unit-${crypto.randomUUID().slice(0, 8)}`, name: `UNIDADE ABSTRATA ${index + 1}`, propulsionType: 'ABSTRACT_THRUST_SOURCE',
      mass: null, positionX: 0, positionY: 2, positionZ: -1.5,
      orientationPitch: 0, orientationYaw: 0, orientationRoll: 0, maxThrust: null, continuousThrust: null,
      minimumStableOutput: null, responseTime: null, efficiencyCurve: [], energyConsumptionCurve: [], thermalOutput: null,
      thermalRadiusEstimate: null, thermalResistance: null, thermalTimeConstant: null, coolingEffectiveness: null,
      airMassFlowReference: null, operationalLimit: null, failureProbabilityPlaceholder: null, mountZone: 'UNPLACED',
      controlGroup: ['PRIMARY'], redundancyGroup: 'unassigned', status: 'INACTIVE', confidenceLevel: 'DATA_REQUIRED',
      powerCommand: null, frontalArea: null, dragCoefficient: null, structuralSupportScore: null, maintenanceAccessScore: null,
      installationEnvelope: { length: null, width: null, height: null }, serviceEnvelope: { length: null, width: null, height: null },
    };
  }

  function currentUnit() { return layout?.units?.find((unit) => unit.id === selectedUnitId) || null; }

  function renderTabs() {
    tabs.innerHTML = layouts.map((item) => `<button type="button" data-layout-id="${escapeHtml(item.id)}" class="${layout?.id === item.id ? 'active' : ''}">${escapeHtml(layoutLabel(item.name))}</button>`).join('');
  }

  const vehicleDefinitions = [
    ['name', 'NOME DA CONFIGURAÇÃO', null, null, 'text'], ['preset', 'PREDEFINIÇÃO DA ARQUITETURA', '', 1, 'preset'], ['objective', 'OBJETIVO DE OTIMIZAÇÃO', '', 1, 'objective'], ['vehicle.dryMass', 'MASSA SECA DO VEÍCULO', 'kg'],
    ['vehicle.dryCg.x', 'CG SECO X', 'm'], ['vehicle.dryCg.y', 'CG SECO Y', 'm'], ['vehicle.dryCg.z', 'CG SECO Z', 'm'],
    ['vehicle.energyCapacityWh', 'CAPACIDADE DE ENERGIA', 'Wh'], ['vehicle.energyReservePercent', 'RESERVA DE ENERGIA', '%'],
    ['vehicle.wingArea', 'ÁREA ALAR', 'm²'], ['vehicle.liftCoefficient', 'COEFICIENTE DE SUSTENTAÇÃO', ''],
    ['vehicle.bodyDragArea', 'ÁREA DE ARRASTO DO CORPO', 'm²'], ['vehicle.airDensity', 'DENSIDADE DO AR', 'kg/m³'],
    ['vehicle.cruiseSpeed', 'VELOCIDADE DE CRUZEIRO', 'm/s'], ['vehicle.cgEnvelopeRadius', 'RAIO DO ENVELOPE DO CG', 'm'],
    ['vehicle.energyStorageZone.x', 'ZONA DE ENERGIA X', 'm'], ['vehicle.energyStorageZone.y', 'ZONA DE ENERGIA Y', 'm'],
    ['vehicle.energyStorageZone.z', 'ZONA DE ENERGIA Z', 'm'], ['vehicle.energyStorageZone.radius', 'RAIO DA ZONA DE ENERGIA', 'm'],
    ['mission.phases.TAKEOFF', 'DURAÇÃO DA DECOLAGEM', 'min', 60], ['mission.phases.TRANSITION', 'DURAÇÃO DA TRANSIÇÃO', 'min', 60],
    ['mission.phases.CRUISE', 'DURAÇÃO DO CRUZEIRO', 'min', 60], ['mission.phases.LANDING', 'DURAÇÃO DO POUSO', 'min', 60],
  ];

  function getPath(path) {
    const dryCgAxis = path.match(/^vehicle\.dryCg\.([xyz])$/)?.[1];
    if (dryCgAxis && !layout?.vehicle?.dryCgProvided?.[dryCgAxis]) return null;
    return path.split('.').reduce((current, key) => current?.[key], layout);
  }
  function setPath(path, raw, multiplier = 1) {
    const parts = path.split('.'); let current = layout;
    parts.slice(0, -1).forEach((key) => { if (!current[key] || typeof current[key] !== 'object') current[key] = {}; current = current[key]; });
    current[parts.at(-1)] = ['name', 'preset', 'objective'].includes(path) ? String(raw).slice(0, 120) : (number(raw) == null ? null : number(raw) * multiplier);
    const dryCgAxis = path.match(/^vehicle\.dryCg\.([xyz])$/)?.[1];
    if (dryCgAxis) {
      if (!layout.vehicle.dryCgProvided) layout.vehicle.dryCgProvided = { x: false, y: false, z: false };
      layout.vehicle.dryCgProvided[dryCgAxis] = number(raw) != null;
    }
  }

  function renderVehicleFields() {
    vehicleFields.innerHTML = vehicleDefinitions.map(([path, label, unit = '', divisor = 1, type = 'number']) => {
      const raw = getPath(path); const shown = raw == null ? '' : Number(raw) / (divisor || 1);
      if (type === 'preset') return `<label>${label}<select data-layout-path="${path}">${['CENTRALIZED', 'DISTRIBUTED', 'DORSAL_DOMINANT', 'LATERAL_DISTRIBUTED', 'WING_ASSISTED', 'HYBRID'].map((item) => `<option value="${item}" ${raw === item ? 'selected' : ''}>${display(item)}</option>`).join('')}</select></label>`;
      if (type === 'objective') return `<label>${label}<select data-layout-path="${path}">${['BALANCED', 'MINIMUM_MASS', 'MINIMUM_DRAG', 'MINIMUM_PILOT_HEAT', 'MINIMUM_ENERGY', 'MAXIMUM_CONTROL', 'MAXIMUM_REDUNDANCY', 'MAXIMUM_ENDURANCE'].map((item) => `<option value="${item}" ${raw === item ? 'selected' : ''}>${display(item)}</option>`).join('')}</select></label>`;
      return `<label class="${raw == null && type !== 'text' ? 'cx-data-required' : ''} ${path === 'name' ? 'wide' : ''}">${label}<input data-layout-path="${path}" data-multiplier="${divisor || 1}" type="${type}" ${type === 'number' ? 'step="any"' : ''} value="${escapeHtml(type === 'text' ? raw : shown)}" placeholder="${type === 'text' ? '' : 'DADOS NECESSÁRIOS'}"><small>${unit || ''}</small></label>`;
    }).join('');
  }

  function renderUnitList() {
    unitList.innerHTML = layout?.units?.length ? layout.units.map((unit) => `<button type="button" class="cx-unit-row ${unit.id === selectedUnitId ? 'active' : ''}" data-unit-id="${escapeHtml(unit.id)}"><strong>${escapeHtml(unit.name)}</strong><b>${escapeHtml(display(unit.status))}</b><small>${escapeHtml(zoneLabel(unit.mountZone))} · ${unit.maxThrust == null ? 'EMPUXO MÁXIMO · DADOS NECESSÁRIOS' : `${unit.maxThrust} N`}</small></button>`).join('') : '<div class="cx-missing">SEM UNIDADES ABSTRATAS. Adicione uma unidade; nenhuma posição de propulsão será presumida.</div>';
  }

  const unitDefinitions = [
    ['name', 'NOME', 'text'], ['status', 'ESTADO', 'status'], ['mass', 'MASSA · kg'], ['maxThrust', 'EMPUXO MÁXIMO · N'],
    ['continuousThrust', 'EMPUXO CONTÍNUO · N'], ['powerCommand', 'COMANDO DE POTÊNCIA · 0–1'],
    ['minimumStableOutput', 'SAÍDA MÍNIMA ESTÁVEL · 0–1'], ['responseTime', 'TEMPO DE RESPOSTA · s'],
    ['positionX', 'POSIÇÃO X · m'], ['positionY', 'POSIÇÃO Y · m'], ['positionZ', 'POSIÇÃO Z · m'],
    ['orientationPitch', 'ORIENTAÇÃO DE ARFAGEM · °'], ['orientationYaw', 'ORIENTAÇÃO DE GUINADA · °'], ['orientationRoll', 'ORIENTAÇÃO DE ROLAGEM · °'],
    ['thermalOutput', 'POTÊNCIA TÉRMICA · W'], ['thermalRadiusEstimate', 'RAIO TÉRMICO · m'],
    ['thermalResistance', 'RESISTÊNCIA TÉRMICA · K/W'], ['thermalTimeConstant', 'CONSTANTE DE TEMPO TÉRMICA · s'],
    ['coolingEffectiveness', 'EFICÁCIA DO RESFRIAMENTO · 0–1'], ['frontalArea', 'ÁREA FRONTAL · m²'],
    ['dragCoefficient', 'COEFICIENTE DE ARRASTO'], ['operationalLimit', 'LIMITE OPERACIONAL · 0–1'],
    ['structuralSupportScore', 'SUPORTE ESTRUTURAL · 0–100'], ['maintenanceAccessScore', 'ACESSO DE MANUTENÇÃO · 0–100'],
    ['redundancyGroup', 'GRUPO DE REDUNDÂNCIA', 'text'], ['confidenceLevel', 'CONFIANÇA', 'confidence'],
    ['energy50', 'CONSUMO A 50% · W', 'curve'], ['energy100', 'CONSUMO A 100% · W', 'curve'],
    ['installationEnvelope.width', 'LARGURA DO ENVELOPE · m'], ['installationEnvelope.height', 'ALTURA DO ENVELOPE · m'], ['installationEnvelope.length', 'COMPRIMENTO DO ENVELOPE · m'],
    ['serviceEnvelope.width', 'LARGURA PARA MANUTENÇÃO · m'], ['serviceEnvelope.height', 'ALTURA PARA MANUTENÇÃO · m'], ['serviceEnvelope.length', 'COMPRIMENTO PARA MANUTENÇÃO · m'],
  ];

  function curveValue(unit, command) { return unit.energyConsumptionCurve?.find((point) => Math.abs(point.powerCommand - command) < .001)?.watts ?? null; }
  function unitValue(unit, path) {
    if (path === 'energy50') return curveValue(unit, .5);
    if (path === 'energy100') return curveValue(unit, 1);
    return path.split('.').reduce((current, key) => current?.[key], unit);
  }

  function renderUnitFields() {
    const unit = currentUnit(); $('cxPropulsionInspectorState').textContent = unit ? unit.id.toUpperCase() : 'SEM UNIDADE';
    if (!unit) { unitFields.innerHTML = '<div class="cx-missing wide">Selecione ou adicione uma unidade abstrata.</div>'; return; }
    const zones = ['UNPLACED', 'FREE_POSITION', ...metadata.candidateZones.map((zone) => zone.id)];
    const fields = [`<label class="wide">ZONA DE POSICIONAMENTO<select data-unit-field="mountZone">${zones.map((zone) => `<option value="${zone}" ${unit.mountZone === zone ? 'selected' : ''}>${escapeHtml(zoneLabel(zone))}</option>`).join('')}</select></label>`];
    unitDefinitions.forEach(([path, label, type = 'number']) => {
      const raw = unitValue(unit, path); const required = raw == null && type === 'number';
      if (type === 'status') fields.push(`<label>ESTADO<select data-unit-field="status">${['ACTIVE', 'INACTIVE', 'FAILED'].map((item) => `<option value="${item}" ${unit.status === item ? 'selected' : ''}>${display(item)}</option>`).join('')}</select></label>`);
      else if (type === 'confidence') fields.push(`<label>CONFIANÇA<select data-unit-field="confidenceLevel">${['DATA_REQUIRED', 'LOW', 'MEDIUM', 'HIGH'].map((item) => `<option value="${item}" ${unit.confidenceLevel === item ? 'selected' : ''}>${display(item)}</option>`).join('')}</select></label>`);
      else fields.push(`<label class="${required ? 'cx-data-required' : ''}">${label}<input data-unit-field="${path}" type="${type === 'text' ? 'text' : 'number'}" ${type === 'text' ? 'maxlength="120"' : 'step="any"'} value="${escapeHtml(value(raw))}" placeholder="${type === 'text' ? '' : 'DADOS NECESSÁRIOS'}"></label>`);
    });
    fields.push(`<label class="wide">GRUPOS DE CONTROLE<select data-unit-field="controlGroup" multiple size="4">${metadata.controlGroups.map((group) => `<option value="${group}" ${unit.controlGroup?.includes(group) ? 'selected' : ''}>${display(group)}</option>`).join('')}</select></label>`);
    fields.push('<button type="button" class="cx-lab-action" id="cxMirrorPropulsionUnit">ESPELHAR ESQUERDA ↔ DIREITA</button><button type="button" class="cx-lab-action cx-unit-danger" id="cxDeletePropulsionUnit">EXCLUIR UNIDADE</button>');
    unitFields.innerHTML = fields.join('');
  }

  function renderZones() {
    const zones = analysis?.candidateZones?.length ? analysis.candidateZones : metadata.candidateZones;
    const unit = currentUnit(); zoneGrid.innerHTML = zones.map((zone) => `<button type="button" class="cx-zone ${unit?.mountZone === zone.id ? 'active' : ''}" data-zone-id="${escapeHtml(zone.id)}" data-status="${escapeHtml(zone.status || 'NOT_EVALUATED')}" title="Zona candidata de estudo; não representa uma instalação aprovada."><b>${escapeHtml(zoneLabel(zone.id))}</b><span>${zone.placementScore == null ? 'NÃO AVALIADA' : `PONTUAÇÃO ${zone.placementScore}`}</span></button>`).join('');
    const unitCount = layout?.units?.length || 0;
    viewportState.textContent = `${zones.length} ZONAS CANDIDATAS · ${unitCount} ${unitCount === 1 ? 'UNIDADE ABSTRATA' : 'UNIDADES ABSTRATAS'} · AS CAIXAS NÃO SÃO MOTORES`;
  }

  const dashboardDefinitions = [
    ['unitsActive', 'UNIDADES ATIVAS', '', 'Quantidade de fontes abstratas marcadas como ativas.'],
    ['totalThrust', 'EMPUXO LÍQUIDO RESULTANTE', ' N', 'Soma vetorial dos empuxos; vetores opostos podem se cancelar.'],
    ['verticalComponent', 'COMPONENTE VERTICAL', ' N', 'Parte do empuxo direcionada para cima no eixo Y.'],
    ['forwardComponent', 'COMPONENTE LONGITUDINAL', ' N', 'Parte do empuxo direcionada para a frente no eixo Z.'],
    ['thrustWeight', 'EMPUXO / PESO (T/W)', '', 'Empuxo resultante dividido pelo peso. Não prova voo seguro nem capacidade de pairar.'],
    ['totalPropulsionMass', 'MASSA DA PROPULSÃO', ' kg', 'Soma das massas informadas; suportes, cabos e refrigeração devem ser incluídos separadamente.'],
    ['rollMoment', 'MOMENTO DE ROLAGEM', ' N·m', 'Tendência estática de girar lateralmente em torno do eixo longitudinal Z.'],
    ['pitchMoment', 'MOMENTO DE ARFAGEM', ' N·m', 'Tendência estática de inclinar frente ou traseira em torno do eixo lateral X.'],
    ['yawMoment', 'MOMENTO DE GUINADA', ' N·m', 'Tendência estática de virar para esquerda ou direita em torno do eixo vertical Y.'],
    ['totalPropulsionEnergyWatts', 'POTÊNCIA INSTANTÂNEA', ' W', 'Demanda instantânea no comando atual; não é a energia total nem a autonomia.'],
    ['totalThermalOutputWatts', 'POTÊNCIA TÉRMICA', ' W', 'Calor dissipado por unidade de tempo; não é temperatura da pele.'],
    ['propulsionDragNewtons', 'ARRASTO DE INSTALAÇÃO', ' N', 'Estimativa ½ρV²CdA sem interação de fluxo ou CFD.'],
    ['redundancyScore', 'REDUNDÂNCIA', '/100', 'Triagem da autoridade restante após falhas abstratas; não é confiabilidade certificada.'],
    ['safetyIndex', 'ÍNDICE DE TRIAGEM', '/100', 'Resumo heurístico para priorizar estudos; não é aprovação de segurança.'],
  ];

  function dashboardMetric(key) {
    const units = layout?.units || []; const active = units.filter((unit) => unit.status === 'ACTIVE');
    if (key === 'unitsActive') return { state: 'calculated', text: String(active.length), note: units.length ? 'CONTAGEM CONFIGURADA' : 'NENHUMA UNIDADE ADICIONADA' };
    if (!analysis) return { state: 'empty', text: 'NÃO CALCULADO', note: 'EXECUTE A ANÁLISE' };
    if (!units.length) return { state: 'empty', text: 'SEM UNIDADES', note: 'ADICIONE UMA UNIDADE ABSTRATA' };
    const raw = analysis.dashboard?.[key];
    const forceKeys = new Set(['totalThrust', 'verticalComponent', 'forwardComponent', 'rollMoment', 'pitchMoment', 'yawMoment']);
    const incompleteForce = active.some((unit) => unit.maxThrust == null || unit.powerCommand == null);
    if (forceKeys.has(key) && incompleteForce) return { state: 'required', text: 'DADOS NECESSÁRIOS', note: 'EMPUXO MÁXIMO + COMANDO' };
    if (['rollMoment', 'pitchMoment', 'yawMoment'].includes(key) && !analysis.massEngine?.vehicleCg) return { state: 'required', text: 'DADOS NECESSÁRIOS', note: 'CENTRO DE GRAVIDADE' };
    if (key === 'totalPropulsionMass' && units.some((unit) => unit.mass == null)) return { state: 'required', text: 'DADOS NECESSÁRIOS', note: 'MASSA DE TODAS AS UNIDADES' };
    if (raw == null) return { state: 'required', text: 'DADOS NECESSÁRIOS', note: 'ENTRADAS INCOMPLETAS' };
    const definition = dashboardDefinitions.find(([metric]) => metric === key);
    return { state: 'calculated', text: format(raw, definition?.[2] || ''), note: active.length ? 'CALCULADO · MODELO L2' : 'CALCULADO · TODAS INATIVAS' };
  }

  function renderMissing(rows) {
    if (!rows.length) return '<div>Os campos obrigatórios deste modelo paramétrico L2 estão presentes. Isso não equivale à validação física.</div>';
    const groups = { '1 · VEÍCULO E REFERÊNCIA': [], '2 · ENERGIA E MISSÃO': [], '3 · UNIDADES ABSTRATAS': [] };
    rows.forEach((item) => {
      if (/^(AT LEAST ONE)/.test(String(item)) || / (PLACEMENT|MASS|MAX THRUST|CONTINUOUS THRUST|POWER COMMAND|MINIMUM STABLE OUTPUT|RESPONSE TIME|THERMAL OUTPUT|THERMAL RADIUS|THERMAL RESISTANCE|THERMAL TIME CONSTANT|COOLING EFFECTIVENESS|OPERATIONAL LIMIT|FRONTAL AREA|DRAG COEFFICIENT|STRUCTURAL SUPPORT|MAINTENANCE ACCESS|ENERGY CONSUMPTION CURVE|INSTALLATION ENVELOPE|SERVICE ENVELOPE|CONTROL GROUP|REDUNDANCY GROUP|CONFIDENCE)$/.test(String(item))) groups['3 · UNIDADES ABSTRATAS'].push(item);
      else if (String(item).startsWith('M01 ') || String(item).includes('ENERGY')) groups['2 · ENERGIA E MISSÃO'].push(item);
      else groups['1 · VEÍCULO E REFERÊNCIA'].push(item);
    });
    return Object.entries(groups).filter(([, items]) => items.length).map(([label, items]) => `<section class="cx-missing-group"><b>${label}</b>${items.map((item) => `<div>○ ${escapeHtml(missingLabel(item))}</div>`).join('')}</section>`).join('');
  }

  function renderAnalysis() {
    dashboard.innerHTML = dashboardDefinitions.map(([key, label, , description]) => { const metric = dashboardMetric(key); return `<div class="cx-dash" data-state="${metric.state}" title="${escapeHtml(description)}"><small>${label}</small><strong>${escapeHtml(metric.text)}</strong><em>${escapeHtml(metric.note)}</em></div>`; }).join('');
    decision.textContent = display(analysis?.decision || 'INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT');
    missing.innerHTML = renderMissing(analysis?.missingData || []);
    const singleFailures = (analysis?.failureEngine?.singleUnitFailure || []).map((row) => `<article><span>${escapeHtml(row.failedUnitId)} · COM FALHA</span><b>${escapeHtml(display(row.classification))}</b><small>${format(row.thrustRemainingPercent, '%')} de empuxo · ${format(row.controlRemainingPercent, '%')} de controle</small></article>`);
    const commonFailures = (analysis?.failureEngine?.commonModeFailure || []).map((row) => `<article><span>MODO COMUM · ${escapeHtml(commonModeLabel(row.group))}</span><b>${format(row.liftRemainingPercent, '%')} VERTICAL</b><small>${escapeHtml((row.failedUnits || []).join(' · '))}</small></article>`);
    failures.innerHTML = [...singleFailures, ...commonFailures].join('') || '<div class="cx-missing">DADOS NECESSÁRIOS</div>';
    mission.innerHTML = (analysis?.missionEngine?.phases || []).map((phase) => `<article><span>${escapeHtml(display(phase.name))}</span><b>${escapeHtml(display(phase.status))}</b><small>${phase.durationSeconds == null ? 'DURAÇÃO · DADOS NECESSÁRIOS' : `${format(phase.durationSeconds / 60, ' min')} · ${format(phase.energyWh, ' Wh')}`}</small></article>`).join('') || '<div class="cx-missing">DADOS NECESSÁRIOS</div>';
    control.innerHTML = (analysis?.controlAllocationEngine?.controlMatrix || []).map((row) => `<article><span>${escapeHtml(row.unitId)}</span><b>S ${display(row.Lift)} · R ${display(row.Roll)} · A ${display(row.Pitch)} · G ${display(row.Yaw)}</b></article>`).join('') || '<div class="cx-missing">SEM UNIDADES</div>';
    const chain = analysis?.evidenceChain; evidence.innerHTML = chain ? `<b>FONTE</b><br>${escapeHtml(evidenceLabel(chain.source))}<br><br><b>MÉTODO</b><br>${escapeHtml(evidenceLabel(chain.method))}<br><br><b>HIPÓTESES</b><br>${chain.assumptions.map((item) => escapeHtml(evidenceLabel(item))).join('<br>')}<br><br><b>CONFIANÇA</b><br>${escapeHtml(display(chain.confidence))} · ${escapeHtml(chain.modelLevel)}<br><br><b>LIMITES</b><br>L1 = geometria conceitual · L2 = cálculo paramétrico simplificado · sem CFD, FEA ou ensaio físico.` : 'Execute a análise para criar a cadeia de evidências.';
    renderDelta(); renderZones(); viewer.setState(layout, analysis, toggles);
  }

  function renderDelta() {
    if (!previousAnalysis || !analysis) { delta.innerHTML = '<div class="cx-missing">Mova uma unidade ou altere uma entrada para comparar antes e depois.</div>'; return; }
    const metrics = [['totalPropulsionMass', 'MASSA TOTAL'], ['rollMoment', 'ROLAGEM'], ['pitchMoment', 'ARFAGEM'], ['yawMoment', 'GUINADA'], ['propulsionDragNewtons', 'ARRASTO'], ['totalThermalOutputWatts', 'TÉRMICO'], ['safetyIndex', 'TRIAGEM']];
    delta.innerHTML = metrics.map(([key, label]) => { const before = previousAnalysis.dashboard[key]; const after = analysis.dashboard[key]; const change = before == null || after == null ? null : Number(after) - Number(before); return `<article><span>${label}</span><b>${change == null ? 'DADOS NECESSÁRIOS' : `${change >= 0 ? '+' : ''}${change.toFixed(3)}`}</b><small>${format(before)} → ${format(after)}</small></article>`; }).join('');
  }

  function renderAll() { renderTabs(); renderVehicleFields(); renderUnitList(); renderUnitFields(); renderZones(); renderAnalysis(); }

  async function analyze({ remember = false, revision = null } = {}) {
    if (!layout) return;
    const requestRevision = revision ?? ++analyzeRevision;
    if (remember) previousAnalysis = analysis ? clone(analysis) : null;
    layout.selectedUnitId = selectedUnitId;
    const requestLayout = clone(layout);
    try {
      const data = await request('/api/condor-x/propulsion/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout: requestLayout }) });
      if (requestRevision !== analyzeRevision) return;
      analysis = data.analysis; layout = analysis.layout; const index = layouts.findIndex((item) => item.id === layout.id); if (index >= 0) layouts[index] = layout;
      if (selectedUnitId && !layout.units.some((unit) => unit.id === selectedUnitId)) selectedUnitId = layout.units[0]?.id || null;
      renderAll(); broadcastState();
    } catch (error) { if (requestRevision === analyzeRevision) decision.textContent = error.message; }
  }

  function scheduleAnalysis(remember = true) {
    clearTimeout(analyzeTimer);
    if (remember && analysis) previousAnalysis = clone(analysis);
    const revision = ++analyzeRevision;
    analyzeTimer = setTimeout(() => analyze({ revision }), 240);
  }
  function selectUnit(id) { selectedUnitId = id; layout.selectedUnitId = id; renderUnitList(); renderUnitFields(); renderZones(); analyze(); }

  function moveUnit(id, position, mountZone) {
    const unit = layout.units.find((item) => item.id === id); if (!unit) return;
    previousAnalysis = analysis ? clone(analysis) : null;
    unit.positionX = Number(position.x); unit.positionY = Number(position.y); unit.positionZ = Number(position.z); unit.mountZone = mountZone;
    selectedUnitId = id; layout.selectedUnitId = id; analyze();
  }

  async function load() {
    if (loadPromise) return loadPromise;
    loadPromise = (async () => {
      try {
        const [data, project] = await Promise.all([request('/api/condor-x/propulsion'), request('/api/projects/condor-x')]);
        metadata = data; layouts = data.layouts || []; bodyParts = project.parts || []; viewer.setParts(bodyParts);
        layout = layouts[0] || null; selectedUnitId = layout?.units?.[0]?.id || null;
        if (layout) await analyze(); else { decision.textContent = 'Crie uma configuração após desbloquear o cofre local.'; broadcastState(); }
      } catch (error) { decision.textContent = error.message; }
    })().finally(() => { loadPromise = null; });
    return loadPromise;
  }

  async function saveLayout() {
    if (!layout) throw new Error('Desbloqueie o cofre local e carregue uma configuração antes de salvar.');
    clearTimeout(analyzeTimer); const saveRevision = ++analyzeRevision; const requestLayout = clone(layout);
    const data = await request(`/api/condor-x/propulsion/layouts/${encodeURIComponent(layout.id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestLayout) });
    if (saveRevision !== analyzeRevision) throw new Error('A configuração mudou durante o salvamento. As alterações mais recentes continuam não salvas; salve novamente.');
    layout = data.layout; const index = layouts.findIndex((item) => item.id === layout.id); if (index >= 0) layouts[index] = layout;
    await analyze();
    decision.textContent = 'CONFIGURAÇÃO SALVA NO COFRE LOCAL CRIPTOGRAFADO.';
    broadcastState();
    return decision.textContent;
  }

  async function runMission() {
    if (!layout) throw new Error('Desbloqueie o cofre local e carregue uma configuração antes de executar a M01.');
    clearTimeout(analyzeTimer); const runRevision = ++analyzeRevision;
    const data = await request('/api/condor-x/propulsion/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout: clone(layout) }) });
    if (runRevision !== analyzeRevision) throw new Error('O resultado M01 foi descartado porque o projeto mudou durante a execução. Execute novamente.');
    analysis = data.analysis; layout = analysis.layout; renderAll();
    decision.textContent = `${display(analysis.decision)} · EXECUÇÃO ${data.run.id}`;
    broadcastState();
    return decision.textContent;
  }

  tabs.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-layout-id]'); if (!button) return;
    layout = layouts.find((item) => item.id === button.dataset.layoutId); selectedUnitId = layout?.units?.[0]?.id || null; previousAnalysis = null; await analyze();
  });
  vehicleFields.addEventListener('input', (event) => { const input = event.target.closest('[data-layout-path]'); if (!input || !layout) return; setPath(input.dataset.layoutPath, input.value, Number(input.dataset.multiplier || 1)); scheduleAnalysis(); });
  unitList.addEventListener('click', (event) => { const button = event.target.closest('[data-unit-id]'); if (button) selectUnit(button.dataset.unitId); });
  unitFields.addEventListener('input', (event) => {
    const input = event.target.closest('[data-unit-field]'); const unit = currentUnit(); if (!input || !unit) return; const path = input.dataset.unitField;
    if (path === 'controlGroup') unit.controlGroup = Array.from(input.selectedOptions).map((option) => option.value);
    else if (path === 'energy50' || path === 'energy100') { const command = path === 'energy50' ? .5 : 1; const points = new Map((unit.energyConsumptionCurve || []).map((point) => [point.powerCommand, point.watts])); if (number(input.value) == null) points.delete(command); else points.set(command, number(input.value)); if (!points.has(0)) points.set(0, 0); unit.energyConsumptionCurve = Array.from(points, ([powerCommand, watts]) => ({ powerCommand, watts })).sort((a, b) => a.powerCommand - b.powerCommand); }
    else if (path.includes('.')) { const [parent, key] = path.split('.'); unit[parent][key] = number(input.value); }
    else if (path === 'mountZone') { const zone = metadata.candidateZones.find((item) => item.id === input.value); unit.mountZone = input.value; if (zone) { unit.positionX = zone.position.x; unit.positionY = zone.position.y; unit.positionZ = zone.position.z; } }
    else if (['name', 'status', 'confidenceLevel', 'redundancyGroup'].includes(path)) unit[path] = input.value;
    else unit[path] = number(input.value);
    renderUnitList(); scheduleAnalysis();
  });
  unitFields.addEventListener('click', (event) => {
    const unit = currentUnit(); if (!unit) return;
    if (event.target.id === 'cxMirrorPropulsionUnit') { previousAnalysis = analysis ? clone(analysis) : null; unit.positionX *= -1; unit.orientationYaw *= -1; unit.mountZone = unit.mountZone.includes('LEFT') ? unit.mountZone.replace('LEFT', 'RIGHT') : unit.mountZone.includes('RIGHT') ? unit.mountZone.replace('RIGHT', 'LEFT') : 'FREE_POSITION'; analyze(); }
    if (event.target.id === 'cxDeletePropulsionUnit' && window.confirm(`Excluir a unidade abstrata “${unit.name}”?`)) { previousAnalysis = analysis ? clone(analysis) : null; layout.units = layout.units.filter((item) => item.id !== unit.id); selectedUnitId = layout.units[0]?.id || null; analyze(); }
  });
  zoneGrid.addEventListener('click', (event) => { const button = event.target.closest('[data-zone-id]'); if (!button) return; const unit = currentUnit(); if (!unit) { decision.textContent = 'Adicione ou selecione uma unidade abstrata antes de testar esta zona candidata.'; return; } const zone = metadata.candidateZones.find((item) => item.id === button.dataset.zoneId); if (zone) moveUnit(unit.id, zone.position, zone.id); });
  root.querySelector('.cx-toggle-row').addEventListener('click', (event) => { const button = event.target.closest('[data-prop-toggle]'); if (!button) return; const key = button.dataset.propToggle; toggles[key] = !toggles[key]; button.classList.toggle('active', toggles[key]); viewer.setState(layout, analysis, toggles); });
  $('cxOpenPropulsionLab').addEventListener('click', () => root.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  $('cxAddPropulsionUnit').addEventListener('click', () => { previousAnalysis = analysis ? clone(analysis) : null; const unit = blankUnit(layout.units.length); layout.units.push(unit); selectedUnitId = unit.id; analyze(); });
  $('cxSavePropulsionLayout').addEventListener('click', async () => { try { await saveLayout(); } catch (error) { decision.textContent = error.message; } });
  $('cxRunPropulsionMission').addEventListener('click', async () => { try { await runMission(); } catch (error) { decision.textContent = error.message; } });
  $('cxNewPropulsionLayout').addEventListener('click', async () => { const name = window.prompt('Nome da nova configuração de propulsão:', `CONFIGURAÇÃO ${String.fromCharCode(65 + layouts.length)}`); if (!name) return; const id = `${slug(name)}-${Date.now().toString(36)}`; try { const payload = { id, name, vehicle: {}, mission: { targetEnduranceSeconds: 7200, phases: {} }, units: [] }; const data = await request('/api/condor-x/propulsion/layouts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); layouts.push(data.layout); layout = data.layout; selectedUnitId = null; previousAnalysis = null; await analyze(); } catch (error) { decision.textContent = error.message; } });
  $('cxDuplicatePropulsionLayout').addEventListener('click', async () => { if (!layout) return; const copy = clone(layout); copy.id = `${slug(copy.name)}-copy-${Date.now().toString(36)}`; copy.name = `${copy.name} · CÓPIA`; copy.units.forEach((unit, index) => { unit.id = `unit-${index + 1}-${crypto.randomUUID().slice(0, 6)}`; }); try { const data = await request('/api/condor-x/propulsion/layouts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(copy) }); layouts.push(data.layout); layout = data.layout; selectedUnitId = layout.units[0]?.id || null; previousAnalysis = null; await analyze(); } catch (error) { decision.textContent = error.message; } });
  $('cxAutoPropulsionLayout').addEventListener('click', async () => { const template = currentUnit(); if (!template) { decision.textContent = 'Selecione uma unidade abstrata configurada para usar como modelo do posicionamento automático.'; return; } const requested = Number(window.prompt('Quantidade de unidades abstratas para posicionar (1–6):', String(Math.max(1, Math.min(6, layout.units.length || 2))))); if (!Number.isInteger(requested) || requested < 1 || requested > 6) return; try { const data = await request('/api/condor-x/propulsion/auto-layout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout, unitTemplate: template, numberOfUnits: requested, allowedZones: metadata.candidateZones.map((zone) => zone.id), objective: layout.objective }) }); const result = data.result; decision.textContent = `${display(result.status)} · ${result.note ? 'Candidatas mantidas para comparar compensações; aparência não é objetivo.' : ''}`; delta.innerHTML = (result.layouts || []).map((item, index) => `<article><span>${escapeHtml(layoutLabel(item.name))}</span><b>PARETO ${index + 1}</b><small>${item.units.map((unit) => escapeHtml(zoneLabel(unit.mountZone))).join(' · ')}</small></article>`).join('') || '<div class="cx-missing">Nenhuma candidata viável foi gerada. Complete os dados e as restrições do modelo.</div>'; } catch (error) { decision.textContent = error.message; } });
  $('cxComparePropulsionLayouts').addEventListener('click', async () => { try { const data = await request('/api/condor-x/propulsion/compare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layouts }) }); const rows = data.comparison.layouts; delta.innerHTML = rows.map((row) => `<article><span>${escapeHtml(layoutLabel(row.name))}</span><b>${escapeHtml(display(row.decision))}</b><small>massa ${format(row.mass, ' kg')} · arrasto ${format(row.drag, ' N')} · triagem ${format(row.safety, '/100')} · autonomia ${format(row.endurance, ' s')}</small></article>`).join(''); decision.textContent = 'Nenhuma configuração única é declarada como melhor; compare compensações e evidências.'; } catch (error) { decision.textContent = error.message; } });
  window.addEventListener('condor-design-studio-update', (event) => {
    if (!layout || !event.detail?.designStudio) return;
    layout.designStudio = clone(event.detail.designStudio);
    scheduleAnalysis(false);
  });
  window.addEventListener('condor-propulsion-command', async (event) => {
    const action = event.detail?.action;
    try {
      if (!layout) throw new Error('Desbloqueie o cofre local criptografado antes de usar esta ação.');
      if (event.detail?.designStudio) layout.designStudio = clone(event.detail.designStudio);
      const message = action === 'save' ? await saveLayout() : action === 'run' ? await runMission() : 'Comando do Estúdio de Design não suportado.';
      commandResult(action, ['save', 'run'].includes(action), message);
    } catch (error) {
      decision.textContent = error.message; commandResult(action, false, error.message);
    }
  });
  window.addEventListener('condor-x-visibility', (event) => { if (event.detail?.active && !layout) load(); else if (event.detail?.active) { viewer.setParts(bodyParts); viewer.resize(); } });
  window.addEventListener('condor-security-ready', () => { if (!layout) load(); });
  request('/api/seguranca/estado').then((state) => { if (state.vault_unlocked) load(); }).catch(() => {});
}
