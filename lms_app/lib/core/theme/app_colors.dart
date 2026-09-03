import 'package:flutter/material.dart';

/// Hard-coded brand + status palette.
///
/// The primary is a deep indigo → violet, warm accent for CTAs. Chosen to
/// read as "premium learning product" without leaning on default Material
/// grey. Everything else in the app sources its colors from this file.
class AppColors {
  AppColors._();

  // --- Brand ---
  static const Color primary = Color(0xFF4F46E5);       // indigo-600
  static const Color primaryDark = Color(0xFF3730A3);   // indigo-800
  static const Color primarySoft = Color(0xFFEEF2FF);   // indigo-50

  static const Color accent = Color(0xFFF59E0B);        // amber-500
  static const Color accentSoft = Color(0xFFFEF3C7);    // amber-100
  // Phase 25 hard-audit fix D-2: the "text-on-amber-soft" color
  // (amber-900) was hardcoded as Color(0xFF92400E) in ~8 places
  // (homework strip, my_calendar day-selected, course_detail pill,
  // login secondary, weekly_timetable_grid english cell, admin
  // grade curriculum, student_detail warn tile, my_classes badge).
  // One token means one rebrand.
  static const Color accentText = Color(0xFF92400E);    // amber-900

  // --- Light surface ---
  static const Color background = Color(0xFFFAFAFB);
  static const Color surface = Colors.white;
  static const Color surfaceMuted = Color(0xFFF3F4F6);
  static const Color border = Color(0xFFE5E7EB);
  static const Color divider = Color(0xFFEEF0F3);

  static const Color textPrimary = Color(0xFF0F172A);   // slate-900
  static const Color textSecondary = Color(0xFF475569); // slate-600
  static const Color textMuted = Color(0xFF94A3B8);     // slate-400

  // --- Dark surface ---
  static const Color backgroundDark = Color(0xFF0B0D12);
  static const Color surfaceDark = Color(0xFF14171F);
  static const Color surfaceMutedDark = Color(0xFF1B1F28);
  static const Color borderDark = Color(0xFF2A2F3A);

  static const Color textPrimaryDark = Color(0xFFF8FAFC);
  static const Color textSecondaryDark = Color(0xFFCBD5E1);
  static const Color textMutedDark = Color(0xFF64748B);

  // --- Status ---
  static const Color success = Color(0xFF10B981);
  static const Color successSoft = Color(0xFFD1FAE5);
  static const Color warning = Color(0xFFF59E0B);
  static const Color warningSoft = Color(0xFFFEF3C7);
  // Phase 33 fix #21 — deep-amber (amber-600) for gradient partners
  // that were bare `Color(0xFF…)` literals in screens. Kept next to
  // `warning` so the palette pairs are visible in one place.
  static const Color warningDeep = Color(0xFFD97706);
  static const Color danger = Color(0xFFEF4444);
  static const Color dangerSoft = Color(0xFFFEE2E2);
  static const Color info = Color(0xFF3B82F6);
  static const Color infoSoft = Color(0xFFDBEAFE);
}
