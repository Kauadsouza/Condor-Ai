/**
 * Texto formatado das respostas (negrito, itálico, listas, código e links),
 * como no chat do PC. Tudo é escapado ANTES de virar HTML: nada que venha do
 * modelo ou de uma página consegue injetar tag ou script.
 */
const CondorTexto = (() => {
  const escapar = (valor) => String(valor ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  function emLinha(texto) {
    return texto
      .replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')
      .replace(/\[([^\]\n]{1,120})\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,
        '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  }

  function html(bruto) {
    const blocos = String(bruto ?? '').split(/```/);
    let saida = '';
    blocos.forEach((bloco, i) => {
      if (i % 2 === 1) {
        // Bloco de código: primeira linha pode ser a linguagem.
        const semLinguagem = bloco.replace(/^[\w+-]{1,20}\n/, '');
        saida += `<pre><code>${escapar(semLinguagem.replace(/\n$/, ''))}</code></pre>`;
        return;
      }
      const linhas = escapar(bloco).split('\n');
      let lista = '';
      const fecharLista = () => { if (lista) { saida += `</${lista}>`; lista = ''; } };
      linhas.forEach((linha) => {
        const item = linha.match(/^\s*[-•*]\s+(.*)$/);
        const numero = linha.match(/^\s*\d+[.)]\s+(.*)$/);
        if (item || numero) {
          const tipo = item ? 'ul' : 'ol';
          if (lista !== tipo) { fecharLista(); saida += `<${tipo}>`; lista = tipo; }
          saida += `<li>${emLinha((item || numero)[1])}</li>`;
          return;
        }
        fecharLista();
        const titulo = linha.match(/^\s*#{1,4}\s+(.*)$/);
        if (titulo) { saida += `<p><strong>${emLinha(titulo[1])}</strong></p>`; return; }
        if (linha.trim()) saida += `<p>${emLinha(linha)}</p>`;
      });
      fecharLista();
    });
    return saida;
  }

  return { html, escapar };
})();
