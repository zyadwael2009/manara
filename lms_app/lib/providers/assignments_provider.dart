import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/assignment.dart';
import '../services/api_service.dart';

final courseAssignmentsProvider =
    FutureProvider.autoDispose.family<List<Assignment>, String>((ref, courseId) async {
  return ApiService.instance.listCourseAssignments(courseId);
});

final assignmentDetailProvider =
    FutureProvider.autoDispose.family<Assignment, String>((ref, assignmentId) async {
  return ApiService.instance.getAssignment(assignmentId);
});

final assignmentSubmissionsProvider =
    FutureProvider.autoDispose.family<List<AssignmentSubmission>, String>(
        (ref, assignmentId) async {
  return ApiService.instance.listAssignmentSubmissions(assignmentId);
});
