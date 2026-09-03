import 'package:flutter/material.dart';

/// Phase 26 · T1 — single source of truth for per-category color/icon.
///
/// Previously the same 9-entry map lived inline in
/// `screens/student/my_classes_screen.dart::_CategoryGlyph` and (with
/// different keys) in `screens/shared/weekly_timetable_grid.dart::_PeriodCell`.
/// A rebrand touched both files; dark mode was ad-hoc.
///
/// Everything that renders a category swatch imports this now.
class CategoryPalette {
  final Color gradientTop;
  final Color gradientBottom;
  final Color softBg;
  final Color textOnSoft;
  final IconData icon;

  const CategoryPalette({
    required this.gradientTop,
    required this.gradientBottom,
    required this.softBg,
    required this.textOnSoft,
    required this.icon,
  });

  static const _general = CategoryPalette(
    gradientTop: Color(0xFF4F46E5),
    gradientBottom: Color(0xFF3730A3),
    softBg: Color(0xFFEEF2FF),
    textOnSoft: Color(0xFF3730A3),
    icon: Icons.school_outlined,
  );

  static const Map<String, CategoryPalette> _map = {
    'math': CategoryPalette(
      gradientTop: Color(0xFF4F46E5),
      gradientBottom: Color(0xFF3730A3),
      softBg: Color(0xFFEEF2FF),
      textOnSoft: Color(0xFF3730A3),
      icon: Icons.calculate_outlined,
    ),
    'science': CategoryPalette(
      gradientTop: Color(0xFF06B6D4),
      gradientBottom: Color(0xFF0E7490),
      softBg: Color(0xFFCFFAFE),
      textOnSoft: Color(0xFF155E75),
      icon: Icons.science_outlined,
    ),
    'english': CategoryPalette(
      gradientTop: Color(0xFF10B981),
      gradientBottom: Color(0xFF047857),
      softBg: Color(0xFFD1FAE5),
      textOnSoft: Color(0xFF065F46),
      icon: Icons.menu_book_outlined,
    ),
    'social_studies': CategoryPalette(
      gradientTop: Color(0xFFF59E0B),
      gradientBottom: Color(0xFFB45309),
      softBg: Color(0xFFFEF3C7),
      textOnSoft: Color(0xFF92400E),
      icon: Icons.public_outlined,
    ),
    'languages': CategoryPalette(
      gradientTop: Color(0xFFEC4899),
      gradientBottom: Color(0xFFBE185D),
      softBg: Color(0xFFFCE7F3),
      textOnSoft: Color(0xFF9D174D),
      icon: Icons.translate_outlined,
    ),
    'arts': CategoryPalette(
      gradientTop: Color(0xFF8B5CF6),
      gradientBottom: Color(0xFF6D28D9),
      softBg: Color(0xFFEDE9FE),
      textOnSoft: Color(0xFF5B21B6),
      icon: Icons.palette_outlined,
    ),
    'pe': CategoryPalette(
      gradientTop: Color(0xFFEF4444),
      gradientBottom: Color(0xFFB91C1C),
      softBg: Color(0xFFFEE2E2),
      textOnSoft: Color(0xFF991B1B),
      icon: Icons.sports_soccer_outlined,
    ),
    'computer_science': CategoryPalette(
      gradientTop: Color(0xFF64748B),
      gradientBottom: Color(0xFF334155),
      softBg: Color(0xFFF1F5F9),
      textOnSoft: Color(0xFF334155),
      icon: Icons.terminal_outlined,
    ),
    'general': _general,
  };

  static CategoryPalette forCategory(String? category) =>
      _map[category ?? 'general'] ?? _general;
}
