import 'package:flutter/material.dart';

/// Spacing / radius tokens used across every screen.
///
/// Kept as plain `const double` fields so they can be used directly in any
/// `EdgeInsets.all(AppSpacing.md)` etc. call.
class AppSpacing {
  AppSpacing._();

  // Micro-spacing — under the 4-based scale, for hairline gaps
  // between glyph + label, pill inset, etc. Phase 26 · T1 added these
  // to keep the 3/4/5/6/10 magic-number sites token-driven.
  static const double hair = 2;
  static const double tiny = 4;
  static const double snug = 6;
  static const double cozy = 10;

  // 4-based scale.
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 48;

  // Radii.
  static const double radiusSm = 8;
  static const double radiusMd = 12;
  static const double radiusLg = 20;
  static const double radiusPill = 999;
}

/// Shadow presets. Cards use `soft`; the hero image on a course detail uses
/// `heroShadow`. Dark mode: keep shadows subtle — the borders on dark
/// surfaces do most of the elevation work.
class AppShadows {
  AppShadows._();

  static const List<BoxShadow> soft = [
    BoxShadow(
      color: Color(0x14000000), // 8% black
      blurRadius: 12,
      offset: Offset(0, 4),
    ),
  ];

  static const List<BoxShadow> hero = [
    BoxShadow(
      color: Color(0x1F000000), // ~12% black
      blurRadius: 24,
      offset: Offset(0, 10),
    ),
  ];
}
