import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/dashboard.dart';
import '../services/api_service.dart';

/// Instructor / admin dashboard payloads. Pull-based — refresh on pull-down
/// or on screen re-open. No polling.
final instructorDashboardProvider =
    FutureProvider.autoDispose<InstructorDashboard>((ref) async {
  return ApiService.instance.getInstructorDashboard();
});

final instructorCourseDrilldownProvider =
    FutureProvider.autoDispose.family<CourseDrilldown, String>((ref, courseId) async {
  return ApiService.instance.getInstructorCourseDrilldown(courseId);
});

final adminDashboardProvider =
    FutureProvider.autoDispose<AdminDashboard>((ref) async {
  return ApiService.instance.getAdminDashboard();
});
