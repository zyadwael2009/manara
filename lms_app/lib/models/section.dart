class Section {
  final String id;
  final String name;
  final int orderIndex;

  const Section({required this.id, required this.name, required this.orderIndex});

  factory Section.fromJson(Map<String, dynamic> j) => Section(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        orderIndex: (j['orderIndex'] ?? 0) as int,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'orderIndex': orderIndex,
      };
}
