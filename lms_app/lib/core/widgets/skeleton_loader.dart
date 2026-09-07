import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// Pulsing rounded rectangle used as a placeholder while data loads.
/// Preferred over a spinner for content areas (matches UI/UX standard #2).
class SkeletonBox extends StatefulWidget {
  final double? width;
  final double height;
  final double radius;
  const SkeletonBox({
    super.key,
    this.width,
    this.height = 16,
    this.radius = AppSpacing.radiusSm,
  });

  @override
  State<SkeletonBox> createState() => _SkeletonBoxState();
}

class _SkeletonBoxState extends State<SkeletonBox> with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final base = isDark ? AppColors.surfaceMutedDark : AppColors.surfaceMuted;
    final hi = isDark ? AppColors.borderDark : AppColors.border;
    return AnimatedBuilder(
      animation: _c,
      builder: (_, _) {
        final t = _c.value;
        return Container(
          width: widget.width,
          height: widget.height,
          decoration: BoxDecoration(
            color: Color.lerp(base, hi, t)!,
            borderRadius: BorderRadius.circular(widget.radius),
          ),
        );
      },
    );
  }
}

/// A single course-card-shaped skeleton, used to fill the catalog while
/// courses load.
class SkeletonCourseCard extends StatelessWidget {
  const SkeletonCourseCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            SkeletonBox(height: 140, radius: AppSpacing.radiusMd),
            SizedBox(height: AppSpacing.lg),
            SkeletonBox(height: 18, width: 220),
            SizedBox(height: AppSpacing.sm),
            SkeletonBox(height: 14, width: 160),
            SizedBox(height: AppSpacing.md),
            SkeletonBox(height: 12, width: 100),
          ],
        ),
      ),
    );
  }
}
