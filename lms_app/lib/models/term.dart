class Term {
  final String id;
  final String schoolYearId;
  final String? schoolYearName;
  final String name;
  final String? startDate;
  final String? endDate;
  final int orderIndex;
  final bool isLocked;
  final String? lockedAt;

  const Term({
    required this.id,
    required this.schoolYearId,
    required this.name,
    this.schoolYearName,
    this.startDate,
    this.endDate,
    this.orderIndex = 0,
    this.isLocked = false,
    this.lockedAt,
  });

  factory Term.fromJson(Map<String, dynamic> j) => Term(
        id: j['id'] as String,
        schoolYearId: (j['schoolYearId'] ?? '') as String,
        schoolYearName: j['schoolYearName'] as String?,
        name: (j['name'] ?? '') as String,
        startDate: j['startDate'] as String?,
        endDate: j['endDate'] as String?,
        orderIndex: (j['orderIndex'] ?? 0) as int,
        isLocked: (j['isLocked'] ?? false) as bool,
        lockedAt: j['lockedAt'] as String?,
      );
}
