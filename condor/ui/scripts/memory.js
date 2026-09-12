/**
 * Memória operacional do Condor.
 *
 * Mostra todos os fatos do cofre em blocos, liga somente associações que o
 * backend consegue explicar e mantém relações confirmadas separadas de
 * sugestões. Nenhum agrupamento visual altera ou apaga a memória persistida.
 */
const CondorMemoria = (() => {
  const $ = (id) => document.getElementById(id);
  const CORES = {
    pessoal: '#8b7cff', trabalho: '#5eead4', preferencia: '#f472b6',
    rotina: '#94a3b8', projeto: '#48df9b', tecnico: '#fac775', geral: '#c4b5fd',
  };
  const NOMES_CATEGORIA = {
    pessoal: 'PESSOAL', trabalho: 'TRABALHO', preferencia: 'PREFERÊNCIAS',
    rotina: 'ROTINA', projeto: 'PROJETOS', tecnico: 'TÉCNICO', geral: 'GERAL',
  };
  const ORDEM_CATEGORIAS = ['trabalho', 'pessoal', 'projeto', 'preferencia', 'rotina', 'tecnico', 'geral'];
  let mapaAtual = null;
  let categoriaAtiva = 'todos';
  let buscaAtual = '';
  let fatoSelecionado = null;
  let carregando = false;
  let orbitaAtual = null;
  let zoomOrbital = 1;
  let archiveBefore = null;

  function init() {
    $('conversationArchiveMore').addEventListener('click', async () => {
      const button=$('conversationArchiveMore'); button.disabled=true;
      try {
        const response=await fetch('/api/conversa/arquivo'+(archiveBefore ? `?antes=${archiveBefore}` : ''),{cache:'no-store'});
        const data=await response.json(); if(!response.ok) throw new Error(data.erro || 'Cofre indisponível');
        for(const item of data.itens) {
          const article=document.createElement('article'); article.className='memory-recent';
          const heading=document.createElement('strong'); heading.textContent=`${item.papel==='user'?'VOCÊ':'CONDOR'} · ${new Date(item.ts*1000).toLocaleString('pt-BR')}`;
          const body=document.createElement('p'); body.textContent=item.conteudo;body.style.whiteSpace='pre-wrap';
          article.append(heading,body);$('conversationArchiveItems').append(article);
        }
        archiveBefore=data.proximo;button.hidden=!archiveBefore;button.textContent='CARREGAR MAIS ANTIGAS';
        if(!data.itens.length) $('conversationArchiveItems').textContent='Nenhuma conversa armazenada.';
      } catch(error) { CondorConversa.mostrarAviso(error.message,true); }
      finally { button.disabled=false; }
    });
    $('memorySearch')?.addEventListener('input', (event) => {
      buscaAtual = String(event.target.value || '').trim().toLocaleLowerCase('pt-BR');
      renderizar();
    });
    $('memoryRefresh')?.addEventListener('click', () => atualizar(true));
    window.addEventListener('resize', () => requestAnimationFrame(desenharLigacoes));
    window.addEventListener('condor-security-ready', () => atualizar(true));
    CondorWS.ao('memoria.stats', () => atualizar());
    CondorWS.ao('core.event', (mensagem) => {
      if (mensagem.event?.type === 'MEMORY_LEARNED') atualizar(true);
    });
    setInterval(() => {
      if (CondorRouter.atual() === 'memoria') atualizar();
    }, 30000);
    atualizar();
  }

  async function atualizar(destacar = false) {
    if (carregando) return;
    carregando = true;
    const botao = $('memoryRefresh');
    if (botao) { botao.disabled = true; botao.textContent = 'ANALISANDO...'; }
    if (!mapaAtual && $('memoryChainBoard')) {
      $('memoryChainBoard').innerHTML = '<div class="memory-loading">LENDO TODAS AS MEMÓRIAS E MONTANDO AS ÓRBITAS...</div>';
    }
    try {
      const [mapaResponse, fluxoResponse] = await Promise.all([
        fetch('/api/memoria/mapa', { cache: 'no-store' }),
        fetch('/api/memoria/fluxo', { cache: 'no-store' }),
      ]);
      if (!mapaResponse.ok) throw new Error(`mapa recusado (${mapaResponse.status})`);
      if (!fluxoResponse.ok) throw new Error(`fluxo recusado (${fluxoResponse.status})`);
      mapaAtual = await mapaResponse.json();
      const fluxo = await fluxoResponse.json();
      renderizar();
      pintarFluxo(fluxo.itens || [], destacar);
    } catch (erro) {
      console.warn('[memoria] não consegui carregar o mapa completo', erro);
      if ($('memoryChainBoard')) {
        $('memoryChainBoard').innerHTML = `<div class="memory-orbit-empty">MEMÓRIA INDISPONÍVEL · ${escapar(erro.message)}</div>`;
      }
      if ($('memoryAnalysisState')) $('memoryAnalysisState').textContent = 'AGUARDANDO O COFRE';
    } finally {
      carregando = false;
      if (botao) { botao.disabled = false; botao.textContent = 'ATUALIZAR'; }
    }
  }

  function renderizar() {
    if (!mapaAtual) return;
    pintarFiltros();
    pintarInteligencia();
    pintarEntidades();
    pintarRelacoesConfirmadas();
    pintarCadeias();
    if (fatoSelecionado && fatosVisiveis().some(f => Number(f.id) === Number(fatoSelecionado))) {
      selecionarFato(fatoSelecionado, false);
    } else {
      limparSelecao();
    }
  }

  function fatosVisiveis() {
    return (mapaAtual?.fatos || []).filter((fato) => {
      if (categoriaAtiva !== 'todos' && fato.categoria !== categoriaAtiva) return false;
      if (!buscaAtual) return true;
      return `${fato.categoria} ${fato.chave} ${fato.valor} ${fato.origem}`
        .toLocaleLowerCase('pt-BR').includes(buscaAtual);
    });
  }

  function pintarFiltros() {
    const alvo = $('memoryFilters');
    if (!alvo) return;
    const contagens = {};
    (mapaAtual.fatos || []).forEach((fato) => {
      contagens[fato.categoria] = (contagens[fato.categoria] || 0) + 1;
    });
    const filtros = [['todos', mapaAtual.fatos.length], ...Object.entries(contagens).sort()];
    alvo.innerHTML = filtros.map(([categoria, quantidade]) => `
      <button type="button" class="${categoriaAtiva === categoria ? 'active' : ''}"
              data-memory-category="${escapar(categoria)}">
        ${categoria === 'todos' ? 'TUDO' : escapar(categoria.toUpperCase())} · ${quantidade}
      </button>`).join('');
    alvo.querySelectorAll('[data-memory-category]').forEach((botao) => {
      botao.addEventListener('click', () => {
        categoriaAtiva = botao.dataset.memoryCategory || 'todos';
        renderizar();
      });
    });
  }

  function pintarInteligencia() {
    const inteligencia = mapaAtual.inteligencia || {};
    const visiveis = fatosVisiveis().length;
    texto('statFacts', visiveis);
    texto('statNodes', inteligencia.entidades || 0);
    texto('statChains', inteligencia.cadeias || 0);
    texto('statEdges', inteligencia.associacoes_sugeridas || 0);
    texto('statConfirmedEdges', inteligencia.relacoes_confirmadas || 0);
    texto('statSemantic', `${inteligencia.cobertura_semantica || 0}/${inteligencia.fatos || 0}`);
    const conectados = Math.max(0, (inteligencia.fatos || 0) - (inteligencia.isoladas || 0));
    texto('memoryAnalysisState', `${conectados} FATOS EM CADEIAS · ${inteligencia.isoladas || 0} ISOLADOS`);
    texto('memoryLastUpdate', inteligencia.atualizado
      ? new Date(inteligencia.atualizado * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
      : 'SEM FATOS');
  }

  function pintarCadeias() {
    const alvo = $('memoryChainBoard');
    if (!alvo) return;
    const visiveis = fatosVisiveis();
    if (!visiveis.length) {
      alvo.innerHTML = `<div class="memory-orbit-empty">${mapaAtual.fatos.length ? 'NENHUMA MEMÓRIA CORRESPONDE AO FILTRO' : 'AINDA NÃO HÁ MEMÓRIAS NO COFRE'}</div>`;
      return;
    }
    const layout = construirOrbita(visiveis);
    orbitaAtual = layout;
    zoomOrbital = 1;
    const idsVisiveis = new Set(visiveis.map(fato => Number(fato.id)));
    const associacoes = (mapaAtual.associacoes_sugeridas || []).filter(
      ligacao => idsVisiveis.has(Number(ligacao.de)) && idsVisiveis.has(Number(ligacao.para)),
    );
    const linhasCategorias = layout.categorias.map(categoria =>
      `<path class="memory-trunk" d="M ${layout.centro.x} ${layout.centro.y} Q ${(layout.centro.x + categoria.x) / 2} ${(layout.centro.y + categoria.y) / 2 - 24} ${categoria.x} ${categoria.y}"/>`,
    ).join('');
    const linhasFatos = layout.fatos.map(item => {
      const categoria = layout.porCategoria.get(item.fato.categoria);
      return `<path class="memory-branch" style="--memory-color:${item.cor}" d="M ${categoria.x} ${categoria.y} L ${item.x.toFixed(1)} ${item.y.toFixed(1)}"/>`;
    }).join('');
    const linhasAssociacoes = associacoes.map(ligacao => {
      const de = layout.porFato.get(Number(ligacao.de));
      const para = layout.porFato.get(Number(ligacao.para));
      if (!de || !para) return '';
      return `<path class="memory-association" d="M ${de.x.toFixed(1)} ${de.y.toFixed(1)} L ${para.x.toFixed(1)} ${para.y.toFixed(1)}"><title>${escapar(ligacao.rotulo || 'memórias relacionadas')}</title></path>`;
    }).join('');
    const categoriasSvg = layout.categorias.map(categoria => `
      <g class="memory-category-node" data-orbit-category="${escapar(categoria.nome)}" tabindex="0" role="button"
         aria-label="Área ${escapar(nomeCategoria(categoria.nome))}, ${categoria.fatos.length} memórias"
         style="--memory-color:${categoria.cor}" transform="translate(${categoria.x.toFixed(1)} ${categoria.y.toFixed(1)})">
        <circle class="category-halo" r="61"/><circle class="category-core" r="44"/>
        <text class="memory-category-name" y="-3">${escapar(nomeCategoria(categoria.nome))}</text>
        <text class="memory-category-count" y="16">${categoria.fatos.length} MEMÓRIAS</text>
      </g>`).join('');
    const fatosSvg = layout.fatos.map(item => {
      const chave = resumir(String(item.fato.chave || '').replaceAll('_', ' '), 19).toUpperCase();
      const valor = resumir(item.fato.valor, 27);
      return `<g class="memory-fact-node" data-fact-id="${Number(item.fato.id)}" tabindex="0" role="button"
        aria-label="${escapar(item.fato.valor)}" style="--memory-color:${item.cor}"
        transform="translate(${item.x.toFixed(1)} ${item.y.toFixed(1)})">
        <rect class="fact-halo" x="-66" y="-32" width="132" height="64" rx="18"/>
        <rect class="fact-block" x="-58" y="-25" width="116" height="50" rx="12"/>
        <text class="memory-fact-key" y="-4">${escapar(chave)}</text>
        <text class="memory-fact-value" y="14">${escapar(valor)}</text>
        <title>${escapar(item.fato.valor)}</title>
      </g>`;
    }).join('');
    alvo.innerHTML = `<div class="memory-orbit-controls" aria-label="Zoom do mapa">
        <button type="button" data-memory-zoom="out" title="Diminuir">−</button>
        <button type="button" data-memory-zoom="reset" title="Centralizar">CENTRO</button>
        <button type="button" data-memory-zoom="in" title="Aumentar">+</button>
      </div>
      <svg class="memory-orbit-svg" id="memoryOrbitSvg" viewBox="0 0 ${layout.largura} ${layout.altura}" role="img" aria-label="Memórias organizadas por área ao redor do núcleo do Condor">
        <defs>
          <radialGradient id="memoryCoreGradient"><stop offset="0" stop-color="#54ff98" stop-opacity=".75"/><stop offset=".28" stop-color="#123c31"/><stop offset="1" stop-color="#061019"/></radialGradient>
          <linearGradient id="memoryTrunkGradient"><stop stop-color="#48ff91"/><stop offset="1" stop-color="#8b7cff"/></linearGradient>
          <filter id="memoryCoreGlow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          <filter id="memorySoftGlow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <g aria-hidden="true">${linhasCategorias}${linhasFatos}${linhasAssociacoes}</g>
        ${categoriasSvg}${fatosSvg}
        <g class="memory-core" transform="translate(${layout.centro.x} ${layout.centro.y})">
          <circle class="memory-core-ring outer" r="104"/><circle class="memory-core-ring" r="82"/>
          <circle class="memory-core-orb" r="65"/><circle class="memory-core-dot" r="7" cy="-25"/>
          <text class="memory-core-title" y="5">CONDOR</text><text class="memory-core-subtitle" y="25">${visiveis.length} MEMÓRIAS</text>
        </g>
      </svg><div class="memory-orbit-caption"><i></i>NÚCLEO → ÁREAS → MEMÓRIAS RELACIONADAS</div>`;
    vincularOrbita(alvo);
  }

  function construirOrbita(fatos) {
    const grupos = new Map();
    fatos.forEach(fato => {
      const categoria = fato.categoria || 'geral';
      if (!grupos.has(categoria)) grupos.set(categoria, []);
      grupos.get(categoria).push(fato);
    });
    const entradas = [...grupos.entries()].sort((a, b) => {
      const ia = ORDEM_CATEGORIAS.indexOf(a[0]), ib = ORDEM_CATEGORIAS.indexOf(b[0]);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a[0].localeCompare(b[0]);
    });
    const maiorGrupo = Math.max(...entradas.map(([, itens]) => itens.length), 1);
    let restantes = maiorGrupo, anel = 0;
    while (restantes > 0) { restantes -= 6 + anel * 4; anel += 1; }
    const alcanceGrupo = 120 + Math.max(0, anel - 1) * 72;
    const raioX = Math.max(430, 285 + alcanceGrupo * 1.12);
    const raioY = Math.max(300, 205 + alcanceGrupo * .72);
    const largura = Math.ceil(Math.max(1420, (raioX + alcanceGrupo + 120) * 2));
    const altura = Math.ceil(Math.max(900, (raioY + alcanceGrupo + 100) * 2));
    const centro = { x: largura / 2, y: altura / 2 };
    const categorias = entradas.map(([nome, itens], indice) => {
      const angulo = -Math.PI / 2 + indice * (Math.PI * 2 / entradas.length);
      return { nome, fatos: itens, cor: CORES[nome] || CORES.geral, angulo,
        x: centro.x + Math.cos(angulo) * raioX, y: centro.y + Math.sin(angulo) * raioY };
    });
    const todosFatos = [];
    categorias.forEach(categoria => {
      let cursor = 0, indiceAnel = 0;
      while (cursor < categoria.fatos.length) {
        const capacidade = 6 + indiceAnel * 4;
        const itens = categoria.fatos.slice(cursor, cursor + capacidade);
        const raio = 122 + indiceAnel * 72;
        itens.forEach((fato, posicao) => {
          const angulo = categoria.angulo + .35 * indiceAnel + posicao * (Math.PI * 2 / itens.length);
          todosFatos.push({ fato, cor: CORES[fato.categoria] || CORES.geral,
            x: categoria.x + Math.cos(angulo) * raio,
            y: categoria.y + Math.sin(angulo) * raio });
        });
        cursor += itens.length;
        indiceAnel += 1;
      }
    });
    return { largura, altura, centro, categorias, fatos: todosFatos,
      porCategoria: new Map(categorias.map(item => [item.nome, item])),
      porFato: new Map(todosFatos.map(item => [Number(item.fato.id), item])) };
  }

  function vincularOrbita(alvo) {
    alvo.querySelectorAll('[data-fact-id]').forEach(no => {
      const abrir = () => selecionarFato(Number(no.dataset.factId));
      no.addEventListener('click', abrir);
      no.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); abrir(); }
      });
    });
    alvo.querySelectorAll('[data-orbit-category]').forEach(no => {
      const filtrar = () => {
        const categoria = no.dataset.orbitCategory || 'todos';
        categoriaAtiva = categoriaAtiva === categoria ? 'todos' : categoria;
        renderizar();
      };
      no.addEventListener('click', filtrar);
      no.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); filtrar(); }
      });
    });
    alvo.querySelectorAll('[data-memory-zoom]').forEach(botao => botao.addEventListener('click', () => {
      const acao = botao.dataset.memoryZoom;
      zoomOrbital = acao === 'reset' ? 1 : Math.max(.65, Math.min(2.4, zoomOrbital * (acao === 'in' ? 1.22 : .82)));
      aplicarZoomOrbital();
    }));
    aplicarZoomOrbital();
  }

  function aplicarZoomOrbital() {
    const svg = $('memoryOrbitSvg');
    if (!svg || !orbitaAtual) return;
    const largura = orbitaAtual.largura / zoomOrbital, altura = orbitaAtual.altura / zoomOrbital;
    svg.setAttribute('viewBox', `${(orbitaAtual.centro.x - largura / 2).toFixed(1)} ${(orbitaAtual.centro.y - altura / 2).toFixed(1)} ${largura.toFixed(1)} ${altura.toFixed(1)}`);
  }

  function desenharLigacoes() {
    aplicarZoomOrbital();
  }

  function nomeCategoria(categoria) {
    return NOMES_CATEGORIA[categoria] || String(categoria || 'geral').replaceAll('_', ' ').toUpperCase();
  }

  function resumir(valor, limite) {
    const textoLimpo = String(valor || '').replace(/\s+/g, ' ').trim();
    return textoLimpo.length > limite ? `${textoLimpo.slice(0, limite - 1)}…` : textoLimpo;
  }

  function selecionarFato(id, rolar = true) {
    fatoSelecionado = Number(id);
    const fato = (mapaAtual.fatos || []).find(item => Number(item.id) === fatoSelecionado);
    if (!fato) return limparSelecao();
    const ligacoes = (mapaAtual.associacoes_sugeridas || []).filter(
      item => Number(item.de) === fatoSelecionado || Number(item.para) === fatoSelecionado,
    );
    const relacionados = new Set(ligacoes.flatMap(item => [Number(item.de), Number(item.para)]));
    document.querySelectorAll('.memory-fact-node').forEach((bloco) => {
      const blocoId = Number(bloco.dataset.factId);
      bloco.classList.toggle('selected', blocoId === fatoSelecionado);
      bloco.classList.toggle('related', blocoId !== fatoSelecionado && relacionados.has(blocoId));
      bloco.classList.toggle('dimmed', !relacionados.has(blocoId));
    });
    pintarSelecionado(fato, ligacoes);
    if (rolar) document.querySelector(`[data-fact-id="${fatoSelecionado}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function pintarSelecionado(fato, ligacoes) {
    texto('memorySelectedStatus', `${ligacoes.length} ASSOCIAÇÕES`);
    const porId = new Map(mapaAtual.fatos.map(item => [Number(item.id), item]));
    const relacionados = ligacoes.map((ligacao) => {
      const outroId = Number(ligacao.de) === Number(fato.id) ? Number(ligacao.para) : Number(ligacao.de);
      return { ligacao, fato: porId.get(outroId) };
    }).filter(item => item.fato);
    const lista = relacionados.length ? `<div class="memory-related-list">${relacionados.map(({ ligacao, fato: outro }) => `
      <button type="button" data-related-id="${Number(outro.id)}"><b>${escapar(ligacao.rotulo.toUpperCase())} · ${Math.round(ligacao.pontuacao * 100)}%</b>${escapar(outro.valor)}${ligacao.evidencia?.length ? `<br><small>EVIDÊNCIA: ${escapar(ligacao.evidencia.join(', '))}</small>` : ''}</button>`).join('')}</div>` : '<p style="margin-top:10px">Este fato ainda não tem uma associação justificável.</p>';
    $('memorySelected').innerHTML = `<h3>${escapar(fato.valor)}</h3>
      <div class="memory-selected-meta"><span>CHAVE<b>${escapar(fato.chave)}</b></span><span>CATEGORIA<b>${escapar(fato.categoria)}</b></span><span>ORIGEM<b>${escapar(fato.origem || 'local')}</b></span><span>ACESSOS<b>${Number(fato.acessos || 0)}</b></span></div>${lista}`;
    $('memorySelected').querySelectorAll('[data-related-id]').forEach((botao) => {
      botao.addEventListener('click', () => selecionarFato(Number(botao.dataset.relatedId)));
    });
  }

  function limparSelecao() {
    fatoSelecionado = null;
    document.querySelectorAll('.memory-fact-node').forEach(bloco => bloco.classList.remove('selected', 'related', 'dimmed'));
    texto('memorySelectedStatus', 'SELECIONE UM BLOCO');
    if ($('memorySelected')) $('memorySelected').innerHTML = '<p>Clique em uma memória para ver sua origem, confiança e por que ela está ligada a outras.</p>';
  }

  function pintarEntidades() {
    const alvo = $('memoryEntities');
    if (!alvo) return;
    const entidades = mapaAtual.entidades || [];
    alvo.innerHTML = entidades.length ? entidades.map(entidade => `<div class="memory-entity"><strong>${escapar(entidade.nome)}</strong><span>${escapar(entidade.tipo.toUpperCase())} · ${entidade.mencoes} MENÇÕES${entidade.resumo ? ` · ${escapar(entidade.resumo)}` : ''}</span></div>`).join('') : '<div class="memory-recent">NENHUMA ENTIDADE EXTRAÍDA</div>';
  }

  function pintarRelacoesConfirmadas() {
    const alvo = $('memoryConfirmedRelations');
    if (!alvo) return;
    const relacoes = mapaAtual.relacoes_confirmadas || [];
    alvo.innerHTML = relacoes.length ? relacoes.map(relacao => `<div class="memory-relation"><strong>${escapar(relacao.de_nome)} → ${escapar(relacao.para_nome)}</strong><span>${escapar(String(relacao.tipo).toUpperCase())} · FORÇA ${Number(relacao.forca || 0).toFixed(1)}</span></div>`).join('') : '<div class="memory-recent">NENHUMA RELAÇÃO CONFIRMADA</div>';
  }

  function pintarFluxo(itens, destacar = false) {
    const alvo = $('memStream');
    if (!alvo) return;
    alvo.innerHTML = itens.length ? itens.map((item, indice) => {
      const data = new Date((item.ts || 0) * 1000);
      const hora = data.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      return `<div class="memory-recent ${destacar && indice === 0 ? 'new' : ''}">${escapar(item.texto)}<span>${escapar(String(item.categoria || 'pessoal').toUpperCase())} · ${hora}</span></div>`;
    }).join('') : '<div class="memory-recent">NADA APRENDIDO AINDA</div>';
  }

  function texto(id, valor) {
    if ($(id)) $(id).textContent = String(valor);
  }

  function escapar(valor) {
    const div = document.createElement('div');
    div.textContent = valor == null ? '' : String(valor);
    return div.innerHTML;
  }

  return { init, atualizar };
})();
