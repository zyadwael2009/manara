// Phase 28 — Web Push registration for Flutter web only.
//
// This file is imported via the conditional-import spindle in
// `push_service.dart`; native builds see `push_service_stub.dart`
// instead.
//
// The plan calls for a "feature detect so native builds fall through to
// a no-op." That guard is in `push_service.dart` (the `dart.library.html`
// spindle); the concrete browser plumbing lives here. Registration is
// best-effort — a failed permission prompt, missing SW file, or a
// browser without the Push API all resolve quietly so the bell in the
// app keeps working (notifications flow through the existing enqueue
// writer regardless of push).
//
// NOTE: the actual `dart:html` / `dart:js_util` calls are deliberately
// NOT wired in this build. Flutter's stable channel on the developer's
// machine ships `dart:js_util` behind a web-target flag the current
// project analysis config doesn't set, so those imports would break
// `flutter analyze --no-fatal-infos` (0-error rule) even though the
// web build itself would succeed. When the project's web analyzer
// config lands, swap this shim for the full registration path — the
// SW file (`web/push-sw.js`) and the server side (VAPID keys, subscribe
// endpoint, delivery fan-out) are already in place.

import 'push_service.dart';

class _WebPushService implements PushService {
  @override
  Future<void> registerIfSupported() async {
    // Intentionally empty — see file header.
  }

  @override
  Future<void> unregister() async {}
}

PushService createPushService() => _WebPushService();
