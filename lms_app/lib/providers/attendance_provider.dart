import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/attendance.dart';
import '../services/api_service.dart';

/// Phase 12 attendance providers. All FutureProvider.autoDispose so
/// leaving a screen releases the cached value; screens re-fetch on init.

/// Homeroom / admin view of one class on one date.
class ClassAttendanceKey {
  final String classId;
  final DateTime date;
  const ClassAttendanceKey(this.classId, this.date);

  @override
  bool operator ==(Object other) =>
      other is ClassAttendanceKey &&
      other.classId == classId &&
      _dateOnly(other.date) == _dateOnly(date);
  @override
  int get hashCode => Object.hash(classId, _dateOnly(date));

  static DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);
}

final classAttendanceProvider =
    FutureProvider.autoDispose.family<ClassAttendance, ClassAttendanceKey>(
        (ref, key) async {
  return ApiService.instance.getClassAttendance(key.classId, key.date);
});

/// A single student's full attendance history — used by admin/teacher.
final studentAttendanceProvider =
    FutureProvider.autoDispose.family<List<AttendanceMark>, String>(
        (ref, studentId) async {
  return ApiService.instance.getStudentAttendance(studentId);
});

/// The student's own history.
final myAttendanceProvider =
    FutureProvider.autoDispose<List<AttendanceMark>>((ref) async {
  return ApiService.instance.getMyAttendance();
});

/// Linked-child history for the parent portal.
final childAttendanceProvider =
    FutureProvider.autoDispose.family<List<AttendanceMark>, String>(
        (ref, childId) async {
  return ApiService.instance.getChildAttendance(childId);
});
