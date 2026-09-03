// Phase 28 — cohort / semester comparison payloads.
//
// Two `TermSnapshot`s per response, one per term. Each snapshot has:
//   * `perClass` — one row per active class in the school this term.
//   * `overall` — unweighted average across those classes (matches the
//     "small class visibility" call in the plan).

class CohortComparison {
  final TermSnapshot termA;
  final TermSnapshot termB;
  const CohortComparison({required this.termA, required this.termB});
  factory CohortComparison.fromJson(Map<String, dynamic> j) =>
      CohortComparison(
        termA: TermSnapshot.fromJson(j['termA'] as Map<String, dynamic>),
        termB: TermSnapshot.fromJson(j['termB'] as Map<String, dynamic>),
      );
}

class TermSnapshot {
  final String termId;
  final String termName;
  final String? startDate;
  final String? endDate;
  final List<CohortClassRow> perClass;
  final CohortMetrics overall;

  const TermSnapshot({
    required this.termId,
    required this.termName,
    required this.perClass,
    required this.overall,
    this.startDate,
    this.endDate,
  });

  factory TermSnapshot.fromJson(Map<String, dynamic> j) {
    final raw = (j['perClass'] as List?) ?? const [];
    return TermSnapshot(
      termId: (j['termId'] as String?) ?? '',
      termName: (j['termName'] as String?) ?? '',
      startDate: j['startDate'] as String?,
      endDate: j['endDate'] as String?,
      perClass: raw
          .whereType<Map<String, dynamic>>()
          .map(CohortClassRow.fromJson)
          .toList(),
      overall: CohortMetrics.fromJson(
          (j['overall'] as Map<String, dynamic>?) ?? const {}),
    );
  }
}

class CohortClassRow {
  final String classId;
  final String className;
  final String? gradeId;
  final int students;
  final double attendanceRate;
  final double avgPercent;
  final double passRate;
  final int certCount;

  const CohortClassRow({
    required this.classId,
    required this.className,
    required this.students,
    required this.attendanceRate,
    required this.avgPercent,
    required this.passRate,
    required this.certCount,
    this.gradeId,
  });

  factory CohortClassRow.fromJson(Map<String, dynamic> j) => CohortClassRow(
        classId: (j['classId'] as String?) ?? '',
        className: (j['className'] as String?) ?? '',
        gradeId: j['gradeId'] as String?,
        students: (j['students'] as num?)?.toInt() ?? 0,
        attendanceRate: (j['attendanceRate'] as num?)?.toDouble() ?? 0.0,
        avgPercent: (j['avgPercent'] as num?)?.toDouble() ?? 0.0,
        passRate: (j['passRate'] as num?)?.toDouble() ?? 0.0,
        certCount: (j['certCount'] as num?)?.toInt() ?? 0,
      );
}

class CohortMetrics {
  final double attendanceRate;
  final double avgPercent;
  final double passRate;
  final int certCount;
  const CohortMetrics({
    required this.attendanceRate,
    required this.avgPercent,
    required this.passRate,
    required this.certCount,
  });
  factory CohortMetrics.fromJson(Map<String, dynamic> j) => CohortMetrics(
        attendanceRate: (j['attendanceRate'] as num?)?.toDouble() ?? 0.0,
        avgPercent: (j['avgPercent'] as num?)?.toDouble() ?? 0.0,
        passRate: (j['passRate'] as num?)?.toDouble() ?? 0.0,
        certCount: (j['certCount'] as num?)?.toInt() ?? 0,
      );
}
