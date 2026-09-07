part of 'api_service.dart';

/// Sign-in, sign-out, and password management.

extension ApiServiceAuth on ApiService {
  // ==========================================================================
  // Auth
  // ==========================================================================
  Future<AuthBundle> register({
    required String name,
    required String email,
    required String password,
    required String role,
  }) async {
    final data = await _send('POST', '/auth/register', body: {
      'name': name,
      'email': email,
      'password': password,
      'role': role,
    }) as Map<String, dynamic>;
    return AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
  }

  Future<AuthBundle> login({required String email, required String password}) async {
    final data = await _send('POST', '/auth/login', body: {
      'email': email,
      'password': password,
    }) as Map<String, dynamic>;
    return AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
  }

  Future<AuthBundle> me() async {
    final data = await _send('GET', '/auth/me') as Map<String, dynamic>;
    return AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
  }

  /// Change your own password.
  ///
  /// The backend bumps `token_version`, which revokes every outstanding
  /// session for this user, then issues a fresh token for the caller — so the
  /// device making the change stays signed in and all others are signed out.
  /// That fresh token has to replace the stored one or the very next request
  /// from this device 401s.
  Future<AuthBundle> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final data = await _send('POST', '/auth/password', body: {
      'currentPassword': currentPassword,
      'newPassword': newPassword,
    }) as Map<String, dynamic>;
    final bundle = AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
    setSessionToken(bundle.sessionToken);
    await StorageService.instance.setSessionToken(bundle.sessionToken);
    return bundle;
  }

  /// Admin resets another account's password.
  ///
  /// Returns the generated temporary password when the caller did not supply
  /// one. It is stored only as a hash, so this response is the single chance
  /// to read it — show it to the admin, don't swallow it.
  Future<String?> adminResetPassword({
    required String userId,
    String? newPassword,
  }) async {
    final data = await _send(
      'POST',
      '/users/$userId/password',
      body: newPassword == null ? <String, dynamic>{} : {'newPassword': newPassword},
    ) as Map<String, dynamic>;
    return data['temporaryPassword'] as String?;
  }

  Future<void> logout() async {
    try {
      await _send('POST', '/auth/logout');
    } finally {
      _sessionToken = null;
      await StorageService.instance.clearSession();
    }
  }
}
