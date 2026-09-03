class SchoolYear {
  final String id;
  final String name;
  final String? startDate;
  final String? endDate;
  final bool isCurrent;

  const SchoolYear({
    required this.id,
    required this.name,
    this.startDate,
    this.endDate,
    this.isCurrent = false,
  });

  factory SchoolYear.fromJson(Map<String, dynamic> j) => SchoolYear(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        startDate: j['startDate'] as String?,
        endDate: j['endDate'] as String?,
        isCurrent: (j['isCurrent'] ?? false) as bool,
      );
}
