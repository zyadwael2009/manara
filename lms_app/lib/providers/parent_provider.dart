import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/certificate.dart';
import '../models/parent_link.dart';
import '../models/quiz.dart';
import '../services/api_service.dart';

/// Phase 6 — parent-portal providers. Autodispose so refetching on
/// child-tab reopen is free of stale caches.
final linkedChildrenProvider =
    FutureProvider.autoDispose<List<LinkedChild>>((ref) async {
  return ApiService.instance.listMyChildren();
});

final childSummaryProvider =
    FutureProvider.autoDispose.family<ChildSummary, String>(
        (ref, childId) async {
  return ApiService.instance.getChildSummary(childId);
});

final childCertificatesProvider =
    FutureProvider.autoDispose.family<List<Certificate>, String>(
        (ref, childId) async {
  return ApiService.instance.getChildCertificates(childId);
});

final childQuizAttemptsProvider =
    FutureProvider.autoDispose.family<List<QuizAttempt>, String>(
        (ref, childId) async {
  return ApiService.instance.getChildQuizAttempts(childId);
});

/// Admin-side: parents linked to a given student.
final studentParentsProvider =
    FutureProvider.autoDispose.family<List<StudentParent>, String>(
        (ref, studentId) async {
  return ApiService.instance.listStudentParents(studentId);
});
