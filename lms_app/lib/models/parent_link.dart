// Phase 6 — parent-portal payloads.
//
// Plain value types matching the JSON shape returned by /api/parents and
// the admin-side /api/users/<id>/parents endpoints.

import 'enrollment.dart';

/// A parent's linked child, as seen from a parent's own listing.
class LinkedChild {
  final String linkId;
  final String studentId;
  final String name;
  final String? email;
  final String? classId;
  final String? className;
  final String? gradeName;
  final String relationship;
  final DateTime? linkCreatedAt;
  /// Phase 12: today's attendance status (or null if unmarked). Powers the
  /// red badge on the child card on parent home.
  final String? todayAttendanceStatus;

  const LinkedChild({
    required this.linkId,
    required this.studentId,
    required this.name,
    required this.relationship,
    this.email,
    this.classId,
    this.className,
    this.gradeName,
    this.linkCreatedAt,
    this.todayAttendanceStatus,
  });

  factory LinkedChild.fromJson(Map<String, dynamic> j) => LinkedChild(
        linkId: j['linkId'] as String,
        studentId: j['studentId'] as String,
        name: (j['name'] ?? '') as String,
        email: j['email'] as String?,
        classId: j['classId'] as String?,
        className: j['className'] as String?,
        gradeName: j['gradeName'] as String?,
        relationship: (j['relationship'] ?? 'guardian') as String,
        linkCreatedAt: j['linkCreatedAt'] == null
            ? null
            : DateTime.tryParse(j['linkCreatedAt'] as String),
        todayAttendanceStatus: j['todayAttendanceStatus'] as String?,
      );
}

/// A student's linked parent, as seen from the admin roster.
class StudentParent {
  final String linkId;
  final String parentId;
  final String name;
  final String? email;
  final String relationship;
  final DateTime? linkCreatedAt;

  const StudentParent({
    required this.linkId,
    required this.parentId,
    required this.name,
    required this.relationship,
    this.email,
    this.linkCreatedAt,
  });

  factory StudentParent.fromJson(Map<String, dynamic> j) => StudentParent(
        linkId: j['linkId'] as String,
        parentId: j['parentId'] as String,
        name: (j['name'] ?? '') as String,
        email: j['email'] as String?,
        relationship: (j['relationship'] ?? 'guardian') as String,
        linkCreatedAt: j['linkCreatedAt'] == null
            ? null
            : DateTime.tryParse(j['linkCreatedAt'] as String),
      );
}

class ChildSummary {
  final ChildStudentStub student;
  final List<Enrollment> enrollments;
  final int activeCertificateCount;

  const ChildSummary({
    required this.student,
    required this.enrollments,
    required this.activeCertificateCount,
  });

  factory ChildSummary.fromJson(Map<String, dynamic> j) => ChildSummary(
        student: ChildStudentStub.fromJson(j['student'] as Map<String, dynamic>),
        enrollments: (j['enrollments'] as List<dynamic>? ?? [])
            .map((e) => Enrollment.fromJson(e as Map<String, dynamic>))
            .toList(),
        activeCertificateCount:
            (j['activeCertificateCount'] as num?)?.toInt() ?? 0,
      );
}

class ChildStudentStub {
  final String id;
  final String name;
  final String? email;
  final String? classId;
  final String? className;
  final String? gradeName;

  const ChildStudentStub({
    required this.id,
    required this.name,
    this.email,
    this.classId,
    this.className,
    this.gradeName,
  });

  factory ChildStudentStub.fromJson(Map<String, dynamic> j) => ChildStudentStub(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        email: j['email'] as String?,
        classId: j['classId'] as String?,
        className: j['className'] as String?,
        gradeName: j['gradeName'] as String?,
      );
}
