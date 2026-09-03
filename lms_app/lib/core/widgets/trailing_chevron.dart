import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Phase 25 hard-audit fix D-9 — shared trailing-chevron widget.
///
/// The Material `Icons.chevron_right_rounded` icon does NOT auto-mirror
/// under RTL directionality — every ListTile using it as `trailing:`
/// would keep pointing right in Arabic, away from the item's target.
///
/// This helper swaps to a directional icon based on
/// `Directionality.of(context)`, so a single import + widget replacement
/// gets every affordance ready for the future Arabic locale swap.
///
/// Usage:
///   trailing: const TrailingChevron(),
class TrailingChevron extends StatelessWidget {
  final Color? color;
  final double size;
  const TrailingChevron({super.key, this.color, this.size = 24});

  @override
  Widget build(BuildContext context) {
    final dir = Directionality.of(context);
    return Icon(
      dir == TextDirection.rtl
          ? Icons.chevron_left_rounded
          : Icons.chevron_right_rounded,
      size: size,
      color: color ?? AppColors.textMuted,
    );
  }
}
