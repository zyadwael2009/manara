import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../core/constants/app_constants.dart';

/// Thin wrapper around SharedPreferences for the auth session bits.
///
/// Kept as a singleton so any layer (API service, providers) can read/write
/// without threading a prefs instance through every constructor. Init once
/// from `main.dart`.
class StorageService {
  StorageService._();
  static final StorageService instance = StorageService._();

  SharedPreferences? _prefs;

  Future<void> init() async {
    _prefs ??= await SharedPreferences.getInstance();
  }

  SharedPreferences get _p {
    final p = _prefs;
    if (p == null) {
      throw StateError('StorageService.init() must be awaited before use.');
    }
    return p;
  }

  // --- Session token ---
  String? getSessionToken() => _p.getString(AppConstants.kSessionToken);
  Future<void> setSessionToken(String? token) async {
    if (token == null || token.isEmpty) {
      await _p.remove(AppConstants.kSessionToken);
    } else {
      await _p.setString(AppConstants.kSessionToken, token);
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
    await _p.remove(AppConstants.kSessionToken);
    await _p.remove(AppConstants.kSessionUserJson);
  }
}
