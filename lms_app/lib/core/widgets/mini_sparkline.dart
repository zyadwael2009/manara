import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Phase 18 — a tiny sparkline for tucking into report-card rows and
/// similar tight spots. Values are 0..1 (fractions).
///
/// Renders a soft area under a line with an emphasized endpoint dot.
/// Silent on empty / single-point input (nothing to plot).
///
/// Deliberately no dependency on any charting library.
class MiniSparkline extends StatelessWidget {
  final List<double> values;
  final Color? color;
  final double width;
  final double height;
  final bool showEndpointDot;

  const MiniSparkline({
    super.key,
    required this.values,
    this.color,
    this.width = 96,
    this.height = 28,
    this.showEndpointDot = true,
  });

  @override
  Widget build(BuildContext context) {
    if (values.length < 2) return SizedBox(width: width, height: height);
    return SizedBox(
      width: width,
      height: height,
      child: CustomPaint(
        painter: _SparklinePainter(
          values: values,
          lineColor: color ?? AppColors.primary,
          showEndpointDot: showEndpointDot,
        ),
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<double> values;
  final Color lineColor;
  final bool showEndpointDot;

  _SparklinePainter({
    required this.values,
    required this.lineColor,
    required this.showEndpointDot,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final n = values.length;
    // Clamp to 0..1 for safety; padding of 3px so the endpoint dot fits.
    final pad = 3.0;
    final drawW = w - pad * 2;
    final drawH = h - pad * 2;

    Offset p(int i) {
      final v = values[i].clamp(0.0, 1.0);
      final x = pad + (i / (n - 1)) * drawW;
      final y = pad + (1.0 - v) * drawH;
      return Offset(x, y);
    }

    // Area fill.
    final fillPath = Path()..moveTo(p(0).dx, h - pad);
    for (int i = 0; i < n; i++) {
      fillPath.lineTo(p(i).dx, p(i).dy);
    }
    fillPath.lineTo(p(n - 1).dx, h - pad);
    fillPath.close();
    final fill = Paint()..color = lineColor.withValues(alpha: 0.14);
    canvas.drawPath(fillPath, fill);

    // Line.
    final linePath = Path()..moveTo(p(0).dx, p(0).dy);
    for (int i = 1; i < n; i++) {
      linePath.lineTo(p(i).dx, p(i).dy);
    }
    final line = Paint()
      ..color = lineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(linePath, line);

    // Endpoint dot.
    if (showEndpointDot) {
      final end = p(n - 1);
      canvas.drawCircle(
          end, 3, Paint()..color = lineColor);
      canvas.drawCircle(end, 1.6, Paint()..color = Colors.white);
    }
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter old) =>
      old.values != values ||
      old.lineColor != lineColor ||
      old.showEndpointDot != showEndpointDot;
}
