/**
 * CondorCell — o CONDOR no iPhone, pelo Tailscale.
 *
 * Quatro passos, cada um com o estado real do PC: Tailscale instalado, conta
 * conectada, iPhone na mesma conta e o CONDOR publicado na rede privada. Com
 * isso pronto, o QR code (uso único, 5 minutos) pareia o iPhone, que ainda
 * confirma a palavra de acesso. Os aparelhos pareados podem ser revogados aqui.
 */
const CondorCell = (() => {
  const $ = (id) => document.getElementById(id);
  let dados = null;
  let relogio = null;

  const escapar = (valor) => String(valor ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  function init() {
    $('celRefresh')?.addEventListener('click', atualizar);
    $('celEntrar')?.addEventListener('click', () => agir('/api/celular/entrar-tailscale', 'ABRINDO O LOGIN NO NAVEGADOR...'));
    $('celLigar')?.addEventListener('click', () => agir('/api/celular/ligar', 'LIGANDO NA REDE PRIVADA...'));
    $('celConvite')?.addEventListener('click', () => agir('/api/celular/convite', 'GERANDO QR CODE...'));
    $('celAparelhos')?.addEventListener('click', (evento) => {
      const botao = evento.target.closest('[data-revogar]');
      if (botao) agir('/api/celular/revogar', 'REVOGANDO...', { id: botao.dataset.revogar });
    });
  }

  async function pedir(caminho, corpo) {
    const opcoes = corpo === undefined ? { cache: 'no-store' } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
    };
    const resposta = await fetch(caminho, opcoes);
    const json = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw new Error(json.erro || `falha ${resposta.status}`);
    return json;
  }

  async function atualizar() {
    try { pintar(await pedir('/api/celular')); } catch (erro) { mensagem(`INDISPONÍVEL · ${erro.message}`); }
  }

  async function agir(caminho, aviso, corpo = {}) {
    mensagem(aviso);
    try {
      const resposta = await pedir(caminho, corpo);
      pintar(resposta);
      if (resposta.precisa_liberar) mensagem('LIBERE O HTTPS NA PÁGINA DO TAILSCALE QUE ABRIU E CLIQUE LIGAR DE NOVO.');
      else if (caminho.endsWith('entrar-tailscale') && resposta.link) mensagem('ENTRE NA SUA CONTA NO NAVEGADOR E VOLTE AQUI.');
      else if (caminho.endsWith('ligar') && !resposta.ok) mensagem(`NÃO LIGOU · ${resposta.erro || 'veja o Tailscale'}`);
      else mensagem('');
    } catch (erro) {
      mensagem(`ERRO · ${erro.message.toUpperCase()}`);
    }
  }

  function mensagem(texto) { const alvo = $('celMsg'); if (alvo) alvo.textContent = texto; }

  function passo(id, feito, texto) {
    const item = $(id);
    if (!item) return;
    item.classList.toggle('feito', feito);
    item.querySelector('em').textContent = texto;
  }

  function pintar(novo) {
    dados = novo;
    const ts = novo.tailscale || {};
    passo('celPassoInstalar', ts.instalado, ts.instalado ? 'INSTALADO' : 'BAIXE EM TAILSCALE.COM/DOWNLOAD');
    passo('celPassoEntrar', ts.logado, ts.logado ? ts.dns.toUpperCase() : 'NÃO CONECTADO');
    passo('celPassoLigar', novo.publicado, novo.publicado ? 'NA REDE PRIVADA' : 'DESLIGADO');
    $('celEntrar').hidden = !ts.instalado || ts.logado;
    $('celLigar').hidden = !ts.logado || novo.publicado;
    $('celConvite').disabled = !novo.publicado;

    const qr = $('celQr');
    clearInterval(relogio);
    if (novo.convite && novo.convite.qr) {
      qr.innerHTML = `<img alt="QR code para parear o iPhone" src="${escapar(novo.convite.qr)}">`;
      const vence = () => {
        const resta = Math.max(0, Math.round(novo.convite.expira_em - Date.now() / 1000));
        $('celQrHint').textContent = resta ? `APONTE A CÂMERA DO IPHONE · VALE ${Math.floor(resta / 60)}:${String(resta % 60).padStart(2, '0')}` : 'EXPIROU · GERE OUTRO';
        if (!resta) { clearInterval(relogio); qr.innerHTML = '<span>QR</span>'; }
      };
      vence(); relogio = setInterval(vence, 1000);
    } else {
      qr.innerHTML = '<span>QR</span>';
      $('celQrHint').textContent = novo.publicado ? 'GERE O QR CODE E APONTE A CÂMERA DO IPHONE.' : 'TERMINE OS PASSOS AO LADO PRIMEIRO.';
    }

    const lista = novo.aparelhos || [];
    $('celAparelhos').innerHTML = lista.length ? lista.map((aparelho) => `
      <div class="cel-device"><div><strong>${escapar(aparelho.nome)}</strong>
      <span>PAREADO ${new Date(aparelho.criado * 1000).toLocaleDateString('pt-BR')} · VISTO ${new Date(aparelho.visto * 1000).toLocaleString('pt-BR')}</span></div>
      <button type="button" data-revogar="${escapar(aparelho.id)}">REVOGAR</button></div>`).join('')
      : '<div class="core-empty">NENHUM IPHONE PAREADO</div>';
    $('celConectados').textContent = novo.conectados ? `${novo.conectados} CONECTADO${novo.conectados > 1 ? 'S' : ''} AGORA` : '';
  }

  return { init, atualizar };
})();
