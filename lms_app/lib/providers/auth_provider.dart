import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/user.dart';
import '../services/api_service.dart';
import '../services/push_service.dart';
import '../services/storage_service.dart';
import 'courses_provider.dart';
import 'enrollments_provider.dart';
import 'parent_provider.dart';

enum AuthStatus { unknown, unauthenticated, authenticated }

@immutable
class AuthState {
  final AuthStatus status;
  final AppUser? user;
  final String? error;

  const AuthState({required this.status, this.user, this.error});
  const AuthState.unknown() : this(status: AuthStatus.unknown);
  const AuthState.signedOut({String? error})
      : this(status: AuthStatus.unauthenticated, error: error);
  const AuthState.signedIn(AppUser user) : this(status: AuthStatus.authenticated, user: user);
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._ref) : super(const AuthState.unknown());

  final Ref _ref;
  final _api = ApiService.instance;
  final _storage = StorageService.instance;

  Future<void> bootstrap() async {
    final token = _storage.getSessionToken();
    if (token == null || token.isEmpty) {
      state = const AuthState.signedOut();
      return;
    }
    _api.setSessionToken(token);
    final cached = _storage.getUserJson();
    AppUser? cachedUser;
    if (cached != null) {
      try {
        cachedUser = AppUser.fromJson(cached);
        state = AuthState.signedIn(cachedUser);
      } catch (_) {}
    }
    try {
      final bundle = await _api.me();
      await _storage.setUserJson(bundle.user.toJson());
      state = AuthState.signedIn(bundle.user);
    } on SessionExpiredException {
      // Real 401 — token dead. Clear + sign out.
      await _storage.clearSession();
      _api.setSessionToken(null);
      state = const AuthState.signedOut();
    } on ApiException {
      // Phase 9 audit fix F11: transient network / CORS / DNS failure. Do
      // NOT drop the user to the login screen — keep them signed in on the
      // cached user. If the token is actually invalid, the next authed call
      // will surface SessionExpired and we'll bounce them cleanly.
      if (cachedUser != null) {
        state = AuthState.signedIn(cachedUser);
      } else {
        state = const AuthState.signedOut();
      }
    }
  }

  Future<void> login({required String email, required String password}) async {
    try {
      final bundle = await _api.login(email: email, password: password);
      await _storage.setSessionToken(bundle.sessionToken);
      await _storage.setUserJson(bundle.user.toJson());
      _api.setSessionToken(bundle.sessionToken);
      state = AuthState.signedIn(bundle.user);
      // Phase 28 — best-effort Web Push registration. Fires only on
      // web (native stubs no-op); a failed permission prompt or
      // missing service worker is swallowed inside the service.
      // ignore: unawaited_futures
      PushService.instance.registerIfSupported();
    } on ApiException catch (e) {
      state = AuthState.signedOut(error: e.message);
      rethrow;
    }
  }

  Future<void> register({
    required String name,
    required String email,
    required String password,
    required String role,
  }) async {
    try {
      final bundle = await _api.register(
        name: name,
        email: email,
        password: password,
        role: role,
      );
      await _storage.setSessionToken(bundle.sessionToken);
      await _storage.setUserJson(bundle.user.toJson());
      _api.setSessionToken(bundle.sessionToken);
      state = AuthState.signedIn(bundle.user);
    } on ApiException catch (e) {
      state = AuthState.signedOut(error: e.message);
      rethrow;
    }
  }

  Future<void> logout() async {
    try {
      await _api.logout();
    } catch (_) {}
    // Phase 28 — release the browser push subscription so the SW
    // isn't paged for a signed-out user. Silent on failure.
    try {
      await PushService.instance.unregister();
    } catch (_) {}
    // Phase 9 audit fix F10: invalidate every user-scoped provider BEFORE
    // clearing the session, so the next signed-in user never sees a flash
    // of the previous user's data on their home screen.
    _ref.invalidate(myCoursesProvider);
    _ref.invalidate(myEnrollmentsProvider);
    _ref.invalidate(catalogProvider);
    _ref.invalidate(linkedChildrenProvider);
    await _storage.clearSession();
    _api.setSessionToken(null);
    state = const AuthState.signedOut();
  }
}

final authProvider =
    StateNotifierProvider<AuthNotifier, AuthState>((ref) => AuthNotifier(ref));
