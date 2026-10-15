// Éden: avisos de lembrete (Web Push). Este arquivo é importado pelo service
// worker do app (vite.config.ts → workbox.importScripts). O conteúdo do aviso
// chega cifrado do servidor do Éden; só este aparelho consegue ler.
/* eslint-disable no-restricted-globals */
self.addEventListener('push', (event) => {
  let dados = {};
  try {
    dados = event.data ? event.data.json() : {};
  } catch (e) {
    dados = { corpo: event.data ? event.data.text() : '' };
  }
  const titulo = typeof dados.titulo === 'string' && dados.titulo ? dados.titulo : 'Éden';
  // Só endereços do próprio Éden ("/tarefas"), nunca outro site.
  let url = '/';
  try {
    if (typeof dados.url === 'string') {
      const destino = new URL(dados.url, self.location.origin);
      if (destino.origin === self.location.origin) {
        url = destino.pathname + destino.search + destino.hash;
      }
    }
  } catch (e) {
    url = '/';
  }
  event.waitUntil(
    self.registration.showNotification(titulo, {
      body: typeof dados.corpo === 'string' ? dados.corpo : '',
      tag: typeof dados.tag === 'string' ? dados.tag : undefined,
      icon: '/pwa-192x192.png',
      badge: '/pwa-192x192.png',
      data: { url },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    (async () => {
      const janelas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const janela of janelas) {
        if ('focus' in janela) {
          await janela.focus();
          if ('navigate' in janela) {
            try {
              await janela.navigate(url);
            } catch (e) {
              // Sem problema: a janela já está aberta.
            }
          }
          return;
        }
      }
      if (self.clients.openWindow) await self.clients.openWindow(url);
    })(),
  );
});
