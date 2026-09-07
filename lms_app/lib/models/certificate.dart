/// Certificate models — full detail + summary + public verify shape.
library;

class Certificate {
  final String id;
  final String certificateNumber;
  final String enrollmentId;
  final DateTime? issuedAt;
  final bool revoked;
  final DateTime? revokedAt;
  final String? revokedReason;

  // Enriched fields returned when the server sees a request from someone
  // allowed to know the names.
  final String? studentName;
  final String? studentId;
  final String? courseTitle;
  final String? courseId;

  const Certificate({
    required this.id,
    required this.certificateNumber,
    required this.enrollmentId,
    this.issuedAt,
    this.revoked = false,
    this.revokedAt,
    this.revokedReason,
    this.studentName,
    this.studentId,
    this.courseTitle,
    this.courseId,
  });

  factory Certificate.fromJson(Map<String, dynamic> j) => Certificate(
        id: j['id'] as String,
        certificateNumber: (j['certificateNumber'] ?? '') as String,
        enrollmentId: (j['enrollmentId'] ?? '') as String,
        issuedAt: j['issuedAt'] != null ? DateTime.tryParse(j['issuedAt'] as String) : null,
        revoked: (j['revoked'] ?? false) as bool,
        revokedAt: j['revokedAt'] != null ? DateTime.tryParse(j['revokedAt'] as String) : null,
        revokedReason: j['revokedReason'] as String?,
        studentName: j['studentName'] as String?,
        studentId: j['studentId'] as String?,
        courseTitle: j['courseTitle'] as String?,
        courseId: j['courseId'] as String?,
      );
}

/// Small blob embedded in `enrollment.certificate` on `/enrollments/mine`.
class CertificateSummary {
  final String id;
  final String certificateNumber;
  final DateTime? issuedAt;
  final bool revoked;

  const CertificateSummary({
    required this.id,
    required this.certificateNumber,
    this.issuedAt,
    this.revoked = false,
  });

  factory CertificateSummary.fromJson(Map<String, dynamic> j) => CertificateSummary(
        id: j['id'] as String,
        certificateNumber: (j['certificateNumber'] ?? '') as String,
        issuedAt: j['issuedAt'] != null ? DateTime.tryParse(j['issuedAt'] as String) : null,
        revoked: (j['revoked'] ?? false) as bool,
      );
}

/// Public verify response — restricted fields.
class VerifyResult {
  final String certificateNumber;
  final String? studentName;
  final String? courseTitle;
  final DateTime? issuedAt;
  final bool revoked;
  final DateTime? revokedAt;
  final String? revokedReason;

  const VerifyResult({
    required this.certificateNumber,
    this.studentName,
    this.courseTitle,
    this.issuedAt,
    this.revoked = false,
    this.revokedAt,
    this.revokedReason,
  });

  factory VerifyResult.fromJson(Map<String, dynamic> j) => VerifyResult(
        certificateNumber: (j['certificateNumber'] ?? '') as String,
        studentName: j['studentName'] as String?,
        courseTitle: j['courseTitle'] as String?,
        issuedAt: j['issuedAt'] != null ? DateTime.tryParse(j['issuedAt'] as String) : null,
        revoked: (j['revoked'] ?? false) as bool,
        revokedAt: j['revokedAt'] != null ? DateTime.tryParse(j['revokedAt'] as String) : null,
        revokedReason: j['revokedReason'] as String?,
      );
}
