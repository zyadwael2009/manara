// Phase 32 · T2 — digital diploma.

class Diploma {
  final String id;
  final String diplomaNumber;
  final String studentId;
  final String? studentName;
  final String? studentEmail;
  final String? gradeId;
  final int classOfYear;
  final DateTime? issuedAt;
  final String? honors;
  final int totalCertificates;
  final double? averagePercent;
  final bool revoked;
  final DateTime? revokedAt;
  final String? revokedReason;

  const Diploma({
    required this.id,
    required this.diplomaNumber,
    required this.studentId,
    required this.classOfYear,
    required this.totalCertificates,
    required this.revoked,
    this.studentName,
    this.studentEmail,
    this.gradeId,
    this.issuedAt,
    this.honors,
    this.averagePercent,
    this.revokedAt,
    this.revokedReason,
  });

  factory Diploma.fromJson(Map<String, dynamic> j) => Diploma(
        id: j['id'] as String,
        diplomaNumber: (j['diplomaNumber'] as String?) ?? '',
        studentId: (j['studentId'] as String?) ?? '',
        studentName: j['studentName'] as String?,
        studentEmail: j['studentEmail'] as String?,
        gradeId: j['gradeId'] as String?,
        classOfYear: (j['classOfYear'] as num?)?.toInt() ?? 0,
        issuedAt: j['issuedAt'] == null
            ? null
            : DateTime.tryParse(j['issuedAt'] as String),
        honors: j['honors'] as String?,
        totalCertificates:
            (j['totalCertificates'] as num?)?.toInt() ?? 0,
        averagePercent: (j['averagePercent'] as num?)?.toDouble(),
        revoked: (j['revoked'] as bool?) ?? false,
        revokedAt: j['revokedAt'] == null
            ? null
            : DateTime.tryParse(j['revokedAt'] as String),
        revokedReason: j['revokedReason'] as String?,
      );
}
