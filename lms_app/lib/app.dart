import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/constants/app_constants.dart';
import 'core/theme/app_theme.dart';
import 'providers/auth_provider.dart';
import 'screens/admin/admin_home_screen.dart';
import 'screens/auth/login_screen.dart' show LoginScreen, DemoCredentials;
import 'services/api_service.dart';
import 'screens/instructor/teacher_home_screen.dart';
import 'screens/parent/parent_home_screen.dart';
import 'screens/splash/splash_screen.dart';
import 'screens/student/my_classes_screen.dart';

/// Root of the app. Watches auth state to swap the home surface — one place
/// that always reflects the current role, so login/logout doesn't need to
/// juggle Navigator stack tricks.
class LmsApp extends ConsumerStatefulWidget {
  const LmsApp({super.key});

  @override
  ConsumerState<LmsApp> createState() => _LmsAppState();
}

class _LmsAppState extends ConsumerState<LmsApp> {
  bool _bootstrapped = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await ref.read(authProvider.notifier).bootstrap();
      if (mounted) setState(() => _bootstrapped = true);
      // Phase 8: honor ?demo=parent|student|teacher|admin from the URL
      // (web only). Lets the README link straight into a role.
      await _maybeAutoDemoLogin();
    });
  }

  Future<void> _maybeAutoDemoLogin() async {
    final auth = ref.read(authProvider);
    if (auth.user != null) return; // already signed in
    final params = Uri.base.queryParameters;
    final role = params['demo'];
    final creds = role == null ? null : DemoCredentials.byRole[role];
    if (creds == null) return;
    try {
      await ref.read(authProvider.notifier).login(
            email: creds.email,
            password: creds.password,
          );
    } on ApiException {
      // Silent — user will see the normal login screen.
    }
  }

  Widget _homeForAuth(AuthState auth) {
    if (!_bootstrapped || auth.status == AuthStatus.unknown) {
      return const SplashScreen();
    }
    if (auth.status == AuthStatus.unauthenticated || auth.user == null) {
      return const LoginScreen();
    }
    final u = auth.user!;
    if (u.isAdmin) return const AdminHomeScreen();
    if (u.isInstructor) return const TeacherHomeScreen();
    if (u.isParent) return const ParentHomeScreen();
    return const MyClassesScreen();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    return MaterialApp(
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      // Locked to light-mode to match the mockups. If you want dark later,
      // swap this back to ThemeMode.system (AppTheme.dark is still built).
      theme: AppTheme.light(),
      darkTheme: AppTheme.light(),
      themeMode: ThemeMode.light,
      home: _homeForAuth(auth),
    );
  }
}
