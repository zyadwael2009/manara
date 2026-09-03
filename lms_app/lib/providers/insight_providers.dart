import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/insight.dart';
import '../services/api_service.dart';

/// Phase 22 — at-risk roster for a class (family key = class id).
final classAtRiskProvider =
    FutureProvider.autoDispose.family<List<AtRiskRow>, String>((ref, classId) async {
  return ApiService.instance.classAtRisk(classId);
});

/// Student's own grade history — one time-series per active/completed
/// enrollment.
final myGradeHistoryProvider =
    FutureProvider.autoDispose<GradeHistory>((ref) async {
  return ApiService.instance.myGradeHistory();
});

/// Admin attendance-patterns block.
final attendancePatternsProvider =
    FutureProvider.autoDispose<AttendancePatterns>((ref) async {
  return ApiService.instance.attendancePatterns();
});
