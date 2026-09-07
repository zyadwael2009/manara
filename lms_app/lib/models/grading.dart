/// Consolidated grading-related model classes — kept in one file since
/// they're small and always used together.
library;

class GradeCategory {
  final String id;
  final String name;
  final String slug;
  final int orderIndex;
  final bool isSystem;

  const GradeCategory({
    required this.id,
    required this.name,
    required this.slug,
    this.orderIndex = 0,
    this.isSystem = false,
  });

  factory GradeCategory.fromJson(Map<String, dynamic> j) => GradeCategory(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        slug: (j['slug'] ?? '') as String,
        orderIndex: (j['orderIndex'] ?? 0) as int,
        isSystem: (j['isSystem'] ?? false) as bool,
      );
}

class GradingScaleBand {
  final String id;
  final int minPercent;
  final int maxPercent;
  final String letter;
  final double gpaValue;
  final int orderIndex;

  const GradingScaleBand({
    required this.id,
    required this.minPercent,
    required this.maxPercent,
    required this.letter,
    required this.gpaValue,
    this.orderIndex = 0,
  });

  factory GradingScaleBand.fromJson(Map<String, dynamic> j) => GradingScaleBand(
        id: j['id'] as String,
        minPercent: (j['minPercent'] ?? 0) as int,
        maxPercent: (j['maxPercent'] ?? 0) as int,
        letter: (j['letter'] ?? '') as String,
        gpaValue: (j['gpaValue'] is num) ? (j['gpaValue'] as num).toDouble() : 0.0,
        orderIndex: (j['orderIndex'] ?? 0) as int,
      );
}

class RubricItem {
  final String id;
  final String courseId;
  final String gradeCategoryId;
  final String? gradeCategoryName;
  final String? gradeCategorySlug;
  final int maxScore;
  final int orderIndex;

  const RubricItem({
    required this.id,
    required this.courseId,
    required this.gradeCategoryId,
    required this.maxScore,
    this.gradeCategoryName,
    this.gradeCategorySlug,
    this.orderIndex = 0,
  });

  factory RubricItem.fromJson(Map<String, dynamic> j) => RubricItem(
        id: (j['id'] ?? '') as String,
        courseId: (j['courseId'] ?? '') as String,
        gradeCategoryId: (j['gradeCategoryId'] ?? '') as String,
        gradeCategoryName: j['gradeCategoryName'] as String?,
        gradeCategorySlug: j['gradeCategorySlug'] as String?,
        maxScore: (j['maxScore'] ?? 0) as int,
        orderIndex: (j['orderIndex'] ?? 0) as int,
      );
}

/// The report-card view returned by `/api/reports/{mine|students/<id>}`.
class ReportCard {
  final String? termId;
  final List<ReportCardSubject> subjects;
  final ReportCardCumulative? cumulative;

  const ReportCard({this.termId, this.subjects = const [], this.cumulative});

  factory ReportCard.fromJson(Map<String, dynamic> j) => ReportCard(
        termId: j['termId'] as String?,
        subjects: (j['subjects'] as List<dynamic>? ?? const [])
            .map((e) => ReportCardSubject.fromJson(e as Map<String, dynamic>))
            .toList(),
        cumulative: j['cumulative'] is Map<String, dynamic>
            ? ReportCardCumulative.fromJson(j['cumulative'] as Map<String, dynamic>)
            : null,
      );
}

class ReportCardSubject {
  final String courseId;
  final String courseTitle;
  final String category;
  final List<RubricItem> rubric;
  /// Map of gradeCategoryId → score.
  final Map<String, double> entries;
  final double? percent;
  final String? letter;
  final double? gpaValue;

  const ReportCardSubject({
    required this.courseId,
    required this.courseTitle,
    required this.category,
    this.rubric = const [],
    this.entries = const {},
    this.percent,
    this.letter,
    this.gpaValue,
  });

  factory ReportCardSubject.fromJson(Map<String, dynamic> j) {
    final entriesRaw = (j['entries'] as Map<String, dynamic>? ?? const {});
    final entries = <String, double>{};
    entriesRaw.forEach((k, v) {
      if (v is num) entries[k] = v.toDouble();
    });
    return ReportCardSubject(
      courseId: (j['courseId'] ?? '') as String,
      courseTitle: (j['courseTitle'] ?? '') as String,
      category: (j['category'] ?? 'general') as String,
      rubric: (j['rubric'] as List<dynamic>? ?? const [])
          .map((e) => RubricItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      entries: entries,
      percent: (j['percent'] is num) ? (j['percent'] as num).toDouble() : null,
      letter: j['letter'] as String?,
      gpaValue: (j['gpaValue'] is num) ? (j['gpaValue'] as num).toDouble() : null,
    );
  }
}

class ReportCardCumulative {
  final double? percent;
  final String? letter;
  final double? gpaValue;

  const ReportCardCumulative({this.percent, this.letter, this.gpaValue});

  factory ReportCardCumulative.fromJson(Map<String, dynamic> j) => ReportCardCumulative(
        percent: (j['percent'] is num) ? (j['percent'] as num).toDouble() : null,
        letter: j['letter'] as String?,
        gpaValue: (j['gpaValue'] is num) ? (j['gpaValue'] as num).toDouble() : null,
      );
}

/// Gradebook view returned by `/api/classes/<id>/gradebook?...`.
class Gradebook {
  final String classId;
  final String className;
  final String courseId;
  final String courseTitle;
  final String termId;
  final String termName;
  final bool termIsLocked;
  final List<RubricItem> rubric;
  final List<GradebookRow> students;
  final bool canWrite;

  const Gradebook({
    required this.classId,
    required this.className,
    required this.courseId,
    required this.courseTitle,
    required this.termId,
    required this.termName,
    required this.termIsLocked,
    required this.canWrite,
    this.rubric = const [],
    this.students = const [],
  });

  factory Gradebook.fromJson(Map<String, dynamic> j) => Gradebook(
        classId: j['classId'] as String,
        className: (j['className'] ?? '') as String,
        courseId: j['courseId'] as String,
        courseTitle: (j['courseTitle'] ?? '') as String,
        termId: j['termId'] as String,
        termName: (j['termName'] ?? '') as String,
        termIsLocked: (j['termIsLocked'] ?? false) as bool,
        canWrite: (j['canWrite'] ?? false) as bool,
        rubric: (j['rubric'] as List<dynamic>? ?? const [])
            .map((e) => RubricItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        students: (j['students'] as List<dynamic>? ?? const [])
            .map((e) => GradebookRow.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class GradebookRow {
  final String enrollmentId;
  final String studentId;
  final String studentName;
  final Map<String, double> entries;
  final double? cachedPercent;
  final String? cachedLetter;
  final double? cachedGpa;

  const GradebookRow({
    required this.enrollmentId,
    required this.studentId,
    required this.studentName,
    this.entries = const {},
    this.cachedPercent,
    this.cachedLetter,
    this.cachedGpa,
  });

  factory GradebookRow.fromJson(Map<String, dynamic> j) {
    final entriesRaw = (j['entries'] as Map<String, dynamic>? ?? const {});
    final entries = <String, double>{};
    entriesRaw.forEach((k, v) {
      if (v is num) entries[k] = v.toDouble();
    });
    return GradebookRow(
      enrollmentId: j['enrollmentId'] as String,
      studentId: j['studentId'] as String,
      studentName: (j['studentName'] ?? '') as String,
      entries: entries,
      cachedPercent: (j['cachedPercent'] is num) ? (j['cachedPercent'] as num).toDouble() : null,
      cachedLetter: j['cachedLetter'] as String?,
      cachedGpa: (j['cachedGpa'] is num) ? (j['cachedGpa'] as num).toDouble() : null,
    );
  }
}

/// "Continue where you left off" pointer.
class ContinuePointer {
  final String enrollmentId;
  final String courseId;
  final String? courseTitle;
  final String? moduleId;
  final String? moduleTitle;
  /// Phase 9 audit fix F8: nullable. Backend now skips a pointer entirely
  /// when the touched lesson was deleted, but keep the cast permissive as
  /// belt-and-suspenders — a null here should never crash the Home screen.
  final String? lessonId;
  final String? lessonTitle;
  final int lastPositionSeconds;

  const ContinuePointer({
    required this.enrollmentId,
    required this.courseId,
    required this.lastPositionSeconds,
    this.lessonId,
    this.courseTitle,
    this.moduleId,
    this.moduleTitle,
    this.lessonTitle,
  });

  factory ContinuePointer.fromJson(Map<String, dynamic> j) => ContinuePointer(
        enrollmentId: j['enrollmentId'] as String,
        courseId: j['courseId'] as String,
        courseTitle: j['courseTitle'] as String?,
        moduleId: j['moduleId'] as String?,
        moduleTitle: j['moduleTitle'] as String?,
        lessonId: j['lessonId'] as String?,
        lessonTitle: j['lessonTitle'] as String?,
        lastPositionSeconds: (j['lastPositionSeconds'] ?? 0) as int,
      );
}

/// Progress state for one lesson from `/api/enrollments/<id>/progress`.
class LessonProgress {
  final String id;
  final String enrollmentId;
  final String lessonId;
  final bool completed;
  final String? completedAt;
  final int lastPositionSeconds;
  final String? lastVisitedAt;

  const LessonProgress({
    required this.id,
    required this.enrollmentId,
    required this.lessonId,
    this.completed = false,
    this.completedAt,
    this.lastPositionSeconds = 0,
    this.lastVisitedAt,
  });

  factory LessonProgress.fromJson(Map<String, dynamic> j) => LessonProgress(
        id: (j['id'] ?? '') as String,
        enrollmentId: (j['enrollmentId'] ?? '') as String,
        lessonId: (j['lessonId'] ?? '') as String,
        completed: (j['completed'] ?? false) as bool,
        completedAt: j['completedAt'] as String?,
        lastPositionSeconds: (j['lastPositionSeconds'] ?? 0) as int,
        lastVisitedAt: j['lastVisitedAt'] as String?,
      );
}
