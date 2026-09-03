// Phase 28 — Web Push service worker.
//
// Registered from lib/services/push_service.dart on Flutter web
// initialization. Handles two events:
//   * `push`             — server-signed VAPID payload arrives; render
//                          a native browser notification.
//   * `notificationclick` — focus (or open) the app tab and pass the
//                          notification's ref back for deep-linking.
//
// Deliberately independent of the Flutter engine: the SW keeps running
// even when the app tab is closed, which is the entire point of Web
// Push in the first place.

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  if (!event.data) return;
  let payload = {};
  try {
    payload = event.data.json();
  } catch (_) {
    payload = { title: 'Manara', body: event.data.text() };
  }
  const title = payload.title || 'Manara';
  const options = {
    body: payload.body || '',
    icon: '/icons/Icon-192.png',
    badge: '/favicon.png',
    tag: (payload.refType && payload.refId)
      ? `${payload.refType}:${payload.refId}`
      : payload.kind || 'manara',
    // Store ref data for the click handler.
    data: {
      refType: payload.refType || null,
      refId: payload.refId || null,
      kind: payload.kind || null,
    },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const clientsList = await self.clients.matchAll({
      type: 'window', includeUncontrolled: true,
    });
    // Reuse an existing tab if the app is already open.
    for (const c of clientsList) {
      if ('focus' in c) {
        c.postMessage({
          type: 'push-click',
          data: event.notification.data || {},
        });
        return c.focus();
      }
    }
    // Otherwise open a new tab at the app root.
    if (self.clients.openWindow) {
      return self.clients.openWindow('/');
    }
  })());
});
