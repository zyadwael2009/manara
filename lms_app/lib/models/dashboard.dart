// Phase 7 — Dashboard payloads.
//
// Plain value types. Field naming mirrors the backend camelCase JSON so
// `fromJson` is a straight read; no post-processing lives here.

// ============================================================================
// Instructor dashboard
// ============================================================================
class InstructorCourseRow {
  final String id;
  final String title;
  final String? gradeName;
  final String category;
  final int enrollmentCount;
  final double avgCompletion; // 0-100
  final double completionRate; // 0-1
  final double quizPassRate; // 0-1
  final double certRate; // 0-1
  final int certCount;
  final int quizCount;

  InstructorCourseRow({
    required this.id,
    required this.title,
    required this.gradeName,
    required this.category,
    required this.enrollmentCount,
    required this.avgCompletion,
    required this.completionRate,
    required this.quizPassRate,
    required this.certRate,
    required this.certCount,
    required this.quizCount,
  });

  factory InstructorCourseRow.fromJson(Map<String, dynamic> j) =>
      InstructorCourseRow(
        id: j['id'] as String,
        title: j['title'] as String,
        gradeName: j['gradeName'] as String?,
        category: (j['category'] as String?) ?? 'general',
        enrollmentCount: (j['enrollmentCount'] as num?)?.toInt() ?? 0,
        avgCompletion: (j['avgCompletion'] as num?)?.toDouble() ?? 0.0,
        completionRate: (j['completionRate'] as num?)?.toDouble() ?? 0.0,
        quizPassRate: (j['quizPassRate'] as num?)?.toDouble() ?? 0.0,
        certRate: (j['certRate'] as num?)?.toDouble() ?? 0.0,
        certCount: (j['certCount'] as num?)?.toInt() ?? 0,
        quizCount: (j['quizCount'] as num?)?.toInt() ?? 0,
      );
}

class InstructorDashboardSummary {
  final int courseCount;
  final int totalStudents;
  final double avgCompletion; // 0-100
  final double avgQuizPassRate; // 0-1

  InstructorDashboardSummary({
    required this.courseCount,
    required this.totalStudents,
    required this.avgCompletion,
    required this.avgQuizPassRate,
  });

  factory InstructorDashboardSummary.fromJson(Map<String, dynamic> j) =>
      InstructorDashboardSummary(
        courseCount: (j['courseCount'] as num?)?.toInt() ?? 0,
        totalStudents: (j['totalStudents'] as num?)?.toInt() ?? 0,
        avgCompletion: (j['avgCompletion'] as num?)?.toDouble() ?? 0.0,
        avgQuizPassRate: (j['avgQuizPassRate'] as num?)?.toDouble() ?? 0.0,
      );
}

class InstructorDashboard {
  final List<InstructorCourseRow> courses;
  final InstructorDashboardSummary summary;

  InstructorDashboard({required this.courses, required this.summary});

  factory InstructorDashboard.fromJson(Map<String, dynamic> j) =>
      InstructorDashboard(
        courses: (j['courses'] as List<dynamic>? ?? [])
            .map((e) => InstructorCourseRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        summary: InstructorDashboardSummary.fromJson(
            j['summary'] as Map<String, dynamic>? ?? const {}),
      );
}

// ============================================================================
// Course drill-down
// ============================================================================
class HistogramBin {
  final String label;
  final int count;
  HistogramBin({required this.label, required this.count});
  factory HistogramBin.fromJson(Map<String, dynamic> j) => HistogramBin(
        label: j['label'] as String,
        count: (j['count'] as num?)?.toInt() ?? 0,
      );
}

class ModuleCompletion {
  final String id;
  final String title;
  final double avgCompletion; // 0-100
  ModuleCompletion({required this.id, required this.title, required this.avgCompletion});
  factory ModuleCompletion.fromJson(Map<String, dynamic> j) => ModuleCompletion(
        id: j['id'] as String,
        title: j['title'] as String,
        avgCompletion: (j['avgCompletion'] as num?)?.toDouble() ?? 0.0,
      );
}

class QuizPassRow {
  final String id;
  final String title;
  final int passingScore;
  final double passRate; // 0-1
  final double attemptedRate; // 0-1
  QuizPassRow({
    required this.id,
    required this.title,
    required this.passingScore,
    required this.passRate,
    required this.attemptedRate,
  });
  factory QuizPassRow.fromJson(Map<String, dynamic> j) => QuizPassRow(
        id: j['id'] as String,
        title: j['title'] as String,
        passingScore: (j['passingScore'] as num?)?.toInt() ?? 60,
        passRate: (j['passRate'] as num?)?.toDouble() ?? 0.0,
        attemptedRate: (j['attemptedRate'] as num?)?.toDouble() ?? 0.0,
      );
}

class TopStudent {
  final String? studentId;
  final String? studentName;
  final double percent;
  final String? letter;
  TopStudent({this.studentId, this.studentName, required this.percent, this.letter});
  factory TopStudent.fromJson(Map<String, dynamic> j) => TopStudent(
        studentId: j['studentId'] as String?,
        studentName: j['studentName'] as String?,
        percent: (j['percent'] as num?)?.toDouble() ?? 0.0,
        letter: j['letter'] as String?,
      );
}

class AtRiskStudent {
  final String? studentId;
  final String? studentName;
  final int progressPercent;
  final double? cachedPercent;
  final List<String> reasons;
  AtRiskStudent({
    this.studentId,
    this.studentName,
    required this.progressPercent,
    this.cachedPercent,
    required this.reasons,
  });
  factory AtRiskStudent.fromJson(Map<String, dynamic> j) => AtRiskStudent(
        studentId: j['studentId'] as String?,
        studentName: j['studentName'] as String?,
        progressPercent: (j['progressPercent'] as num?)?.toInt() ?? 0,
        cachedPercent: (j['cachedPercent'] as num?)?.toDouble(),
        reasons: (j['reasons'] as List<dynamic>? ?? []).cast<String>(),
      );
}

class CourseDrilldown {
  final String courseId;
  final String courseTitle;
  final int enrollmentCount;
  final int minCertificatePercent;
  final List<HistogramBin> completionHistogram;
  final List<ModuleCompletion> moduleCompletion;
  final List<QuizPassRow> quizPassRates;
  final List<TopStudent> topStudents;
  final List<AtRiskStudent> atRisk;

  CourseDrilldown({
    required this.courseId,
    required this.courseTitle,
    required this.enrollmentCount,
    required this.minCertificatePercent,
    required this.completionHistogram,
    required this.moduleCompletion,
    required this.quizPassRates,
    required this.topStudents,
    required this.atRisk,
  });

  factory CourseDrilldown.fromJson(Map<String, dynamic> j) => CourseDrilldown(
        courseId: j['courseId'] as String,
        courseTitle: j['courseTitle'] as String,
        enrollmentCount: (j['enrollmentCount'] as num?)?.toInt() ?? 0,
        minCertificatePercent: (j['minCertificatePercent'] as num?)?.toInt() ?? 60,
        completionHistogram: (j['completionHistogram'] as List<dynamic>? ?? [])
            .map((e) => HistogramBin.fromJson(e as Map<String, dynamic>))
            .toList(),
        moduleCompletion: (j['moduleCompletion'] as List<dynamic>? ?? [])
            .map((e) => ModuleCompletion.fromJson(e as Map<String, dynamic>))
            .toList(),
        quizPassRates: (j['quizPassRates'] as List<dynamic>? ?? [])
            .map((e) => QuizPassRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        topStudents: (j['topStudents'] as List<dynamic>? ?? [])
            .map((e) => TopStudent.fromJson(e as Map<String, dynamic>))
            .toList(),
        atRisk: (j['atRisk'] as List<dynamic>? ?? [])
            .map((e) => AtRiskStudent.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

// ============================================================================
// Admin dashboard
// ============================================================================
class AdminTopline {
  final int totalUsers;
  final Map<String, int> usersByRole;
  final int publishedCourses;
  final int draftCourses;
  final int activeEnrollments;
  final double platformCompletionRate; // 0-1
  final int certsIssuedLast30d;
  // Phase 30 · T2 — fee KPIs.
  final double feeOutstandingTotal;
  final int studentsWithOverdueFees;

  AdminTopline({
    required this.totalUsers,
    required this.usersByRole,
    required this.publishedCourses,
    required this.draftCourses,
    required this.activeEnrollments,
    required this.platformCompletionRate,
    required this.certsIssuedLast30d,
    this.feeOutstandingTotal = 0.0,
    this.studentsWithOverdueFees = 0,
  });

  factory AdminTopline.fromJson(Map<String, dynamic> j) => AdminTopline(
        totalUsers: (j['totalUsers'] as num?)?.toInt() ?? 0,
        usersByRole: {
          for (final entry
              in (j['usersByRole'] as Map<String, dynamic>? ?? const {}).entries)
            entry.key: (entry.value as num).toInt(),
        },
        publishedCourses: (j['publishedCourses'] as num?)?.toInt() ?? 0,
        draftCourses: (j['draftCourses'] as num?)?.toInt() ?? 0,
        activeEnrollments: (j['activeEnrollments'] as num?)?.toInt() ?? 0,
        platformCompletionRate:
            (j['platformCompletionRate'] as num?)?.toDouble() ?? 0.0,
        certsIssuedLast30d: (j['certsIssuedLast30d'] as num?)?.toInt() ?? 0,
        feeOutstandingTotal:
            (j['feeOutstandingTotal'] as num?)?.toDouble() ?? 0.0,
        studentsWithOverdueFees:
            (j['studentsWithOverdueFees'] as num?)?.toInt() ?? 0,
      );
}

class PopularCourseRow {
  final String courseId;
  final String title;
  final int enrollmentCount;
  PopularCourseRow({required this.courseId, required this.title, required this.enrollmentCount});
  factory PopularCourseRow.fromJson(Map<String, dynamic> j) => PopularCourseRow(
        courseId: j['courseId'] as String,
        title: j['title'] as String,
        enrollmentCount: (j['enrollmentCount'] as num?)?.toInt() ?? 0,
      );
}

class CompletionCourseRow {
  final String courseId;
  final String title;
  final double avgCompletion;
  final int enrollmentCount;
  CompletionCourseRow({
    required this.courseId,
    required this.title,
    required this.avgCompletion,
    required this.enrollmentCount,
  });
  factory CompletionCourseRow.fromJson(Map<String, dynamic> j) => CompletionCourseRow(
        courseId: j['courseId'] as String,
        title: j['title'] as String,
        avgCompletion: (j['avgCompletion'] as num?)?.toDouble() ?? 0.0,
        enrollmentCount: (j['enrollmentCount'] as num?)?.toInt() ?? 0,
      );
}

class MonthBucket {
  final String month; // 'YYYY-MM'
  final int count;
  MonthBucket({required this.month, required this.count});
  factory MonthBucket.fromJson(Map<String, dynamic> j) => MonthBucket(
        month: j['month'] as String,
        count: (j['count'] as num?)?.toInt() ?? 0,
      );
}

class AdminDashboard {
  final AdminTopline topline;
  final List<PopularCourseRow> mostPopular;
  final List<CompletionCourseRow> highestCompletion;
  final List<MonthBucket> certsPerMonth;
  final List<MonthBucket> usersPerMonth;
  final Map<String, int> gradeBands;

  AdminDashboard({
    required this.topline,
    required this.mostPopular,
    required this.highestCompletion,
    required this.certsPerMonth,
    required this.usersPerMonth,
    required this.gradeBands,
  });

  factory AdminDashboard.fromJson(Map<String, dynamic> j) => AdminDashboard(
        topline: AdminTopline.fromJson(j['topline'] as Map<String, dynamic>? ?? const {}),
        mostPopular: (j['mostPopular'] as List<dynamic>? ?? [])
            .map((e) => PopularCourseRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        highestCompletion: (j['highestCompletion'] as List<dynamic>? ?? [])
            .map((e) => CompletionCourseRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        certsPerMonth: (j['certsPerMonth'] as List<dynamic>? ?? [])
            .map((e) => MonthBucket.fromJson(e as Map<String, dynamic>))
            .toList(),
        usersPerMonth: (j['usersPerMonth'] as List<dynamic>? ?? [])
            .map((e) => MonthBucket.fromJson(e as Map<String, dynamic>))
            .toList(),
        gradeBands: {
          for (final entry
              in (j['gradeBands'] as Map<String, dynamic>? ?? const {}).entries)
            entry.key: (entry.value as num).toInt(),
        },
      );
}
