import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Circular progress ring with animated fill on first paint.
class ProgressRing extends StatefulWidget {
  final double percent; // 0-100
  final double size;
  final String? label;
  final Color? color;

  const ProgressRing({
    super.key,
    required this.percent,
    this.size = 42,
    this.label,
    this.color,
  });

  @override
  State<ProgressRing> createState() => _ProgressRingState();
}

class _ProgressRingState extends State<ProgressRing>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;
  late Animation<double> _fill;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _fill = Tween<double>(begin: 0.0, end: widget.percent.clamp(0.0, 100.0) / 100.0)
        .animate(CurvedAnimation(parent: _c, curve: Curves.easeOutCubic));
    _c.forward();
  }

  @override
  void didUpdateWidget(covariant ProgressRing old) {
    super.didUpdateWidget(old);
    if (old.percent != widget.percent) {
      _fill = Tween<double>(
        begin: _fill.value,
        end: widget.percent.clamp(0.0, 100.0) / 100.0,
      ).animate(CurvedAnimation(parent: _c, curve: Curves.easeOutCubic));
      _c
        ..reset()
        ..forward();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? AppColors.primary;
    final done = widget.percent >= 100;
    return AnimatedBuilder(
      animation: _fill,
      builder: (_, _) => CustomPaint(
        size: Size.square(widget.size),
        painter: _RingPainter(
          progress: _fill.value,
          color: done ? AppColors.success : color,
          strokeWidth: 4,
          trackColor: AppColors.surfaceMuted,
        ),
        child: SizedBox.square(
          dimension: widget.size,
          child: Center(
            child: Text(
              widget.label ?? (done ? '✓' : '${widget.percent.round()}%'),
              style: TextStyle(
                fontSize: widget.size * 0.28,
                fontWeight: FontWeight.w700,
                color: done ? AppColors.success : color,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  final double progress;
  final Color color;
  final Color trackColor;
  final double strokeWidth;

  _RingPainter({
    required this.progress,
    required this.color,
    required this.trackColor,
    required this.strokeWidth,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final center = rect.center;
    final radius = math.min(size.width, size.height) / 2 - strokeWidth / 2;
    final trackPaint = Paint()
      ..color = trackColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    canvas.drawCircle(center, radius, trackPaint);

    if (progress <= 0) return;
    final progPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      progress * 2 * math.pi,
      false,
      progPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _RingPainter old) =>
      old.progress != progress || old.color != color;
}
