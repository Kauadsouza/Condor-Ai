const viewport = document.getElementById('condorXViewport');

if (viewport && !viewport.dataset.ready) {
  viewport.dataset.ready = 'true';

  const REGIONS = {
    head: { label: 'Cabeça', group: 'head-group', box: [207, 28, 106, 140] },
    neck: { label: 'Pescoço', group: 'head-group', box: [215, 140, 90, 88] },
    chest: { label: 'Tórax', group: 'torso', box: [138, 178, 244, 220] },
    abdomen: { label: 'Abdômen', group: 'torso', box: [184, 368, 152, 124] },
    pelvis: { label: 'Quadril', group: 'torso', box: [190, 456, 140, 102] },
    power: { label: 'Centro', group: 'torso', box: [225, 260, 70, 70] },
    'left-shoulder': { label: 'Ombro esquerdo', group: 'left-arm', box: [134, 190, 82, 130] },
    'left-upper-arm': { label: 'Braço esquerdo', group: 'left-arm', box: [126, 286, 76, 150] },
    'left-elbow': { label: 'Cotovelo esquerdo', group: 'left-arm', box: [124, 414, 68, 66] },
    'left-forearm': { label: 'Antebraço esquerdo', group: 'left-arm', box: [105, 454, 84, 172] },
    'left-hand': { label: 'Mão esquerda', group: 'left-arm', box: [88, 586, 102, 108] },
    'right-shoulder': { label: 'Ombro direito', group: 'right-arm', box: [304, 190, 82, 130] },
    'right-upper-arm': { label: 'Braço direito', group: 'right-arm', box: [318, 286, 76, 150] },
    'right-elbow': { label: 'Cotovelo direito', group: 'right-arm', box: [328, 414, 68, 66] },
    'right-forearm': { label: 'Antebraço direito', group: 'right-arm', box: [331, 454, 84, 172] },
    'right-hand': { label: 'Mão direita', group: 'right-arm', box: [330, 586, 102, 108] },
    'left-thigh': { label: 'Coxa esquerda', group: 'legs', box: [184, 514, 82, 208] },
    'left-knee': { label: 'Joelho esquerdo', group: 'legs', box: [188, 674, 70, 68] },
    'left-shin': { label: 'Canela esquerda', group: 'legs', box: [180, 714, 78, 158] },
    'left-foot': { label: 'Pé esquerdo', group: 'legs', box: [168, 838, 94, 60] },
    'right-thigh': { label: 'Coxa direita', group: 'legs', box: [254, 514, 82, 208] },
    'right-knee': { label: 'Joelho direito', group: 'legs', box: [262, 674, 70, 68] },
    'right-shin': { label: 'Canela direita', group: 'legs', box: [262, 714, 78, 158] },
    'right-foot': { label: 'Pé direito', group: 'legs', box: [258, 838, 94, 60] },
  };

  const GROUPS = {
    'head-group': { label: 'Cabeça e pescoço', parts: ['head', 'neck'] },
    torso: { label: 'Tronco', parts: ['chest', 'abdomen', 'pelvis', 'power'] },
    'left-arm': { label: 'Braço esquerdo', parts: ['left-shoulder', 'left-upper-arm', 'left-elbow', 'left-forearm', 'left-hand'] },
    'right-arm': { label: 'Braço direito', parts: ['right-shoulder', 'right-upper-arm', 'right-elbow', 'right-forearm', 'right-hand'] },
    legs: { label: 'Pernas', parts: ['left-thigh', 'left-knee', 'left-shin', 'left-foot', 'right-thigh', 'right-knee', 'right-shin', 'right-foot'] },
  };

  const silhouette = `
    <svg class="cx-human-map" viewBox="0 0 520 900" role="img" aria-labelledby="cxHumanTitle cxHumanDescription">
      <title id="cxHumanTitle">Mapa anatômico digital do Condor X</title>
      <desc id="cxHumanDescription">Silhueta humana frontal dividida em regiões de projeto selecionáveis.</desc>
      <defs>
        <linearGradient id="cxBodyFill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1b4551"/><stop offset=".46" stop-color="#102a36"/><stop offset="1" stop-color="#081621"/></linearGradient>
        <radialGradient id="cxSelectedFill" cx="50%" cy="40%" r="72%"><stop offset="0" stop-color="#c9ffff" stop-opacity=".48"/><stop offset=".55" stop-color="#5eead4" stop-opacity=".24"/><stop offset="1" stop-color="#5eead4" stop-opacity=".09"/></radialGradient>
        <linearGradient id="cxScanFill" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5eead4" stop-opacity="0"/><stop offset=".5" stop-color="#d5ffff" stop-opacity=".72"/><stop offset="1" stop-color="#5eead4" stop-opacity="0"/></linearGradient>
        <filter id="cxBodyGlow" x="-45%" y="-25%" width="190%" height="150%"><feGaussianBlur stdDeviation="7" result="blur"/><feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.18 0 0 0 0 0.82 0 0 0 0 0.87 0 0 0 .34 0"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <filter id="cxCoreGlow" x="-120%" y="-120%" width="340%" height="340%"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>

        <path id="cxHeadShape" d="M260 34 C231 34 216 56 217 88 C218 106 223 124 232 138 C240 150 249 157 260 160 C271 157 280 150 288 138 C297 124 302 106 303 88 C304 56 289 34 260 34 Z"/>
        <path id="cxNeckShape" d="M238 145 C240 163 236 176 224 184 L229 218 C245 226 275 226 291 218 L296 184 C284 176 280 163 282 145 C274 154 268 160 260 161 C252 160 246 154 238 145 Z"/>
        <path id="cxChestShape" d="M225 181 C211 187 193 192 177 198 C157 205 145 221 145 243 C145 269 154 298 166 325 C176 346 184 367 190 390 C210 402 234 408 260 408 C286 408 310 402 330 390 C336 367 344 346 354 325 C366 298 375 269 375 243 C375 221 363 205 343 198 C327 192 309 187 295 181 C289 204 278 216 260 217 C242 216 231 204 225 181 Z"/>
        <path id="cxAbdomenShape" d="M190 376 C212 390 236 397 260 397 C284 397 308 390 330 376 C326 407 321 439 316 470 C300 480 281 486 260 486 C239 486 220 480 204 470 C199 439 194 407 190 376 Z"/>
        <path id="cxPelvisShape" d="M204 461 C220 472 240 479 260 479 C280 479 300 472 316 461 C322 484 323 510 317 532 C302 546 282 553 260 548 C238 553 218 546 203 532 C197 510 198 484 204 461 Z"/>
        <path id="cxLeftShoulderShape" d="M178 198 C158 201 145 216 141 239 C139 264 145 288 154 309 C166 316 181 315 193 306 L205 235 C204 216 195 203 178 198 Z"/>
        <path id="cxLeftUpperArmShape" d="M153 294 C143 307 138 329 138 351 L135 425 C135 445 142 458 155 462 C170 465 181 454 184 435 L193 321 C185 306 170 296 153 294 Z"/>
        <path id="cxLeftElbowShape" d="M136 420 C132 438 133 455 141 466 C149 477 164 478 174 469 C181 462 184 448 181 434 C169 426 151 421 136 420 Z"/>
        <path id="cxLeftForearmShape" d="M142 460 C133 478 128 500 124 525 L116 581 C113 600 119 614 131 619 C144 623 155 612 159 595 L174 475 C165 465 154 461 142 460 Z"/>
        <g id="cxLeftHandShape">
          <path d="M123 594 C116 605 113 621 117 635 C120 646 130 652 141 648 C153 644 160 633 158 620 C156 607 147 598 136 594 Z"/>
          <path d="M121 610 C111 613 103 622 100 634 C98 643 102 650 108 650 C114 650 118 643 120 636 L128 622 Z"/>
          <path d="M116 630 C111 642 109 658 112 670 C114 678 120 681 126 678 C131 675 131 669 130 662 L128 635 Z"/>
          <path d="M127 635 C124 649 124 670 128 681 C131 689 138 691 143 687 C148 683 146 675 145 669 L141 638 Z"/>
          <path d="M139 635 C138 651 141 670 146 679 C150 686 157 686 161 681 C165 676 161 669 159 663 L153 635 Z"/>
          <path d="M151 628 C153 642 158 657 164 664 C169 670 176 668 178 662 C180 657 174 651 171 646 L163 623 Z"/>
        </g>
        <path id="cxLeftThighShape" d="M205 520 C194 545 190 576 192 609 L198 689 C200 708 211 719 225 718 C240 717 250 704 252 684 L258 548 C244 543 225 534 205 520 Z"/>
        <path id="cxLeftKneeShape" d="M198 682 C195 699 198 717 207 727 C216 736 232 735 241 725 C248 717 251 701 247 686 C233 678 213 678 198 682 Z"/>
        <path id="cxLeftShinShape" d="M206 719 C196 740 190 769 192 797 C194 821 202 838 207 850 C211 860 224 863 234 856 C242 850 243 839 241 826 L242 726 C231 719 217 717 206 719 Z"/>
        <path id="cxLeftFootShape" d="M207 844 C205 856 199 864 187 871 C178 876 173 884 179 889 C190 897 224 897 243 891 C250 889 252 882 248 875 L235 852 C226 844 216 842 207 844 Z"/>
      </defs>

      <g class="cx-orbit-field" aria-hidden="true"><ellipse cx="260" cy="454" rx="188" ry="350"/><ellipse cx="260" cy="454" rx="218" ry="390"/><path d="M38 454 H482 M260 20 V884"/></g>
      <g class="cx-measure-rail" aria-hidden="true"><path d="M50 48 V875 M470 48 V875"/><path d="M50 62 h17 M50 142 h9 M50 222 h17 M50 302 h9 M50 382 h17 M50 462 h9 M50 542 h17 M50 622 h9 M50 702 h17 M50 782 h9 M50 862 h17"/><path d="M470 62 h-17 M470 142 h-9 M470 222 h-17 M470 302 h-9 M470 382 h-17 M470 462 h-9 M470 542 h-17 M470 622 h-9 M470 702 h-17 M470 782 h-9 M470 862 h-17"/></g>

      <g class="cx-human-body" filter="url(#cxBodyGlow)">
        <use href="#cxHeadShape" class="cx-human-part" data-zone="head"/><use href="#cxNeckShape" class="cx-human-part" data-zone="neck"/>
        <use href="#cxChestShape" class="cx-human-part" data-zone="chest"/><use href="#cxAbdomenShape" class="cx-human-part" data-zone="abdomen"/><use href="#cxPelvisShape" class="cx-human-part" data-zone="pelvis"/>
        <use href="#cxLeftShoulderShape" class="cx-human-part" data-zone="left-shoulder"/><use href="#cxLeftShoulderShape" class="cx-human-part" data-zone="right-shoulder" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftUpperArmShape" class="cx-human-part" data-zone="left-upper-arm"/><use href="#cxLeftUpperArmShape" class="cx-human-part" data-zone="right-upper-arm" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftElbowShape" class="cx-human-part" data-zone="left-elbow"/><use href="#cxLeftElbowShape" class="cx-human-part" data-zone="right-elbow" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftForearmShape" class="cx-human-part" data-zone="left-forearm"/><use href="#cxLeftForearmShape" class="cx-human-part" data-zone="right-forearm" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftHandShape" class="cx-human-part" data-zone="left-hand"/><use href="#cxLeftHandShape" class="cx-human-part" data-zone="right-hand" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftThighShape" class="cx-human-part" data-zone="left-thigh"/><use href="#cxLeftThighShape" class="cx-human-part" data-zone="right-thigh" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftKneeShape" class="cx-human-part" data-zone="left-knee"/><use href="#cxLeftKneeShape" class="cx-human-part" data-zone="right-knee" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftShinShape" class="cx-human-part" data-zone="left-shin"/><use href="#cxLeftShinShape" class="cx-human-part" data-zone="right-shin" transform="translate(520 0) scale(-1 1)"/>
        <use href="#cxLeftFootShape" class="cx-human-part" data-zone="left-foot"/><use href="#cxLeftFootShape" class="cx-human-part" data-zone="right-foot" transform="translate(520 0) scale(-1 1)"/>
      </g>
      <rect class="cx-body-scan" x="86" y="0" width="348" height="3" aria-hidden="true"/>
      <g class="cx-anatomy-lines" aria-hidden="true">
        <path d="M228 221 C245 232 275 232 292 221 M188 259 C213 245 237 247 255 261 M332 259 C307 245 283 247 265 261"/>
        <path d="M260 260 V460 M208 326 C226 339 243 342 256 338 M312 326 C294 339 277 342 264 338"/>
        <path d="M216 398 C231 407 246 410 256 407 M304 398 C289 407 274 410 264 407 M220 444 C234 451 247 453 256 451 M300 444 C286 451 273 453 264 451"/>
        <path d="M205 533 C220 547 238 553 254 551 M315 533 C300 547 282 553 266 551 M200 688 C214 681 232 682 246 691 M320 688 C306 681 288 682 274 691"/>
        <path d="M201 791 C214 784 230 786 242 795 M319 791 C306 784 290 786 278 795 M237 83 C245 78 252 76 260 76 C268 76 275 78 283 83 M260 84 V115 M245 134 C254 139 266 139 275 134"/>
      </g>
      <g class="cx-core" data-zone="power" filter="url(#cxCoreGlow)" role="button" tabindex="0" aria-label="Abrir centro"><circle cx="260" cy="294" r="31"/><path d="M274 278 A22 22 0 1 0 274 310"/><path d="M278 282 L285 275 M278 306 L285 313"/></g>
      <g class="cx-target-points" aria-hidden="true"><circle cx="260" cy="157" r="2.6"/><circle cx="155" cy="438" r="2.6"/><circle cx="365" cy="438" r="2.6"/><circle cx="222" cy="705" r="2.6"/><circle cx="298" cy="705" r="2.6"/></g>
    </svg>`;

  viewport.innerHTML = `<div class="cx-human-stage">${silhouette}</div>`;
  const model = viewport.querySelector('.cx-human-map');
  const hero = document.querySelector('.cx-hero-grid');
  const workspace = document.querySelector('.cx-workspace');
  const shell = document.querySelector('.cx-shell');
  const moduleList = document.querySelector('.cx-module-list');
  let selected = 'chest';
  let currentRegion = null;
  let currentItems = [];
  let currentParts = [];
  let active = !document.getElementById('projectDetail')?.hidden;
  let animationFrame = 0;

  if (!moduleList || !hero || !shell) {
    const mobileGroup = (id) => {
      if (id === 'power') return 'power';
      const group = GROUPS[id] ? id : REGIONS[id]?.group;
      if (group === 'torso') return 'chest';
      if (group === 'head-group') return 'head';
      return group || 'chest';
    };
    const selectMobileModule = (id, notify = false) => {
      const normalized = mobileGroup(id);
      const parts = GROUPS[normalized]?.parts || (normalized === 'chest' ? ['chest', 'abdomen', 'pelvis'] : [normalized]);
      model.querySelectorAll('[data-zone]').forEach((element) => element.classList.toggle('is-selected', parts.includes(element.dataset.zone)));
      if (notify) window.dispatchEvent(new CustomEvent('condor-x-picked', { detail: { id: normalized } }));
    };
    model.addEventListener('click', (event) => {
      const target = event.target.closest('[data-zone]');
      if (target) selectMobileModule(target.dataset.zone, true);
    });
    window.addEventListener('condor-x-select', (event) => selectMobileModule(event.detail.id));
    window.addEventListener('condor-x-visibility', (event) => viewport.classList.toggle('is-active', Boolean(event.detail?.active)));
    selectMobileModule('chest');
  } else {
  moduleList.innerHTML = Object.entries(GROUPS).map(([groupId, group]) => `
    <section class="cx-zone-group">
      <button class="cx-zone-group-button" type="button" data-cx-part="${groupId}"><strong>${group.label}</strong><em>${group.parts.length} ZONAS</em></button>
      <div class="cx-zone-subparts">${group.parts.map((id) => `<button type="button" data-cx-part="${id}">${REGIONS[id].label.replace(/ (esquerdo|esquerda|direito|direita)$/, '')}</button>`).join('')}</div>
    </section>`).join('');

  const regionView = document.createElement('section');
  regionView.className = 'cx-region-view';
  regionView.id = 'cxRegionView';
  regionView.hidden = true;
  regionView.innerHTML = `
    <header class="cx-region-header">
      <button class="cx-region-back" id="cxRegionBack" type="button">← CORPO COMPLETO</button>
      <div><small>CONDOR X · AMBIENTE DA REGIÃO</small><h1 id="cxRegionTitle">Região</h1><p id="cxRegionSubtitle">Ambiente vazio preparado para desenvolvimento.</p></div>
      <div class="cx-region-code" id="cxRegionCode">CX / REGIÃO</div>
    </header>
    <div class="cx-region-layout">
      <article class="cx-region-visual">
        <div class="cx-region-focus" id="cxRegionFocus"></div>
        <div class="cx-region-tabs" id="cxRegionTabs"></div>
      </article>
      <aside class="cx-region-board">
        <header><div><small>DESENVOLVIMENTO DA REGIÃO</small><h2>Rascunhos e registros</h2></div><button id="cxNewItem" type="button">+ NOVO</button></header>
        <div class="cx-region-counters"><span><strong id="cxCountComponents">0</strong><small>COMPONENTES</small></span><span><strong id="cxCountRequirements">0</strong><small>REQUISITOS</small></span><span><strong id="cxCountTests">0</strong><small>TESTES</small></span></div>
        <form class="cx-region-form" id="cxRegionForm" hidden>
          <label>TIPO<select id="cxItemType"><option value="componente">Peça / componente</option><option value="requisito">Requisito</option><option value="nota">Nota</option><option value="teste">Teste</option></select></label>
          <label>TÍTULO<input id="cxItemTitle" maxlength="180" required placeholder="Nome do registro"></label>
          <label>DETALHES<textarea id="cxItemDetails" maxlength="4000" rows="4" placeholder="Descreva somente o que estiver definido"></textarea></label>
          <div><button type="button" id="cxCancelItem">CANCELAR</button><button type="submit">SALVAR NO COFRE</button></div>
        </form>
        <div class="cx-region-message" id="cxRegionMessage" role="status"></div>
        <div class="cx-region-items" id="cxRegionItems"></div>
      </aside>
    </div>`;
  shell.insertBefore(regionView, workspace || null);

  const focus = document.getElementById('cxRegionFocus');
  const tabs = document.getElementById('cxRegionTabs');
  const regionTitle = document.getElementById('cxRegionTitle');
  const regionSubtitle = document.getElementById('cxRegionSubtitle');
  const regionCode = document.getElementById('cxRegionCode');
  const form = document.getElementById('cxRegionForm');
  const itemType = document.getElementById('cxItemType');
  const itemTitle = document.getElementById('cxItemTitle');
  const itemDetails = document.getElementById('cxItemDetails');
  const itemList = document.getElementById('cxRegionItems');
  const message = document.getElementById('cxRegionMessage');

  function regionParts(id) {
    return GROUPS[id]?.parts || [id];
  }

  function unionBox(ids) {
    const boxes = ids.map((id) => REGIONS[id].box);
    const minX = Math.min(...boxes.map((box) => box[0]));
    const minY = Math.min(...boxes.map((box) => box[1]));
    const maxX = Math.max(...boxes.map((box) => box[0] + box[2]));
    const maxY = Math.max(...boxes.map((box) => box[1] + box[3]));
    const padding = Math.max(18, Math.min(48, Math.max(maxX - minX, maxY - minY) * .09));
    return [minX - padding, minY - padding, maxX - minX + padding * 2, maxY - minY + padding * 2];
  }

  function selectModule(id, notify = false) {
    const parts = regionParts(id);
    selected = REGIONS[id] || GROUPS[id] ? id : 'chest';
    model.querySelectorAll('[data-zone]').forEach((element) => element.classList.toggle('is-selected', parts.includes(element.dataset.zone)));
    document.querySelectorAll('[data-cx-part]').forEach((button) => button.classList.toggle('active', button.dataset.cxPart === selected));
    if (notify) window.dispatchEvent(new CustomEvent('condor-x-picked', { detail: { id: selected } }));
  }

  function renderFocusedRegion(id) {
    const groupId = GROUPS[id] ? id : REGIONS[id].group;
    const displayParts = GROUPS[groupId].parts;
    const selectedParts = regionParts(id);
    const box = unionBox(displayParts);
    const clones = displayParts.flatMap((partId) => [...model.querySelectorAll(`[data-zone="${partId}"]`)].map((element) => ({ element, partId }))).map(({ element, partId }) => {
      const clone = element.cloneNode(true);
      clone.classList.toggle('is-selected', selectedParts.includes(partId));
      clone.classList.toggle('is-context', !selectedParts.includes(partId));
      clone.removeAttribute('tabindex');
      return clone.outerHTML;
    }).join('');
    focus.innerHTML = `<svg class="cx-region-map" viewBox="${box.join(' ')}" aria-hidden="true"><g class="cx-region-focus-body">${clones}</g></svg>`;
    tabs.innerHTML = GROUPS[groupId].parts.map((partId) => `<button type="button" data-region-tab="${partId}" class="${partId === id ? 'active' : ''}">${REGIONS[partId].label.replace(/ (esquerdo|esquerda|direito|direita)$/, '')}</button>`).join('');
  }

  function setMessage(text, error = false) {
    message.textContent = text;
    message.classList.toggle('error', error);
  }

  function renderItems() {
    const count = (type) => currentItems.filter((item) => item.tipo === type).length;
    document.getElementById('cxCountComponents').textContent = currentParts.length + count('componente');
    document.getElementById('cxCountRequirements').textContent = count('requisito');
    document.getElementById('cxCountTests').textContent = count('teste');
    itemList.replaceChildren();
    if (!currentItems.length && !currentParts.length) {
      const empty = document.createElement('div');
      empty.className = 'cx-region-empty';
      empty.innerHTML = '<span>○</span><strong>Nenhum registro nesta região</strong><p>Adicione somente quando houver uma decisão ou informação real.</p>';
      itemList.appendChild(empty);
      return;
    }
    currentParts.forEach((part) => {
      const card = document.createElement('article');
      card.className = `cx-region-item ${part.integrated ? 'integrated' : ''}`;
      const head = document.createElement('header');
      const type = document.createElement('small'); type.textContent = part.integrated ? 'PEÇA INTEGRADA' : 'RASCUNHO DE PEÇA';
      const state = document.createElement('span'); state.textContent = part.status.toUpperCase();
      head.append(type, state);
      const title = document.createElement('strong'); title.textContent = part.name;
      const details = document.createElement('p'); details.textContent = part.material ? `Material registrado: ${part.material}` : 'Material e propriedades ainda não definidos.';
      const actions = document.createElement('div'); actions.className = 'cx-part-action';
      const version = document.createElement('button'); version.type = 'button'; version.className = 'cx-part-version'; version.textContent = 'SALVAR NOVA VERSÃO';
      version.addEventListener('click', () => createPartVersion(part));
      actions.appendChild(version);
      if (!part.integrated) {
        const integrate = document.createElement('button'); integrate.type = 'button'; integrate.className = 'cx-part-integrate'; integrate.textContent = 'INTEGRAR AO MODELO';
        integrate.addEventListener('click', () => integratePart(part));
        actions.appendChild(integrate);
      }
      card.append(head, title, details, actions);
      itemList.appendChild(card);
    });
    currentItems.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'cx-region-item';
      const head = document.createElement('header');
      const type = document.createElement('small');
      type.textContent = item.tipo.toUpperCase();
      const status = document.createElement('select');
      [['rascunho', 'RASCUNHO'], ['planejado', 'PLANEJADO'], ['em_desenvolvimento', 'EM DESENVOLVIMENTO'], ['bloqueado', 'BLOQUEADO'], ['validado', 'VALIDADO']].forEach(([value, label]) => {
        const option = document.createElement('option'); option.value = value; option.textContent = label; option.selected = item.status === value; status.appendChild(option);
      });
      head.append(type, status);
      const title = document.createElement('strong'); title.textContent = item.titulo;
      const details = document.createElement('p'); details.textContent = item.detalhes || 'Sem detalhes registrados.';
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'cx-region-delete'; remove.textContent = 'EXCLUIR';
      status.addEventListener('change', () => updateItem(item, status.value));
      remove.addEventListener('click', () => deleteItem(item));
      card.append(head, title, details, remove);
      itemList.appendChild(card);
    });
  }

  async function loadItems() {
    if (!currentRegion) return;
    setMessage('Carregando registros...');
    try {
      const [itemsResponse, projectResponse] = await Promise.all([
        fetch(`/api/condor-x/regions/${encodeURIComponent(currentRegion)}/items`, { cache: 'no-store' }),
        fetch('/api/projects/condor-x', { cache: 'no-store' }),
      ]);
      const data = await itemsResponse.json();
      const projectData = await projectResponse.json();
      if (!itemsResponse.ok) throw new Error(data.erro || 'Não foi possível carregar os registros.');
      currentItems = data.items || [];
      currentParts = projectResponse.ok ? (projectData.parts || []).filter((part) => part.region === currentRegion) : [];
      setMessage('');
      renderItems();
    } catch (error) {
      currentItems = [];
      currentParts = [];
      renderItems();
      setMessage(error.message, true);
    }
  }

  async function updateItem(item, status) {
    setMessage('Salvando alteração...');
    try {
      const response = await fetch(`/api/condor-x/region-items/${encodeURIComponent(item.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ titulo: item.titulo, detalhes: item.detalhes, status }) });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.erro || 'Não foi possível salvar.');
      item.status = status;
      setMessage('Alteração salva no cofre local.');
    } catch (error) { setMessage(error.message, true); renderItems(); }
  }

  async function deleteItem(item) {
    if (!window.confirm(`Excluir o registro “${item.titulo}”?`)) return;
    setMessage('Excluindo registro...');
    try {
      const response = await fetch(`/api/condor-x/region-items/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.erro || 'Não foi possível excluir.');
      currentItems = currentItems.filter((current) => current.id !== item.id);
      setMessage('Registro excluído.');
      renderItems();
    } catch (error) { setMessage(error.message, true); }
  }

  async function createItem(event) {
    event.preventDefault();
    const titulo = itemTitle.value.trim();
    if (!titulo || !currentRegion) return;
    setMessage('Salvando no cofre local...');
    try {
      const creatingPart = itemType.value === 'componente';
      const response = await fetch(creatingPart ? '/api/projects/condor-x/parts' : `/api/condor-x/regions/${encodeURIComponent(currentRegion)}/items`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(creatingPart ? { region: currentRegion, name: titulo, type: 'component', notes: itemDetails.value.trim() } : { tipo: itemType.value, titulo, detalhes: itemDetails.value.trim() }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Não foi possível criar o registro.');
      if (creatingPart) currentParts.unshift(data.part);
      else currentItems.unshift(data.item);
      form.reset(); form.hidden = true;
      setMessage(creatingPart ? 'Rascunho criado fora do modelo principal.' : 'Registro salvo no cofre local.');
      renderItems();
    } catch (error) { setMessage(error.message, true); }
  }

  async function createPartVersion(part) {
    setMessage('Criando nova versão...');
    try {
      const response = await fetch(`/api/parts/${encodeURIComponent(part.id)}/versions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ snapshot: { name: part.name, region: part.region, type: part.type, material: part.material }, notes: 'Versão criada no ambiente da região.' }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Não foi possível criar a versão.');
      setMessage(`${data.version.label} criada e preservada no histórico.`);
    } catch (error) { setMessage(error.message, true); }
  }

  async function integratePart(part) {
    if (!window.confirm(`Integrar “${part.name}” ao modelo principal? O rascunho permanecerá no histórico.`)) return;
    setMessage('Integrando peça ao projeto...');
    try {
      const response = await fetch(`/api/parts/${encodeURIComponent(part.id)}/integrate`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Não foi possível integrar a peça.');
      Object.assign(part, data.part);
      setMessage('Peça integrada explicitamente ao modelo principal.');
      renderItems();
    } catch (error) { setMessage(error.message, true); }
  }

  function openRegion(id) {
    if (!REGIONS[id] && !GROUPS[id]) return;
    currentRegion = id;
    const label = REGIONS[id]?.label || GROUPS[id].label;
    const partCount = regionParts(id).length;
    selectModule(id, true);
    regionTitle.textContent = label;
    regionSubtitle.textContent = partCount > 1 ? `${partCount} zonas anatômicas disponíveis neste ambiente.` : 'Zona anatômica individual preparada para desenvolvimento.';
    regionCode.textContent = `CX / ${id.replaceAll('-', ' ').toUpperCase()}`;
    renderFocusedRegion(id);
    hero.hidden = true;
    if (workspace) workspace.hidden = true;
    regionView.hidden = false;
    form.hidden = true; form.reset(); setMessage('');
    fetch(`/api/projects/condor-x/regions/${encodeURIComponent(id)}/select`, { method: 'POST' })
      .then(() => { if (typeof CondorCoreUI !== 'undefined') CondorCoreUI.loadStatus(); })
      .catch(() => {});
    const detailView = document.getElementById('projectDetail');
    if (detailView) detailView.scrollTo({ top: 0, behavior: 'smooth' });
    loadItems();
  }

  function closeRegion() {
    currentRegion = null;
    regionView.hidden = true;
    hero.hidden = false;
    if (workspace) workspace.hidden = false;
    form.hidden = true; setMessage('');
    selectModule('chest');
  }

  model.addEventListener('click', (event) => {
    const target = event.target.closest('[data-zone]');
    if (target) openRegion(target.dataset.zone);
  });
  model.addEventListener('keydown', (event) => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[data-zone]')) { event.preventDefault(); openRegion(event.target.dataset.zone); }
  });
  moduleList.addEventListener('click', (event) => {
    const target = event.target.closest('[data-cx-part]');
    if (target) openRegion(target.dataset.cxPart);
  });
  tabs.addEventListener('click', (event) => {
    const target = event.target.closest('[data-region-tab]');
    if (target) openRegion(target.dataset.regionTab);
  });
  document.getElementById('cxRegionBack').addEventListener('click', closeRegion);
  document.getElementById('cxNewItem').addEventListener('click', () => { form.hidden = false; itemTitle.focus(); });
  document.getElementById('cxCancelItem').addEventListener('click', () => { form.hidden = true; form.reset(); });
  form.addEventListener('submit', createItem);

  viewport.addEventListener('pointermove', (event) => {
    if (!active || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const rect = viewport.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - .5) * 2;
    const y = ((event.clientY - rect.top) / rect.height - .5) * 2;
    cancelAnimationFrame(animationFrame);
    animationFrame = requestAnimationFrame(() => { model.style.setProperty('--cx-parallax-x', `${x * 4}px`); model.style.setProperty('--cx-parallax-y', `${y * 2.5}px`); });
  });
  viewport.addEventListener('pointerleave', () => { model.style.setProperty('--cx-parallax-x', '0px'); model.style.setProperty('--cx-parallax-y', '0px'); });

  window.addEventListener('condor-x-select', (event) => selectModule(event.detail.id));
  window.addEventListener('condor-x-region-close', closeRegion);
  window.addEventListener('condor-x-visibility', (event) => { active = Boolean(event.detail?.active); viewport.classList.toggle('is-active', active); if (!active) closeRegion(); });
  window.addEventListener('condor-x-resize', () => viewport.style.setProperty('--cx-viewport-ratio', String(viewport.clientWidth / Math.max(viewport.clientHeight, 1))));

  selectModule('chest');
  viewport.classList.toggle('is-active', active);
  }
}
