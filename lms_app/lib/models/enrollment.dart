import 'certificate.dart';

/// Minimal course info the /enrollments/mine endpoint returns nested per row.
class EnrolledCourseStub {
  final String id;
  final String title;
  final String? gradeId;
  final String category;
  final String? electiveGroup;
  final String? thumbnailUrl;
  final String status;

  const EnrolledCourseStub({
    required this.id,
    required this.title,
    required this.category,
    required this.status,
    this.gradeId,
    this.electiveGroup,
    this.thumbnailUrl,
  });

  factory EnrolledCourseStub.fromJson(Map<String, dynamic> j) => EnrolledCourseStub(
        id: j['id'] as String,
        title: (j['title'] ?? '') as String,
        gradeId: j['gradeId'] as String?,
        category: (j['category'] ?? 'general') as String,
        electiveGroup: j['electiveGroup'] as String?,
        thumbnailUrl: j['thumbnailUrl'] as String?,
        status: (j['status'] ?? 'draft') as String,
      );
}

class Enrollment {
  final String id;
  final String studentId;
  final String courseId;
  final String status;         // active | dropped | completed
  final String enrolledVia;    // auto_mandatory | elective_choice | manual
  final int progressPercent;
  final DateTime? enrolledAt;
  final DateTime? completedAt;
  final EnrolledCourseStub? course;

  // Phase 3 grade rollup cache (server-computed)
  final double? cachedPercent;
  final String? cachedLetter;
  final double? cachedGpa;

  // Phase 5 — auto-issued certificate summary (null unless issued)
  final CertificateSummary? certificate;

  const Enrollment({
    required this.id,
    required this.studentId,
    required this.courseId,
    required this.status,
    required this.enrolledVia,
    this.progressPercent = 0,
    this.enrolledAt,
    this.completedAt,
    this.course,
    this.cachedPercent,
    this.cachedLetter,
    this.cachedGpa,
    this.certificate,
  });

  /// Matches the backend's `Enrollment.is_active` property: a live
  /// student-course relationship. Includes both 'active' and 'completed'
  /// because a completed enrollment still owns lesson history, grades,
  /// certificates, and read access — the student is still "in" the course.
  bool get isActive => status == 'active' || status == 'completed';
  bool get isCompleted => status == 'completed';
  bool get isDropped => status == 'dropped';
  /// True only while progress < 100% and status is not dropped.
  bool get isInProgress => status == 'active';

  factory Enrollment.fromJson(Map<String, dynamic> j) => Enrollment(
        id: j['id'] as String,
        studentId: (j['studentId'] ?? '') as String,
        courseId: (j['courseId'] ?? '') as String,
        status: (j['status'] ?? 'active') as String,
        enrolledVia: (j['enrolledVia'] ?? 'manual') as String,
        progressPercent: (j['progressPercent'] ?? 0) as int,
        enrolledAt: j['enrolledAt'] != null ? DateTime.tryParse(j['enrolledAt'] as String) : null,
        completedAt: j['completedAt'] != null ? DateTime.tryParse(j['completedAt'] as String) : null,
        course: j['course'] is Map<String, dynamic>
            ? EnrolledCourseStub.fromJson(j['course'] as Map<String, dynamic>)
            : null,
        cachedPercent:
            (j['cachedPercent'] is num) ? (j['cachedPercent'] as num).toDouble() : null,
        cachedLetter: j['cachedLetter'] as String?,
        cachedGpa: (j['cachedGpa'] is num) ? (j['cachedGpa'] as num).toDouble() : null,
        certificate: j['certificate'] is Map<String, dynamic>
            ? CertificateSummary.fromJson(j['certificate'] as Map<String, dynamic>)
            : null,
      );
}

/// One pending elective choice for a student — the group tag + the alternatives.
class PendingElective {
  final String group;
  final List<PendingElectiveOption> options;

  const PendingElective({required this.group, required this.options});

  factory PendingElective.fromJson(Map<String, dynamic> j) => PendingElective(
        group: (j['group'] ?? '') as String,
        options: (j['options'] as List<dynamic>? ?? const [])
            .map((e) => PendingElectiveOption.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class PendingElectiveOption {
  final String courseId;
  final String title;
  final String? instructorName;

  const PendingElectiveOption({
    required this.courseId,
    required this.title,
    this.instructorName,
  });

  factory PendingElectiveOption.fromJson(Map<String, dynamic> j) => PendingElectiveOption(
        courseId: (j['courseId'] ?? '') as String,
        title: (j['title'] ?? '') as String,
        instructorName: j['instructorName'] as String?,
      );
}
