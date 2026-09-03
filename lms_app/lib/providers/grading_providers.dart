import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';

final schoolYearsProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listSchoolYears();
});

final termsProvider = FutureProvider.autoDispose.family((ref, String yearId) async {
  return ApiService.instance.listTerms(yearId);
});

final gradeCategoriesProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listGradeCategories();
});

final gradingScaleProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listGradingScale();
});

final rubricProvider = FutureProvider.autoDispose.family((ref, String courseId) async {
  return ApiService.instance.getRubric(courseId);
});

final myReportCardProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.getMyReportCard();
});

/// Report card for a specific student — admin / teacher / parent view.
final studentReportCardProvider =
    FutureProvider.autoDispose.family((ref, String studentId) async {
  return ApiService.instance.getStudentReportCard(studentId);
});

/// Continue-where-you-left-off pointer for the current student.
final continuePointerProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.getContinuePointer();
});
