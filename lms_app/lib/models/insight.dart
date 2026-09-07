/// Phase 22 — insight & intervention envelopes.
library;

class AtRiskRow {
  final String studentId;
  final String name;
  final String email;
  final bool atRisk;
  final List<String> reasons;

  const AtRiskRow({
    required this.studentId,
    required this.name,
    required this.email,
    required this.atRisk,
    this.reasons = const [],
  });

  factory AtRiskRow.fromJson(Map<String, dynamic> j) => AtRiskRow(
        studentId: (j['studentId'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        email: (j['email'] as String?) ?? '',
        atRisk: (j['atRisk'] as bool?) ?? false,
        reasons: (j['reasons'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList(),
      );

  /// Human labels for the machine-slug reasons the backend returns.
  static String labelFor(String reason) => switch (reason) {
        'low_grade' => 'Low cumulative grade',
        'low_attendance' => 'Low attendance',
        'missing_work' => 'Missing assignments',
        'failing_quizzes' => 'Failing quizzes',
        _ => reason,
      };
}

class GradeHistoryPoint {
  final DateTime recordedAt;
  final double percent;
  final String? letter;
  const GradeHistoryPoint({
    required this.recordedAt,
    required this.percent,
    this.letter,
  });
  factory GradeHistoryPoint.fromJson(Map<String, dynamic> j) =>
      GradeHistoryPoint(
        recordedAt: DateTime.tryParse((j['recordedAt'] as String?) ?? '') ??
            DateTime(1970),
        percent: (j['percent'] as num?)?.toDouble() ?? 0,
        letter: j['letter'] as String?,
      );
}

class GradeHistoryCourse {
  final String courseId;
  final String courseTitle;
  final List<GradeHistoryPoint> points;
  const GradeHistoryCourse({
    required this.courseId,
    required this.courseTitle,
    this.points = const [],
  });
  factory GradeHistoryCourse.fromJson(Map<String, dynamic> j) =>
      GradeHistoryCourse(
        courseId: (j['courseId'] as String?) ?? '',
        courseTitle: (j['courseTitle'] as String?) ?? '',
        points: (j['points'] as List<dynamic>? ?? const [])
            .map((e) => GradeHistoryPoint.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  /// +1 / 0 / -1 based on first vs last point in the series (needs 2+).
  int get trendDirection {
    if (points.length < 2) return 0;
    final first = points.first.percent;
    final last = points.last.percent;
    if ((last - first).abs() < 0.5) return 0;
    return last > first ? 1 : -1;
  }
}

class GradeHistory {
  final List<GradeHistoryCourse> series;
  const GradeHistory({this.series = const []});
  factory GradeHistory.fromJson(Map<String, dynamic> j) => GradeHistory(
        series: (j['series'] as List<dynamic>? ?? const [])
            .map(
                (e) => GradeHistoryCourse.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

// ---------------------------------------------------------------------------
// Attendance patterns
// ---------------------------------------------------------------------------
class AttendancePatterns {
  final List<ChronicAbsentee> chronicAbsentees;
  final List<TardyLeader> tardyLeaders;
  final List<ClassAttendanceRank> classes;
  const AttendancePatterns({
    this.chronicAbsentees = const [],
    this.tardyLeaders = const [],
    this.classes = const [],
  });
  factory AttendancePatterns.fromJson(Map<String, dynamic> j) =>
      AttendancePatterns(
        chronicAbsentees: (j['chronicAbsentees'] as List<dynamic>? ?? const [])
            .map((e) => ChronicAbsentee.fromJson(e as Map<String, dynamic>))
            .toList(),
        tardyLeaders: (j['tardyLeaders'] as List<dynamic>? ?? const [])
            .map((e) => TardyLeader.fromJson(e as Map<String, dynamic>))
            .toList(),
        classes: (j['classes'] as List<dynamic>? ?? const [])
            .map((e) => ClassAttendanceRank.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class ChronicAbsentee {
  final String studentId;
  final String name;
  final double? pctPresent;
  final int absentCount;
  const ChronicAbsentee({
    required this.studentId,
    required this.name,
    required this.absentCount,
    this.pctPresent,
  });
  factory ChronicAbsentee.fromJson(Map<String, dynamic> j) => ChronicAbsentee(
        studentId: (j['studentId'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        pctPresent: (j['pctPresent'] as num?)?.toDouble(),
        absentCount: (j['absentCount'] as num?)?.toInt() ?? 0,
      );
}

class TardyLeader {
  final String studentId;
  final String name;
  final int lateCount;
  const TardyLeader({
    required this.studentId,
    required this.name,
    required this.lateCount,
  });
  factory TardyLeader.fromJson(Map<String, dynamic> j) => TardyLeader(
        studentId: (j['studentId'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        lateCount: (j['lateCount'] as num?)?.toInt() ?? 0,
      );
}

class ClassAttendanceRank {
  final String classId;
  final String name;
  final double pctPresent;
  final int marksCount;
  const ClassAttendanceRank({
    required this.classId,
    required this.name,
    required this.pctPresent,
    required this.marksCount,
  });
  factory ClassAttendanceRank.fromJson(Map<String, dynamic> j) => ClassAttendanceRank(
        classId: (j['classId'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        pctPresent: (j['pctPresent'] as num?)?.toDouble() ?? 0,
        marksCount: (j['marksCount'] as num?)?.toInt() ?? 0,
      );
}
