import 'enrollment.dart';
import 'module.dart';

class Course {
  final String id;
  final String title;
  final String description;
  final String? gradeId;
  final String? gradeName;
  final String? electiveGroup;
  final String? instructorId;
  final String? instructorName;
  final double price;
  final bool isFree;
  final String category;
  final String? thumbnailUrl;
  final String status; // draft | published
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final List<CourseModule> modules;

  // Phase 2 additions
  final Enrollment? myEnrollment;
  final bool isEnrolled;
  final int? enrolledCount;

  // Phase 18 — attendance projection for the student caller.
  final MyAttendanceSummary? myAttendance;

  const Course({
    required this.id,
    required this.title,
    required this.description,
    required this.instructorId,
    required this.instructorName,
    required this.price,
    required this.isFree,
    required this.category,
    required this.thumbnailUrl,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.gradeId,
    this.gradeName,
    this.electiveGroup,
    this.modules = const [],
    this.myEnrollment,
    this.isEnrolled = false,
    this.enrolledCount,
    this.myAttendance,
  });

  bool get isPublished => status == 'published';
  bool get isDraft => status == 'draft';
  bool get isElective => electiveGroup != null && electiveGroup!.isNotEmpty;
  bool get isMandatory => !isElective;

  factory Course.fromJson(Map<String, dynamic> j) => Course(
        id: j['id'] as String,
        title: (j['title'] ?? '') as String,
        description: (j['description'] ?? '') as String,
        instructorId: j['instructorId'] as String?,
        instructorName: j['instructorName'] as String?,
        price: (j['price'] is num ? (j['price'] as num).toDouble() : 0.0),
        isFree: (j['isFree'] ?? true) as bool,
        category: (j['category'] ?? 'general') as String,
        thumbnailUrl: j['thumbnailUrl'] as String?,
        status: (j['status'] ?? 'draft') as String,
        gradeId: j['gradeId'] as String?,
        gradeName: j['gradeName'] as String?,
        electiveGroup: j['electiveGroup'] as String?,
        createdAt: j['createdAt'] != null ? DateTime.tryParse(j['createdAt'] as String) : null,
        updatedAt: j['updatedAt'] != null ? DateTime.tryParse(j['updatedAt'] as String) : null,
        modules: (j['modules'] as List<dynamic>? ?? const [])
            .map((e) => CourseModule.fromJson(e as Map<String, dynamic>))
            .toList(),
        myEnrollment: j['myEnrollment'] is Map<String, dynamic>
            ? Enrollment.fromJson(j['myEnrollment'] as Map<String, dynamic>)
            : null,
        isEnrolled: (j['isEnrolled'] ?? false) as bool,
        enrolledCount: j['enrolledCount'] as int?,
        myAttendance: j['myAttendance'] is Map<String, dynamic>
            ? MyAttendanceSummary.fromJson(
                j['myAttendance'] as Map<String, dynamic>)
            : null,
      );
}

/// Phase 18 — per-student attendance summary. Same shape backend-side —
/// attendance is class-level (not per-course), so this number is the
/// same across every course the caller is enrolled in.
class MyAttendanceSummary {
  final int present;
  final int absent;
  final int late;
  final int excused;
  final int total;
  final double? percent;

  const MyAttendanceSummary({
    this.present = 0,
    this.absent = 0,
    this.late = 0,
    this.excused = 0,
    this.total = 0,
    this.percent,
  });

  bool get hasHistory => total > 0;

  factory MyAttendanceSummary.fromJson(Map<String, dynamic> j) =>
      MyAttendanceSummary(
        present: (j['present'] as num?)?.toInt() ?? 0,
        absent: (j['absent'] as num?)?.toInt() ?? 0,
        late: (j['late'] as num?)?.toInt() ?? 0,
        excused: (j['excused'] as num?)?.toInt() ?? 0,
        total: (j['total'] as num?)?.toInt() ?? 0,
        percent: (j['percent'] as num?)?.toDouble(),
      );
}
