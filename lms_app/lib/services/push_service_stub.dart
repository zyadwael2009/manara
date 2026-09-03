// Phase 28 — non-web stub for `PushService`.
//
// Native builds (iOS/Android/desktop) don't have the browser Push API.
// This stub is chosen via the conditional-import spindle in
// `push_service.dart`; its methods resolve immediately with no work.
// The mobile FCM/APNs implementation lands in a later phase.

import 'push_service.dart';

class _StubPushService implements PushService {
  @override
  Future<void> registerIfSupported() async {}
  @override
  Future<void> unregister() async {}
}

PushService createPushService() => _StubPushService();
