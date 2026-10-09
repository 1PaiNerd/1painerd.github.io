(function () {
  'use strict';
  const assetName = 'enquanto-voce-briga-eles-lucram.pdf';
  const endpoint = 'https://api.github.com/repos/1PaiNerd/1painerd.github.io/releases/tags/livro-2026-10';
  const counter = document.getElementById('counter');
  const local = ['127.0.0.1', 'localhost', ''].includes(location.hostname);
  if (local) {
    document.getElementById('preview').hidden = false;
    document.querySelectorAll('.download').forEach(a => {
      a.href = 'assets/' + assetName;
      a.download = assetName;
    });
    counter.textContent = 'Prévia: o contador público será ativado na publicação.';
    return;
  }
  async function updateCount() {
    try {
      const response = await fetch(endpoint, {headers: {Accept: 'application/vnd.github+json'}, signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw new Error('Contador indisponível');
      const release = await response.json();
      const asset = release.assets?.find(a => a.name === assetName && a.state === 'uploaded');
      if (!asset || !Number.isSafeInteger(asset.download_count) || asset.download_count < 0) throw new Error('Contagem inválida');
      counter.textContent = new Intl.NumberFormat('pt-BR').format(asset.download_count) + ' downloads · Total do GitHub, sujeito a atraso. Não representa leitores únicos.';
    } catch (_) {
      counter.textContent = 'Contador temporariamente indisponível. Você pode baixar normalmente.';
    }
  }
  updateCount();
  // A read-only request: opening/reloading this page never increments the count.
  setInterval(() => { if (!document.hidden) updateCount(); }, 120000);
})();
