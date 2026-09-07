/// Phase 20 — server envelope for `POST /api/admin/users/import`.
library;

class BulkImportResult {
  final List<BulkImportRow> created;
  final List<BulkImportRow> updated;
  final List<BulkImportSkip> skipped;
  final List<BulkImportError> errors;
  final String notice;

  const BulkImportResult({
    this.created = const [],
    this.updated = const [],
    this.skipped = const [],
    this.errors = const [],
    this.notice = '',
  });

  int get totalTouched =>
      created.length + updated.length + skipped.length + errors.length;

  factory BulkImportResult.fromJson(Map<String, dynamic> j) => BulkImportResult(
        created: (j['created'] as List<dynamic>? ?? const [])
            .map((e) => BulkImportRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        updated: (j['updated'] as List<dynamic>? ?? const [])
            .map((e) => BulkImportRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        skipped: (j['skipped'] as List<dynamic>? ?? const [])
            .map((e) => BulkImportSkip.fromJson(e as Map<String, dynamic>))
            .toList(),
        errors: (j['errors'] as List<dynamic>? ?? const [])
            .map((e) => BulkImportError.fromJson(e as Map<String, dynamic>))
            .toList(),
        notice: (j['notice'] as String?) ?? '',
      );
}

class BulkImportRow {
  final int row;
  final String email;
  final String id;

  /// Present on created rows only. Every imported user now gets their own
  /// random password instead of the whole school sharing one literal, and
  /// this response is the only place it is ever readable -- the server keeps
  /// just the hash.
  final String? temporaryPassword;

  const BulkImportRow({
    required this.row,
    required this.email,
    required this.id,
    this.temporaryPassword,
  });

  factory BulkImportRow.fromJson(Map<String, dynamic> j) => BulkImportRow(
        row: (j['row'] as num?)?.toInt() ?? 0,
        email: (j['email'] as String?) ?? '',
        id: (j['id'] as String?) ?? '',
        temporaryPassword: j['temporaryPassword'] as String?,
      );
}

class BulkImportSkip {
  final int row;
  final String email;
  final String reason;
  const BulkImportSkip({required this.row, required this.email, required this.reason});
  factory BulkImportSkip.fromJson(Map<String, dynamic> j) => BulkImportSkip(
        row: (j['row'] as num?)?.toInt() ?? 0,
        email: (j['email'] as String?) ?? '',
        reason: (j['reason'] as String?) ?? '',
      );
}

class BulkImportError {
  final int row;
  final String error;
  const BulkImportError({required this.row, required this.error});
  factory BulkImportError.fromJson(Map<String, dynamic> j) => BulkImportError(
        row: (j['row'] as num?)?.toInt() ?? 0,
        error: (j['error'] as String?) ?? '',
      );
}
