// Phase 28 — browser Web Push registration.
//
// Public facade. The concrete impl lives in `push_service_web.dart`
// on Flutter web (via the conditional-import spindle below) and in
// `push_service_stub.dart` on native — the plan's "feature detect so
// mobile builds fall through to a no-op" contract.
//
// Public API:
//   * `PushService.instance.registerIfSupported()`
//   * `PushService.instance.unregister()`
//
// Both are best-effort. A failed permission prompt, missing SW file, or
// browser without the Push API all resolve quietly — the bell in the
// app still works because notifications flow through the existing
// `enqueue` writer.

import 'push_service_stub.dart'
    if (dart.library.html) 'push_service_web.dart';

abstract class PushService {
  static final PushService instance = createPushService();

  /// Ask the browser for permission (if not already granted), register
  /// the service worker, subscribe with the server's public key, and
  /// POST the subscription up.
  Future<void> registerIfSupported();

  /// Look up the browser's current subscription and unsubscribe both
  /// locally + on the server. Safe to call on sign-out even when never
  /// registered.
  Future<void> unregister();
}
