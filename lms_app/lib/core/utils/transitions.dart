import 'package:animations/animations.dart';
import 'package:flutter/material.dart';

/// Wraps a destination widget in a shared-axis fade+slide transition.
///
/// Used with `Navigator.of(context).push(fadeThroughRoute(NextScreen()))`
/// so every screen change looks intentional instead of the default MaterialPageRoute
/// slide-from-right.
PageRouteBuilder<T> fadeThroughRoute<T>(Widget page, {Duration duration = const Duration(milliseconds: 350)}) {
  return PageRouteBuilder<T>(
    transitionDuration: duration,
    reverseTransitionDuration: duration,
    pageBuilder: (context, animation, secondaryAnimation) => page,
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      return FadeThroughTransition(
        animation: animation,
        secondaryAnimation: secondaryAnimation,
        child: child,
      );
    },
  );
}

/// Slower, more deliberate hero flight than Flutter's default 300ms —
/// makes the course-card → detail-header transition feel smoother.
PageRouteBuilder<T> heroRoute<T>(Widget page) {
  return PageRouteBuilder<T>(
    transitionDuration: const Duration(milliseconds: 450),
    reverseTransitionDuration: const Duration(milliseconds: 350),
    pageBuilder: (context, animation, secondaryAnimation) => page,
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      return FadeTransition(
        opacity: CurvedAnimation(parent: animation, curve: Curves.easeOutCubic),
        child: child,
      );
    },
  );
}
