import 'package:flutter/material.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';

/// Passive loader — shown while `app.dart` bootstraps auth state. Actual
/// routing happens in `LmsApp` once bootstrap completes.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _AnimatedLogo(),
            const SizedBox(height: AppSpacing.xl),
            Text(AppConstants.appName,
                style: AppTextStyles.display(context, color: AppColors.primary)),
            const SizedBox(height: AppSpacing.sm),
            Text(AppConstants.tagline, style: AppTextStyles.caption(context)),
          ],
        ),
      ),
    );
  }
}

class _AnimatedLogo extends StatefulWidget {
  const _AnimatedLogo();
  @override
  State<_AnimatedLogo> createState() => _AnimatedLogoState();
}

class _AnimatedLogoState extends State<_AnimatedLogo>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) {
        final t = _c.value;
        return Container(
          width: 96,
          height: 96,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                Color.lerp(AppColors.primary, AppColors.accent, t)!,
                AppColors.primaryDark,
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
            boxShadow: [
              BoxShadow(
                color: AppColors.primary.withValues(alpha: 0.35 + 0.15 * t),
                blurRadius: 30 + 20 * t,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: CustomPaint(
            painter: _LighthousePainter(pulse: t),
            size: const Size(96, 96),
          ),
        );
      },
    );
  }
}

/// Small stylized lighthouse mark. Drawn from primitives so no asset file
/// is needed — matches the "Manara" (منارة) name.
class _LighthousePainter extends CustomPainter {
  final double pulse; // 0..1 — lamp glow strength
  _LighthousePainter({required this.pulse});

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final cx = w / 2;
    final white = Paint()..color = Colors.white;

    // Base plinth.
    final base = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx - w * 0.28, h * 0.78, w * 0.56, h * 0.08),
      const Radius.circular(2),
    );
    canvas.drawRRect(base, white);

    // Tapered tower (two trapezoids stacked).
    final tower = Path()
      ..moveTo(cx - w * 0.22, h * 0.78)
      ..lineTo(cx - w * 0.14, h * 0.34)
      ..lineTo(cx + w * 0.14, h * 0.34)
      ..lineTo(cx + w * 0.22, h * 0.78)
      ..close();
    canvas.drawPath(tower, white);

    // Gallery walkway rim.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(cx - w * 0.18, h * 0.30, w * 0.36, h * 0.05),
        const Radius.circular(1.5),
      ),
      white,
    );

    // Lamp housing.
    final lampHousing = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx - w * 0.10, h * 0.18, w * 0.20, h * 0.13),
      const Radius.circular(3),
    );
    canvas.drawRRect(lampHousing, white);

    // Roof cone.
    final roof = Path()
      ..moveTo(cx - w * 0.14, h * 0.18)
      ..lineTo(cx, h * 0.06)
      ..lineTo(cx + w * 0.14, h * 0.18)
      ..close();
    canvas.drawPath(roof, white);

    // Lamp glow — pulsing dot at the light.
    final glow = Paint()
      ..color = Colors.white.withValues(alpha: 0.35 + 0.4 * pulse)
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, 4 + 4 * pulse);
    canvas.drawCircle(Offset(cx, h * 0.245), 4 + 3 * pulse, glow);
    canvas.drawCircle(Offset(cx, h * 0.245), 2.4, white);
  }

  @override
  bool shouldRepaint(covariant _LighthousePainter old) => old.pulse != pulse;
}
