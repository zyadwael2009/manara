class Grade {
  final String id;
  final String name;
  final String? sectionId;
  final String? sectionName;
  final int orderIndex;

  const Grade({
    required this.id,
    required this.name,
    this.sectionId,
    this.sectionName,
    this.orderIndex = 0,
  });

  factory Grade.fromJson(Map<String, dynamic> j) => Grade(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        sectionId: j['sectionId'] as String?,
        sectionName: j['sectionName'] as String?,
        orderIndex: (j['orderIndex'] ?? 0) as int,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'sectionId': sectionId,
        'sectionName': sectionName,
        'orderIndex': orderIndex,
      };
}
