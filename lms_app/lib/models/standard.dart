// Phase 32 · T3 — curriculum standards + student mastery.

class Standard {
  final String id;
  final String code;
  final String name;
  final String description;
  final String? subject;
  const Standard({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    this.subject,
  });
  factory Standard.fromJson(Map<String, dynamic> j) => Standard(
        id: j['id'] as String,
        code: (j['code'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        description: (j['description'] as String?) ?? '',
        subject: j['subject'] as String?,
      );
}

/// Mastery-view row returned by `GET /api/students/<sid>/standards-mastery`.
class StandardMastery {
  final String standardId;
  final String code;
  final String name;
  final String? subject;
  final double? masteryPercent;
  final String band; // mastered | meeting | progressing | beginning | not-assessed
  final int sampleSize;

  const StandardMastery({
    required this.standardId,
    required this.code,
    required this.name,
    required this.band,
    required this.sampleSize,
    this.subject,
    this.masteryPercent,
  });

  factory StandardMastery.fromJson(Map<String, dynamic> j) => StandardMastery(
        standardId: (j['standardId'] as String?) ?? '',
        code: (j['code'] as String?) ?? '',
        name: (j['name'] as String?) ?? '',
        subject: j['subject'] as String?,
        masteryPercent: (j['masteryPercent'] as num?)?.toDouble(),
        band: (j['band'] as String?) ?? 'not-assessed',
        sampleSize: (j['sampleSize'] as num?)?.toInt() ?? 0,
      );
}
