import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'app_colors.dart';

/// Type scale built on top of Google Fonts' Inter.
///
/// Every screen pulls styles from here rather than constructing `TextStyle`s
/// inline, so a future font swap (Cairo for Arabic bilingual, or a different
/// display face) is a one-line change.
class AppTextStyles {
  AppTextStyles._();

  static TextStyle _base({
    required double size,
    required FontWeight weight,
    Color? color,
    double? height,
    double? letterSpacing,
  }) {
    return GoogleFonts.inter(
      fontSize: size,
      fontWeight: weight,
      color: color,
      height: height,
      letterSpacing: letterSpacing,
    );
  }

  // Display / hero.
  static TextStyle display(BuildContext _, {Color? color}) => _base(
        size: 34,
        weight: FontWeight.w800,
        color: color ?? AppColors.textPrimary,
        height: 1.15,
        letterSpacing: -0.5,
      );

  // Headings.
  static TextStyle h1(BuildContext _, {Color? color}) => _base(
        size: 26,
        weight: FontWeight.w700,
        color: color ?? AppColors.textPrimary,
        height: 1.2,
        letterSpacing: -0.3,
      );
  static TextStyle h2(BuildContext _, {Color? color}) => _base(
        size: 20,
        weight: FontWeight.w700,
        color: color ?? AppColors.textPrimary,
        height: 1.25,
      );
  static TextStyle h3(BuildContext _, {Color? color}) => _base(
        size: 17,
        weight: FontWeight.w600,
        color: color ?? AppColors.textPrimary,
        height: 1.3,
      );

  // Body.
  static TextStyle body(BuildContext _, {Color? color}) => _base(
        size: 15,
        weight: FontWeight.w400,
        color: color ?? AppColors.textPrimary,
        height: 1.5,
      );
  static TextStyle bodyStrong(BuildContext _, {Color? color}) => _base(
        size: 15,
        weight: FontWeight.w600,
        color: color ?? AppColors.textPrimary,
        height: 1.5,
      );
  static TextStyle caption(BuildContext _, {Color? color}) => _base(
        size: 13,
        weight: FontWeight.w500,
        color: color ?? AppColors.textSecondary,
        height: 1.4,
      );
  static TextStyle micro(BuildContext _, {Color? color}) => _base(
        size: 11,
        weight: FontWeight.w600,
        color: color ?? AppColors.textMuted,
        height: 1.3,
        letterSpacing: 0.4,
      );

  // Button label.
  static TextStyle button({Color? color}) => _base(
        size: 15,
        weight: FontWeight.w600,
        color: color,
        letterSpacing: 0.2,
      );
}
