(() => {
  'use strict';

  if (!('serviceWorker' in navigator)) {
    return;
  }

  window.addEventListener('load', async () => {
    try {
      await navigator.serviceWorker.register('/service-worker.js', {
        scope: '/',
        updateViaCache: 'none'
      });
    } catch (error) {
      console.error('Não foi possível registrar a PWA do Agenda1.', error);
    }
  });
})();
