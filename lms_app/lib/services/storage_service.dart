import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/constants/app_constants.dart';

/// Storage for the auth session.
///
/// Two backing stores, split by sensitivity:
///
///   * **The session token** goes to `flutter_secure_storage` — the Android
///     Keystore, the iOS Keychain, or WebCrypto-wrapped storage on web. It is
///     a bearer credential valid for 90 days: anything holding it *is* the
///     user. It previously sat in `SharedPreferences`, which is a
///     world-readable XML file on a rooted Android device and plain
///     `localStorage` on web.
///   * **The cached user snapshot** stays in `SharedPreferences`. It is a
///     name, an email and a role — the same data the API hands back on the
///     next request — and it only exists so the splash screen can render
///     something before `/auth/me` returns.
///
/// Secure storage is async-only, but `getSessionToken()` is called
/// synchronously from the API service on every single request. So the token
/// is read once during `init()` (which `main.dart` already awaits) and cached
/// in memory; writes go to both the cache and the secure store.
class StorageService {
  StorageService._();
  static final StorageService instance = StorageService._();

  // v10 encrypts with its own ciphers by default; the old
  // `encryptedSharedPreferences` flag is deprecated and ignored.
  static const _secure = FlutterSecureStorage();

  SharedPreferences? _prefs;
  String? _cachedToken;

  Future<void> init() async {
    _prefs ??= await SharedPreferences.getInstance();
    _cachedToken = await _readTokenWithMigration();
  }

  SharedPreferences get _p {
    final p = _prefs;
    if (p == null) {
      throw StateError('StorageService.init() must be awaited before use.');
    }
    return p;
  }

  /// Read the token from secure storage, lifting across any token left in
  /// `SharedPreferences` by a build that predates this change — otherwise
  /// upgrading the app would silently sign everybody out.
  Future<String?> _readTokenWithMigration() async {
    String? token;
    try {
      token = await _secure.read(key: AppConstants.kSessionToken);
    } catch (_) {
      // A corrupt keystore entry (happens after some Android restores)
      // should mean "signed out", not "app won't start".
      token = null;
    }
    if (token != null && token.isNotEmpty) {
      // Clear any stale plaintext copy left behind by an older build.
      await _p.remove(AppConstants.kSessionToken);
      return token;
    }

    final legacy = _p.getString(AppConstants.kSessionToken);
    if (legacy == null || legacy.isEmpty) return null;
    try {
      await _secure.write(key: AppConstants.kSessionToken, value: legacy);
      await _p.remove(AppConstants.kSessionToken);
    } catch (_) {
      // Keep the legacy value working rather than logging the user out.
      return legacy;
    }
    return legacy;
  }

  // --- Session token ---
  String? getSessionToken() => _cachedToken;

  Future<void> setSessionToken(String? token) async {
    if (token == null || token.isEmpty) {
      _cachedToken = null;
      try {
        await _secure.delete(key: AppConstants.kSessionToken);
      } catch (_) {}
      await _p.remove(AppConstants.kSessionToken);
      return;
    }
    _cachedToken = token;
    try {
      await _secure.write(key: AppConstants.kSessionToken, value: token);
    } catch (_) {
      // Secure storage unavailable (an old device, a locked keystore). The
      // in-memory cache still carries the session for this run rather than
      // dropping the user back to the login screen mid-task.
    }
  }

  // --- Cached user snapshot (so splash can render offline) ---
  Map<String, dynamic>? getUserJson() {
    final raw = _p.getString(AppConstants.kSessionUserJson);
    if (raw == null || raw.isEmpty) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<void> setUserJson(Map<String, dynamic>? user) async {
    if (user == null) {
      await _p.remove(AppConstants.kSessionUserJson);
    } else {
      await _p.setString(AppConstants.kSessionUserJson, jsonEncode(user));
    }
  }

  Future<void> clearSession() async {
    await setSessionToken(null);
    await _p.remove(AppConstants.kSessionUserJson);
  }
}
