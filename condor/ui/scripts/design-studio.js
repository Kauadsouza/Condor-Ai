import { DEFAULT_DESIGN_STATE } from './design-studio-3d.js';

const root = document.getElementById('cxDesignStudio');

if (root && !root.dataset.ready) {
  root.dataset.ready = 'true';
  const $ = (id) => document.getElementById(id);
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, Number(value)));
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  const statusLabels = {
    UNVALIDATED: 'NÃO VALIDADO', DATA_REQUIRED: 'DADOS NECESSÁRIOS', LOW: 'BAIXA', MEDIUM: 'MÉDIA', HIGH: 'ALTA',
    INSUFFICIENT_DATA: 'DADOS INSUFICIENTES', INSUFFICIENT_DATA_TO_DETERMINE_PROPULSION_LAYOUT: 'DADOS INSUFICIENTES PARA DETERMINAR A CONFIGURAÇÃO DE PROPULSÃO',
    REJECTED: 'REJEITADA', CANDIDATE_FOR_FURTHER_SIMULATION: 'CANDIDATA A SIMULAÇÕES ADICIONAIS', PASS: 'ATENDIDA', FAIL: 'NÃO ATENDIDA',
  };
  const modeLabels = { DESIGN: 'PROJETO', AERO: 'AERODINÂMICA', STRUCTURE: 'ESTRUTURA', MASS_CG: 'MASSA / CG', ENERGY: 'ENERGIA', PROPULSION: 'PROPULSÃO', THERMAL: 'TÉRMICO', SAFETY: 'SEGURANÇA', MISSION: 'MISSÃO' };
  const statusLabel = (value) => statusLabels[String(value || '').toUpperCase()] || String(value || '').replaceAll('_', ' ');

  const modeLabel = $('cxStudioModeLabel');
  const overlayLabel = $('cxStudioOverlayLabel');
  const inspectorTitle = $('cxInspectorTitle');
  const inspectorStatus = $('cxInspectorStatus');
  const inspectorSummary = $('cxInspectorSummary');
  const cadxBaselineStatus = $('cxCadxBaselineStatus');
  const inspectorControls = $('cxInspectorControls');
  const selectedComponent = $('cxSelectedComponent');
  const selectedReadout = $('cxSelectedReadout');
  const impact = $('cxChangeImpact');
  const impactConfidence = $('cxImpactConfidence');
  const unsavedLabel = $('cxStudioUnsaved');
  const flightPose = $('cxFlightPose');
  const flightPoseLabel = $('cxFlightPoseLabel');
  const missionPhase = $('cxMissionPhase');
  const studioStatus = $('cxStudioStatus');
  const studioConfidence = $('cxStudioConfidence');
  const studioModelLevel = $('cxStudioModelLevel');
  const hint = $('cxStudioHint');

  let viewer = window.CondorXDesignStudioViewer || null;
  let layout = null;
  let analysis = null;
  let design = clone(DEFAULT_DESIGN_STATE);
  let selectedId = 'CX-M01-WING-L';
  let unsaved = false;
  let cadxBaseline = null;

  function renderCadxBaselineStatus() {
    if (!cadxBaselineStatus) return;
    const assetCount = Array.isArray(cadxBaseline?.assets) ? cadxBaseline.assets.length : 0;
    if (!assetCount) {
      cadxBaselineStatus.hidden = true;
      cadxBaselineStatus.textContent = '';
      return;
    }
    cadxBaselineStatus.hidden = false;
    cadxBaselineStatus.textContent = `CADX R1 ATIVO · OBJ É O CORPO VISUAL · ${assetCount} ARQUIVOS (STEP + OBJ) · GEOMETRIA SEM VALIDAÇÃO FÍSICA`;
  }

  async function loadCadxBaseline() {
    try {
      const response = await fetch('/api/projects/condor-x/cad-baseline', { cache: 'no-store' });
      if (!response.ok) return;
      cadxBaseline = await response.json();
      renderCadxBaselineStatus();
    } catch {
      // The studio remains usable when the optional local source registry is unavailable.
    }
  }

  // Limite interno preservado: FLOW PREVIEW · NOT CFD.
  const modeCopy = {
    DESIGN: ['HIPÓTESE DE PROJETO · NÃO VALIDADA', 'GIRE · SELECIONE A ASA · ARRASTE O CONTROLE ÂMBAR'],
    AERO: ['PRÉVIA DE FLUXO · NÃO É CFD', 'LINHAS DE FLUXO SIMPLIFICADAS · NENHUM RESULTADO DE CFD IMPORTADO'],
    STRUCTURE: ['CAMINHOS DE CARGA · VISUALIZAÇÃO PROVISÓRIA', 'ESTRUTURA DORSAL + INTEGRAÇÃO COM A RAIZ DA ASA'],
    MASS_CG: ['MASSA / CG · RESULTADO DO MÓDULO QUANDO DISPONÍVEL', 'O MARCADOR DO CG SÓ APARECE COM DADOS DO MÓDULO DE CÁLCULO'],
    ENERGY: ['VOLUMES DE ENERGIA · DADOS DE CAPACIDADE NECESSÁRIOS', 'ARRASTE UM VOLUME · REVISE O IMPACTO DA ALTERAÇÃO'],
    PROPULSION: ['PROPULSÃO ABSTRATA · CANDIDATOS DE PROJETO', 'TECNOLOGIA NÃO SELECIONADA · ARRASTE O ENVELOPE INTEGRADO'],
    THERMAL: ['MODELO TÉRMICO · APENAS HIPÓTESE SEM DADOS', 'VOLUMES DE CALOR SÃO CONCEITUAIS ATÉ EXISTIREM DADOS DO MÓDULO'],
    SAFETY: ['VOLUME DE PROTEÇÃO DO PILOTO · VISÃO CONCEITUAL', 'TRANSPARÊNCIA DA CASCA · DADOS DE SAÍDA NECESSÁRIOS'],
    MISSION: ['MISSÃO M01 · META 02:00:00', 'VERTICAL → TRANSIÇÃO → CRUZEIRO SUSTENTADO PELAS ASAS → POUSO'],
  };

  const selectionCopy = {
    'CX-M01-WING-L': ['Asa esquerda', 'NÃO VALIDADA', 'Asa rígida enflechada e afilada integrada à estrutura dorsal. A geometria é visual e relativa; ainda precisa de validação aerodinâmica.'],
    'CX-M01-WING-R': ['Asa direita', 'ESPELHADA', 'Hipótese visual espelhada. Desvincular as asas e estudar assimetrias continuam como trabalhos futuros de engenharia.'],
    'CX-M01-DORSAL-SPINE': ['Estrutura dorsal', 'HIPÓTESE DE PROJETO', 'Estrutura central estreita que conecta tronco, raízes das asas e envelopes candidatos integrados. Nenhum resultado de carga estrutural é afirmado.'],
    'CX-M01-PILOT-SURVIVAL-VOLUME': ['Volume de proteção do piloto', 'VISÃO CONCEITUAL', 'Referência humana interna simplificada, usada apenas para distinguir o piloto da casca externa.'],
  };

  function designRecord(id) {
    return design.energyVolumes?.find((item) => item.id === id) || design.propulsionPods?.find((item) => item.id === id) || null;
  }

  function selectedDetails() {
    if (selectionCopy[selectedId]) return selectionCopy[selectedId];
    const record = designRecord(selectedId);
    if (record?.id.includes('ENERGY')) return ['Volume de energia', 'DADOS NECESSÁRIOS', 'Volume abstrato para alocação de energia. Massa, capacidade, química e propriedades térmicas não são presumidas.'];
    if (record?.id.includes('PROP')) return ['Envelope integrado de propulsão', 'CANDIDATO DE PROJETO', `Envelope abstrato de propulsão para a variante visual ${design.propulsionConcept}. Nenhuma tecnologia ou instalação física foi selecionada.`];
    if (selectedId?.endsWith(':SPAN')) return ['Controle da envergadura', 'EDIÇÃO VISUAL', 'Arraste o controle âmbar ou use o inspetor. O valor é relativo à referência corporal digital, não uma dimensão certificada.'];
    return ['CX-M01 Conceito A', 'NÃO VALIDADO', 'Hipótese de aeronave pessoal compacta com corpo protegido, superfícies funcionais de sustentação e envelopes abstratos integrados de propulsão.'];
  }

  function markUnsaved(message, confidence = 'BAIXA CONFIANÇA') {
    unsaved = true;
    unsavedLabel.textContent = 'NÃO SALVO'; unsavedLabel.classList.add('unsaved');
    impact.textContent = message; impactConfidence.textContent = confidence;
  }

  function rangeControl(label, key, min, max, step, value, formatter, group = 'wing') {
    return `<label>${escapeHtml(label)}<b data-value-for="${escapeHtml(group)}.${escapeHtml(key)}">${escapeHtml(formatter(value))}</b><input type="range" min="${min}" max="${max}" step="${step}" value="${value}" data-design-group="${escapeHtml(group)}" data-design-key="${escapeHtml(key)}"></label>`;
  }

  function renderWingControls() {
    const wing = design.wing;
    inspectorControls.innerHTML = [
      rangeControl('Envergadura', 'spanScale', .65, 1.65, .01, wing.spanScale, (value) => `${Math.round(value * 100)}% REF. CORPORAL`),
      rangeControl('Corda na raiz', 'rootChordScale', .65, 1.5, .01, wing.rootChordScale, (value) => `${Math.round(value * 100)}% REF.`),
      rangeControl('Corda na ponta', 'tipChordScale', .55, 1.5, .01, wing.tipChordScale, (value) => `${Math.round(value * 100)}% REF.`),
      rangeControl('Enflechamento', 'sweepDegrees', 5, 55, 1, wing.sweepDegrees, (value) => `${Math.round(value)}° VISUAL`),
      rangeControl('Diedro', 'dihedralDegrees', -12, 22, 1, wing.dihedralDegrees, (value) => `${Math.round(value)}° VISUAL`),
      rangeControl('Torção', 'twistDegrees', -15, 15, 1, wing.twistDegrees, (value) => `${Math.round(value)}° VISUAL`),
      `<label>Prévia do recolhimento<b>${wing.fold === 'DEPLOYED' ? 'ABERTA' : wing.fold === 'PARTIAL' ? 'PARCIAL' : 'RECOLHIDA'}</b><select data-design-group="wing" data-design-key="fold"><option value="DEPLOYED" ${wing.fold === 'DEPLOYED' ? 'selected' : ''}>ABERTA</option><option value="PARTIAL" ${wing.fold === 'PARTIAL' ? 'selected' : ''}>PARCIAL</option><option value="STOWED" ${wing.fold === 'STOWED' ? 'selected' : ''}>RECOLHIDA</option></select></label>`,
      `<button type="button" data-wing-link>${wing.linked ? 'ESPELHAMENTO À DIREITA · VINCULADO' : 'VINCULAR AS ASAS'}</button>`,
      '<div class="cx-airfoil-mini"><small>SEÇÃO DO AEROFÓLIO</small><svg viewBox="0 0 220 60" aria-label="Seção conceitual do aerofólio"><path d="M8 35 C45 8 160 12 212 31 C158 35 72 45 8 35Z"/></svg><span>PERFIL · PROVISÓRIO</span></div>',
    ].join('');
  }

  function renderPositionControls(record, group) {
    const position = record.position || { x: 0, y: 0, z: 0 };
    inspectorControls.innerHTML = [
      `<div class="cx-data-note">COORDENADAS DE REFERÊNCIA · APENAS MODELO DIGITAL<br>X = DIREITA · Y = CIMA · Z = FRENTE</div>`,
      rangeControl('Lateral X', 'x', -1.5, 1.5, .01, position.x, (value) => Number(value).toFixed(2), group),
      rangeControl('Vertical Y', 'y', -1.2, 1.5, .01, position.y, (value) => Number(value).toFixed(2), group),
      rangeControl('Longitudinal Z', 'z', -.8, .8, .01, position.z, (value) => Number(value).toFixed(2), group),
      `<div class="cx-required-grid"><span>MASSA<b>DADOS NECESSÁRIOS</b></span><span>${group === 'energy' ? 'CAPACIDADE' : 'EMPUXO'}<b>DADOS NECESSÁRIOS</b></span><span>TÉRMICO<b>DADOS NECESSÁRIOS</b></span><span>CONFIANÇA<b>BAIXA</b></span></div>`,
    ].join('');
  }

  function renderModeControls() {
    if (design.mode === 'AERO') {
      inspectorControls.innerHTML = '<div class="cx-overlay-options"><button class="active" type="button">PRÉVIA DE FLUXO</button><button type="button" disabled>PRESSÃO · DADOS NECESSÁRIOS</button><button type="button" disabled>VELOCIDADE · DADOS NECESSÁRIOS</button><button type="button" disabled>RESULTADO DE CFD · NÃO IMPORTADO</button></div><div class="cx-data-note">A prévia reage à atitude e à geometria da asa, mas não é uma simulação de dinâmica dos fluidos computacional.</div>';
    } else if (design.mode === 'MASS_CG') {
      const cg = analysis?.massEngine?.vehicleCg;
      inspectorControls.innerHTML = cg ? `<div class="cx-engine-result"><small>CENTRO DE GRAVIDADE · MÓDULO DE CÁLCULO</small><strong>X ${Number(cg.x).toFixed(3)} · Y ${Number(cg.y).toFixed(3)} · Z ${Number(cg.z).toFixed(3)}</strong><span>FONTE · MODELO SIMPLIFICADO DO CONDOR X</span></div>` : '<div class="cx-empty-engine"><strong>CG · DADOS NECESSÁRIOS</strong><p>Informe massa seca, CG seco e massas da propulsão verificadas antes de exibir o marcador.</p></div>';
    } else if (design.mode === 'THERMAL') {
      const thermal = analysis?.dashboard?.totalThermalOutputWatts;
      inspectorControls.innerHTML = thermal == null ? '<div class="cx-empty-engine"><strong>MODELO TÉRMICO · APENAS HIPÓTESE</strong><p>Não existe potência térmica calculada para as unidades abstratas atuais.</p></div>' : `<div class="cx-engine-result"><small>POTÊNCIA TÉRMICA TOTAL</small><strong>${Number(thermal).toLocaleString('pt-BR')} W</strong><span>NÍVEL DO MODELO · L2</span></div>`;
    } else if (design.mode === 'SAFETY') {
      inspectorControls.innerHTML = `<label>Volume de proteção do piloto<b>${design.pilotVisible ? 'VISÍVEL' : 'VISÍVEL NESTE MODO'}</b><button type="button" data-pilot-toggle>${design.pilotVisible ? 'OCULTAR FORA DO MODO SEGURANÇA' : 'MANTER PILOTO VISÍVEL'}</button></label><div class="cx-required-grid"><span>SAÍDA<b>DADOS NECESSÁRIOS</b></span><span>IMPACTO<b>DADOS NECESSÁRIOS</b></span><span>VISIBILIDADE<b>DADOS NECESSÁRIOS</b></span><span>ESTRUTURA<b>DADOS NECESSÁRIOS</b></span></div>`;
    } else if (design.mode === 'MISSION') {
      const mission = analysis?.missionEngine;
      inspectorControls.innerHTML = `<div class="cx-engine-result"><small>META DE AUTONOMIA M01</small><strong>02:00:00</strong><span>${escapeHtml(statusLabel(mission?.status || 'INSUFFICIENT_DATA'))}</span></div><div class="cx-data-note">A meta é um requisito, não uma previsão de autonomia. O cruzeiro sustentado pelas asas deve reduzir a demanda de propulsão; ainda são necessárias evidências.</div>`;
    } else if (design.mode === 'STRUCTURE') {
      inspectorControls.innerHTML = '<div class="cx-empty-engine"><strong>CAMINHOS DE CARGA · PROVISÓRIOS</strong><p>A continuidade entre estrutura dorsal e raízes das asas está visível. FEA e validação estrutural não foram importados.</p></div>';
    } else if (design.mode === 'PROPULSION') {
      const record = designRecord(selectedId) || design.propulsionPods[0];
      renderPositionControls(record, 'propulsion');
    } else if (design.mode === 'ENERGY') {
      const record = designRecord(selectedId) || design.energyVolumes[0];
      renderPositionControls(record, 'energy');
    } else {
      renderWingControls();
    }
  }

  function renderInspector() {
    const [title, status, summary] = selectedDetails();
    inspectorTitle.textContent = title; inspectorStatus.textContent = status; inspectorSummary.textContent = summary;
    selectedComponent.textContent = selectedId || 'CX-M01 CONCEITO A';
    selectedReadout.textContent = selectedId?.includes('ENERGY') ? 'MASSA + CAPACIDADE · DADOS NECESSÁRIOS' : selectedId?.includes('PROP') ? 'ENVELOPE VISUAL · TECNOLOGIA NÃO SELECIONADA' : 'GEOMETRIA RELATIVA · HIPÓTESE';
    renderModeControls();
  }

  function renderMissionPhase() {
    const pose = Number(design.flightPoseDegrees || 0);
    const phase = pose < 18 ? 'TAKEOFF' : pose < 66 ? 'TRANSITION' : 'CRUISE';
    flightPoseLabel.textContent = `${pose < 18 ? 'SOLO' : pose < 66 ? 'TRANSIÇÃO' : 'CRUZEIRO'} · ${Math.round(pose)}°`;
    missionPhase.textContent = design.mode === 'MISSION' ? ({ TAKEOFF: 'DECOLAGEM', TRANSITION: 'TRANSIÇÃO', CRUISE: 'CRUZEIRO' }[phase]) : 'REVISÃO DE PROJETO';
    root.querySelectorAll('[data-phase]').forEach((element) => element.classList.toggle('active', design.mode === 'MISSION' && element.dataset.phase === phase));
  }

  function render() {
    root.querySelectorAll('[data-cx-mode]').forEach((button) => button.classList.toggle('active', button.dataset.cxMode === design.mode));
    root.querySelectorAll('[data-cx-concept]').forEach((button) => button.classList.toggle('active', button.dataset.cxConcept === design.propulsionConcept));
    modeLabel.textContent = `ESTÚDIO DE DESIGN · ${modeLabels[design.mode] || design.mode.replace('_', ' / ')}`;
    overlayLabel.textContent = modeCopy[design.mode]?.[0] || modeCopy.DESIGN[0];
    hint.textContent = modeCopy[design.mode]?.[1] || modeCopy.DESIGN[1];
    flightPose.value = design.flightPoseDegrees;
    renderMissionPhase(); renderInspector();
    viewer?.setDesignState(design, analysis); viewer?.selectDesign(selectedId);
    studioModelLevel.textContent = analysis?.evidenceChain?.modelLevel || 'L1 / L2';
    const missingCount = analysis?.missingData?.length || 0;
    studioConfidence.textContent = missingCount ? `BAIXA · ${missingCount} PENDÊNCIAS` : statusLabel(analysis?.evidenceChain?.confidence || 'LOW');
    studioStatus.textContent = statusLabel(analysis?.decision || 'UNVALIDATED');
  }

  function emitDesignUpdate(reason, changedId = selectedId) {
    markUnsaved(reason);
    window.dispatchEvent(new CustomEvent('condor-design-studio-update', { detail: { designStudio: clone(design), changedId, reason } }));
  }

  function select(id) {
    selectedId = id || 'CX-M01-WING-L'; viewer?.selectDesign(selectedId); renderInspector();
  }

  function chooseMode(mode) {
    design.mode = mode;
    if (mode === 'ENERGY') selectedId = design.energyVolumes[0]?.id;
    else if (mode === 'PROPULSION' || mode === 'THERMAL') selectedId = design.propulsionPods[0]?.id;
    else if (mode === 'SAFETY') selectedId = 'CX-M01-PILOT-SURVIVAL-VOLUME';
    else if (['AERO', 'DESIGN'].includes(mode)) selectedId = 'CX-M01-WING-L';
    render();
  }

  function bindViewer(target) {
    if (!target) return; viewer = target;
    viewer.onDesignSelect = (id) => select(id);
    viewer.onDesignMove = (id, position) => {
      if (id.endsWith(':SPAN')) {
        design.wing.spanScale = clamp(Math.abs(position.x) / .92, .65, 1.65);
        selectedId = id.startsWith('CX-M01-WING-R') ? 'CX-M01-WING-R' : 'CX-M01-WING-L';
        emitDesignUpdate('A envergadura mudou na visualização 3D. Efeitos aerodinâmicos, estruturais e de missão continuam como DADOS NECESSÁRIOS até os módulos receberem geometria validada.', selectedId);
      } else {
        const record = designRecord(id);
        if (record) {
          record.position = { x: clamp(position.x, -2.5, 2.5), y: clamp(position.y, -2.5, 2.5), z: clamp(position.z, -2.5, 2.5) };
          selectedId = id;
          emitDesignUpdate(`${record.id} foi movido no modelo digital compartilhado. A geometria mudou; efeitos em massa, controle, calor e autonomia continuam como DADOS NECESSÁRIOS quando faltam entradas.`, id);
        }
      }
      render();
    };
    target.setDesignState(design, analysis); target.selectDesign(selectedId);
  }

  root.addEventListener('click', (event) => {
    const modeButton = event.target.closest('[data-cx-mode]'); if (modeButton) { chooseMode(modeButton.dataset.cxMode); return; }
    const conceptButton = event.target.closest('[data-cx-concept]');
    if (conceptButton) {
      design.propulsionConcept = conceptButton.dataset.cxConcept; chooseMode('PROPULSION');
      emitDesignUpdate(`Variante visual ${design.propulsionConcept} selecionada como candidata de arquitetura. As métricas comparativas continuam como DADOS NECESSÁRIOS até cada variante possuir entradas fundamentadas em evidências.`, selectedId); return;
    }
    const viewButton = event.target.closest('[data-cx-view]'); if (viewButton) { viewButton.dataset.cxView === 'fit' ? viewer?.fitStudioView() : viewer?.setView(viewButton.dataset.cxView); return; }
    if (event.target.closest('#cxOrientationCube')) { viewer?.setView('iso'); return; }
    if (event.target.closest('[data-wing-link]')) { design.wing.linked = !design.wing.linked; emitDesignUpdate(design.wing.linked ? 'Espelhamento das asas ativado.' : 'Espelhamento das asas desativado para futura exploração assimétrica.'); render(); return; }
    if (event.target.closest('[data-pilot-toggle]')) { design.pilotVisible = !design.pilotVisible; emitDesignUpdate('A visibilidade do volume de proteção do piloto foi alterada.'); render(); return; }
    if (event.target.closest('#cxAdvancedGeometry')) { window.dispatchEvent(new CustomEvent('condor-x-open-region', { detail: { id: 'chest' } })); return; }
  });

  inspectorControls.addEventListener('input', (event) => {
    const input = event.target.closest('[data-design-key]'); if (!input) return;
    const group = input.dataset.designGroup; const key = input.dataset.designKey;
    if (group === 'wing') design.wing[key] = input.tagName === 'SELECT' ? input.value : Number(input.value);
    else {
      const record = designRecord(selectedId); if (!record) return;
      record.position[key] = Number(input.value);
    }
    const display = inspectorControls.querySelector(`[data-value-for="${group}.${key}"]`);
    if (display) display.textContent = group === 'wing' && key.endsWith('Scale') ? `${Math.round(Number(input.value) * 100)}% REF` : group === 'wing' ? `${Math.round(Number(input.value))}° VISUAL` : Number(input.value).toFixed(2);
    viewer?.setDesignState(design, analysis);
    emitDesignUpdate(group === 'wing' ? 'A geometria da asa mudou. A prévia de fluxo foi atualizada; resultados aerodinâmicos, estruturais e de missão continuam como DADOS NECESSÁRIOS.' : `${selectedId} foi movido. O impacto só é recalculado com as evidências disponíveis.`);
  });

  flightPose.addEventListener('input', () => {
    design.flightPoseDegrees = Number(flightPose.value); viewer?.setDesignState(design, analysis); renderMissionPhase();
    markUnsaved('A atitude de voo mudou apenas como estado visual do corpo inteiro. Anatomia e desempenho físico de voo não foram alterados nem inferidos.');
  });
  flightPose.addEventListener('change', () => emitDesignUpdate('Atitude de voo atualizada. A prévia de fluxo reage visualmente; a dinâmica de voo continua como DADOS NECESSÁRIOS.'));

  $('cxStudioSave').addEventListener('click', () => {
    studioStatus.textContent = 'SALVANDO';
    window.dispatchEvent(new CustomEvent('condor-propulsion-command', { detail: { action: 'save', designStudio: clone(design) } }));
  });
  $('cxStudioRun').addEventListener('click', () => {
    chooseMode('MISSION'); studioStatus.textContent = 'EXECUTANDO M01';
    window.dispatchEvent(new CustomEvent('condor-propulsion-command', { detail: { action: 'run', designStudio: clone(design) } }));
  });
  $('cxStudioCompare').addEventListener('click', () => {
    chooseMode('PROPULSION');
    inspectorTitle.textContent = 'Comparação de variantes visuais'; inspectorStatus.textContent = 'DADOS NECESSÁRIOS';
    inspectorSummary.textContent = 'A, B e C ainda são variações dos envelopes visuais, não arquiteturas completas nem tecnologias selecionadas.';
    inspectorControls.innerHTML = ['A', 'B', 'C'].map((concept) => `<article class="cx-concept-compare"><header><strong>VARIANTE VISUAL ${concept}</strong><span>${concept === design.propulsionConcept ? 'VISÃO ATIVA' : 'CANDIDATA'}</span></header><div>MASSA<b>DADOS NECESSÁRIOS</b></div><div>VOLUME<b>APENAS RELATIVO</b></div><div>ARRASTO<b>DADOS NECESSÁRIOS</b></div><div>CALOR<b>DADOS NECESSÁRIOS</b></div><div>CONTROLE<b>DADOS NECESSÁRIOS</b></div><div>AUTONOMIA<b>DADOS NECESSÁRIOS</b></div></article>`).join('');
    impact.textContent = 'Nenhuma variante vencedora foi definida. Primeiro, cada arquitetura precisa registrar unidades, função por fase, massa, consumo, calor, controle e evidências comparáveis.';
  });

  window.addEventListener('condor-design-viewer-ready', (event) => bindViewer(event.detail?.viewer));
  window.addEventListener('condor-propulsion-state', (event) => {
    layout = event.detail?.layout || layout; analysis = event.detail?.analysis || analysis;
    if (layout?.designStudio) design = clone(layout.designStudio);
    render();
  });
  window.addEventListener('condor-propulsion-command-result', (event) => {
    const detail = event.detail || {};
    if (detail.action === 'save' && detail.ok) { unsaved = false; unsavedLabel.textContent = 'SALVO'; unsavedLabel.classList.remove('unsaved'); impact.textContent = 'Estado do conceito salvo na configuração local criptografada.'; }
    if (detail.action === 'run') impact.textContent = detail.message || 'Verificação M01 concluída.';
    studioStatus.textContent = detail.message || (detail.ok ? 'PRONTO' : 'AÇÃO NÃO CONCLUÍDA');
  });

  bindViewer(viewer); render(); loadCadxBaseline();
}
