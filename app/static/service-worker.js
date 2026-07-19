const VERSION = 'agenda1-online-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();

    await Promise.all(
      cacheNames
        .filter((cacheName) => cacheName.startsWith('agenda1-'))
        .map((cacheName) => caches.delete(cacheName))
    );

    await self.clients.claim();
  })());
});

// Não existe listener de "fetch" nesta versão. Agenda, clientes, financeiro,
// estoque e demais dados continuam sendo obtidos diretamente do Flask.
