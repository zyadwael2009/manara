import 'package:flutter/foundation.dart';

/// App-wide constants — non-design values (design tokens live in core/theme).
class AppConstants {
  AppConstants._();

  static const String appName = 'Manara';
  static const String tagline = 'Light every step of learning.';

  /// Explicit override via `--dart-define=API_BASE_URL=...`. Empty when unset.
  static const String _apiBaseUrlOverride = String.fromEnvironment('API_BASE_URL');

  /// API base URL.
  ///
  /// Phase 11 audit fix L8: default picks the right localhost per platform.
  /// Previously hard-coded to `10.0.2.2` (Android emulator only) — iOS sim,
  /// desktop and web all failed with a generic "Cannot reach server."
  /// `--dart-define=API_BASE_URL=...` still overrides for cloud deploys.
  static String get apiBaseUrl {
    if (_apiBaseUrlOverride.isNotEmpty) return _apiBaseUrlOverride;
    if (kIsWeb) return 'http://localhost:5000/api';
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:5000/api';
    }
    // iOS simulator, macOS/Linux/Windows desktop.
    return 'http://localhost:5000/api';
  }

  /// The origin part of `apiBaseUrl` — used to resolve relative /media/ URLs
  /// returned from `POST /api/uploads`.
  static String get mediaOrigin {
    final u = Uri.parse(apiBaseUrl);
    return '${u.scheme}://${u.host}${u.hasPort ? ":${u.port}" : ""}';
  }

  /// Resolve a server-returned media URL. Server returns things like
  /// `/media/pdfs/<uuid>.pdf`; we prepend the API origin.
  static String resolveMediaUrl(String pathOrUrl) {
    if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
      return pathOrUrl;
    }
    if (pathOrUrl.startsWith('/')) return '$mediaOrigin$pathOrUrl';
    return '$mediaOrigin/$pathOrUrl';
  }

  // --- Storage keys ---
  static const String kSessionToken = 'session_token';
  static const String kSessionUserJson = 'session_user_json';

  // --- School subjects (matches backend `courses.category`) ---
  static const List<String> courseCategories = [
    'math',
    'science',
    'english',
    'social_studies',
    'languages',
    'arts',
    'pe',
    'computer_science',
    'general',
  ];

  static String prettyCategory(String c) {
    switch (c) {
      case 'math': return 'Math';
      case 'science': return 'Science';
      case 'english': return 'English';
      case 'social_studies': return 'Social Studies';
      case 'languages': return 'Languages';
      case 'arts': return 'Arts';
      case 'pe': return 'Physical Education';
      case 'computer_science': return 'Computer Science';
      case 'general': return 'General';
      default: return c;
    }
  }

  // --- Elective groups (matches backend `courses.elective_group`) ---
  static const List<String> electiveGroups = [
    'language',
    'science_track',
    'math_track',
    'humanities',
    'arts',
  ];

  static String prettyElectiveGroup(String g) {
    switch (g) {
      case 'language': return 'Language';
      case 'science_track': return 'Science Track';
      case 'math_track': return 'Math Track';
      case 'humanities': return 'Humanities';
      case 'arts': return 'Arts';
      default: return g;
    }
  }

  // --- Sections defaults (admin-configurable at runtime) ---
  static const List<String> defaultSections = ['Elementary', 'Middle', 'High'];
}
