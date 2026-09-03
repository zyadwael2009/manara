# Push notifications — setup notes

The backend ships two push transports side-by-side:

| Transport | Status                            | Platforms          |
|-----------|-----------------------------------|--------------------|
| Web Push  | **Wired** (Phase 28)              | Chrome/Edge/Firefox |
| FCM/APNs  | **Ready-to-activate** (Phase 30)  | Android/iOS  |

## Web Push (works today)

Nothing to configure. On first request to `GET /api/push/public-key`,
the server generates an ECDSA P-256 keypair into
`instance/vapid.json` and returns the public half. The browser passes
the public key to `PushManager.subscribe`, the browser hits
`POST /api/push/subscribe`, and every subsequent call to
`utils.notifications.enqueue` fans out via `pywebpush`.

## FCM / APNs (mobile) — 4-step activation

Both the sender in `utils/push.py::send_mobile_push` and the Flutter
side in `push_service_native_fcm.dart.template` are ready. Neither
runs today because the Firebase project doesn't exist yet — both are
feature-gated to no-op silently until you flip four switches:

1. **Create a Firebase project** (or reuse an existing one). Enable
   Cloud Messaging. Register the Manara Android + iOS bundles under
   that project.
2. **Drop the service-account JSON** at
   `backend/instance/firebase.json`. The path is what
   `utils/push.py::send_mobile_push` reads.
3. **Uncomment the deps**:
   - `backend/requirements.txt`: uncomment `pyfcm>=2.0.0`, then
     `pip install -r requirements.txt`.
   - `lms_app/pubspec.yaml`: uncomment the two `firebase_*` lines,
     then `flutter pub get`.
4. **Activate the Flutter native path**:
   - Drop `google-services.json` under `android/app/`.
   - Drop `GoogleService-Info.plist` under `ios/Runner/`.
   - Rename `lib/services/push_service_native_fcm.dart.template` to
     `.dart` (drop the `.template` suffix).
   - In `lib/services/push_service.dart`, swap the conditional-import
     spindle to:

     ```dart
     import 'push_service_stub.dart'
         if (dart.library.html) 'push_service_web.dart'
         if (dart.library.io) 'push_service_native_fcm.dart';
     ```

That's it. Login → `PushService.instance.registerIfSupported()` pulls
the FCM token and POSTs it with `platform: "fcm"` (`"apns"` on iOS).
The backend receives it, `fan_out_to_user` routes it to
`send_mobile_push`, and the app gets push notifications on the same
enqueue-writer path the browser already uses.

### Safety net

If any of the four steps is skipped, the affected side no-ops with a
log entry — nothing crashes:

- Missing `firebase.json` → `send_mobile_push` logs once and returns
  `(False, None)`.
- Missing `pyfcm` import → same shape (`_pyfcm is None` branch).
- Missing `firebase_messaging` in pubspec → `push_service_native_fcm`
  never compiles because it's still `.template`; the stub takes over.
