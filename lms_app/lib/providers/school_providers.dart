import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';

// Simple async providers for the admin surfaces.

final sectionsProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listSections();
});

final gradesProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listGrades();
});

final classesProvider = FutureProvider.autoDispose.family((ref, String? gradeId) async {
  return ApiService.instance.listClasses(gradeId: gradeId);
});

final classDetailProvider = FutureProvider.autoDispose.family((ref, String classId) async {
  return ApiService.instance.getClass(classId);
});

final gradeCurriculumProvider =
    FutureProvider.autoDispose.family((ref, String gradeId) async {
  return ApiService.instance.getGradeCurriculum(gradeId);
});

final unassignedStudentsProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.searchStudents(unassigned: true, limit: 50);
});

final instructorsProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listInstructors();
});

final departmentLeadersProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listDepartmentLeaders();
});

/// Pending electives for one student — used on the student-detail admin screen.
final pendingElectivesProvider =
    FutureProvider.autoDispose.family((ref, String studentId) async {
  return ApiService.instance.getPendingElectives(studentId);
});
