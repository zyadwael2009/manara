// Phase 28 — fees + payments.

class FeeItem {
  final String id;
  final String studentId;
  final String label;
  final double amount;
  final String currency;
  final DateTime? dueDate;
  final String? notes;
  final double paidAmount;
  final double balance;
  final List<FeePayment> payments;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const FeeItem({
    required this.id,
    required this.studentId,
    required this.label,
    required this.amount,
    required this.currency,
    required this.paidAmount,
    required this.balance,
    required this.payments,
    this.dueDate,
    this.notes,
    this.createdAt,
    this.updatedAt,
  });

  bool get isFullyPaid => balance <= 0.001;

  factory FeeItem.fromJson(Map<String, dynamic> j) {
    final raw = (j['payments'] as List?) ?? const [];
    return FeeItem(
      id: j['id'] as String,
      studentId: (j['studentId'] as String?) ?? '',
      label: (j['label'] as String?) ?? '',
      amount: (j['amount'] as num?)?.toDouble() ?? 0.0,
      currency: (j['currency'] as String?) ?? 'USD',
      dueDate: j['dueDate'] == null
          ? null
          : DateTime.tryParse('${j['dueDate']}T00:00:00'),
      notes: j['notes'] as String?,
      paidAmount: (j['paidAmount'] as num?)?.toDouble() ?? 0.0,
      balance: (j['balance'] as num?)?.toDouble() ?? 0.0,
      payments: raw
          .whereType<Map<String, dynamic>>()
          .map(FeePayment.fromJson)
          .toList(),
      createdAt: j['createdAt'] == null
          ? null
          : DateTime.tryParse(j['createdAt'] as String),
      updatedAt: j['updatedAt'] == null
          ? null
          : DateTime.tryParse(j['updatedAt'] as String),
    );
  }
}

class FeePayment {
  final String id;
  final String feeItemId;
  final double amount;
  final DateTime? paidAt;
  final String? method;
  final String? note;

  const FeePayment({
    required this.id,
    required this.feeItemId,
    required this.amount,
    this.paidAt,
    this.method,
    this.note,
  });

  factory FeePayment.fromJson(Map<String, dynamic> j) => FeePayment(
        id: j['id'] as String,
        feeItemId: (j['feeItemId'] as String?) ?? '',
        amount: (j['amount'] as num?)?.toDouble() ?? 0.0,
        paidAt: j['paidAt'] == null
            ? null
            : DateTime.tryParse(j['paidAt'] as String),
        method: j['method'] as String?,
        note: j['note'] as String?,
      );
}

/// The `GET /api/students/<id>/fees` and `GET /api/fees/mine` envelope.
class FeeStatement {
  final String? studentId;
  final List<FeeItem> items;
  final double totalAmount;
  final double totalPaid;
  final double totalBalance;
  const FeeStatement({
    required this.items,
    required this.totalAmount,
    required this.totalPaid,
    required this.totalBalance,
    this.studentId,
  });

  factory FeeStatement.fromJson(Map<String, dynamic> j) {
    final raw = (j['items'] as List?) ?? const [];
    return FeeStatement(
      studentId: j['studentId'] as String?,
      items: raw
          .whereType<Map<String, dynamic>>()
          .map(FeeItem.fromJson)
          .toList(),
      totalAmount: (j['totalAmount'] as num?)?.toDouble() ?? 0.0,
      totalPaid: (j['totalPaid'] as num?)?.toDouble() ?? 0.0,
      totalBalance: (j['totalBalance'] as num?)?.toDouble() ?? 0.0,
    );
  }
}
