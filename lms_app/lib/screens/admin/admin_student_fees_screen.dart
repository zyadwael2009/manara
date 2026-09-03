import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/fees.dart';
import '../../services/api_service.dart';

/// Phase 28 — admin view of one student's fees.
///
/// Adds admin-only write actions on top of the shared read layout:
///   * Add fee item.
///   * Log payment against any fee (with a partial-payment guard —
///     the server also refuses > outstanding balance, but the client
///     blocks it inline so the UX is snappy).
///   * Delete fee item (with confirm).
///
/// The receipt PDF button uses the same endpoint the student sees.
class AdminStudentFeesScreen extends ConsumerStatefulWidget {
  final String studentId;
  final String studentName;
  const AdminStudentFeesScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });
  @override
  ConsumerState<AdminStudentFeesScreen> createState() =>
      _AdminStudentFeesScreenState();
}

class _AdminStudentFeesScreenState
    extends ConsumerState<AdminStudentFeesScreen> {
  Future<FeeStatement>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<FeeStatement> _load() =>
      ApiService.instance.listStudentFees(widget.studentId);

  void _reload() => setState(() => _future = _load());

  Future<void> _addFee() async {
    final res = await showDialog<_NewFee>(
      context: context,
      builder: (d) => const _NewFeeDialog(),
    );
    if (res == null) return;
    try {
      await ApiService.instance.createFee(
        widget.studentId,
        label: res.label,
        amount: res.amount,
        currency: res.currency,
        dueDate: res.dueDate,
        notes: res.notes,
      );
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  Future<void> _logPayment(FeeItem fee) async {
    final res = await showDialog<_NewPayment>(
      context: context,
      builder: (d) => _NewPaymentDialog(maxAmount: fee.balance),
    );
    if (res == null) return;
    try {
      await ApiService.instance.logFeePayment(
        fee.id,
        amount: res.amount,
        method: res.method,
        note: res.note,
      );
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  Future<void> _deleteFee(FeeItem fee) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Delete this fee?'),
        content: Text(
          'This removes "${fee.label}" and every payment logged against it. '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(d, false),
              child: const Text('Cancel')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.pop(d, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.instance.deleteFee(fee.id);
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.studentName} · Fees',
            style: AppTextStyles.h3(context)),
        actions: [
          IconButton(
            tooltip: 'Statement PDF',
            icon: const Icon(Icons.picture_as_pdf_outlined),
            onPressed: () => launchUrl(
              Uri.parse(ApiService.instance.feesPdfUrl(widget.studentId)),
              mode: LaunchMode.platformDefault,
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addFee,
        icon: const Icon(Icons.add),
        label: const Text('Add fee'),
      ),
      body: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<FeeStatement>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return ListView(children: [
                const SizedBox(height: 80),
                Center(child: Text(friendlyError(snap.error!))),
              ]);
            }
            final s = snap.data!;
            if (s.items.isEmpty) {
              return ListView(children: const [
                EmptyState(
                  icon: Icons.receipt_long_outlined,
                  title: 'No fees yet',
                  message:
                      'Tap Add fee to create the first line item for '
                      'this student.',
                ),
              ]);
            }
            final fmt = NumberFormat.currency(symbol: '', decimalDigits: 2);
            return ListView(
              padding: const EdgeInsets.all(AppSpacing.xl),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: Row(children: [
                      Expanded(
                          child: _kv(context, 'Billed',
                              fmt.format(s.totalAmount))),
                      Expanded(
                          child: _kv(context, 'Paid',
                              fmt.format(s.totalPaid))),
                      Expanded(
                          child: _kv(context, 'Balance',
                              fmt.format(s.totalBalance),
                              color: s.totalBalance > 0
                                  ? AppColors.danger
                                  : AppColors.success)),
                    ]),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                for (final f in s.items) _AdminFeeCard(
                  fee: f,
                  onLogPayment: () => _logPayment(f),
                  onDelete: () => _deleteFee(f),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _kv(BuildContext context, String label, String value,
      {Color? color}) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: AppTextStyles.micro(context,
                  color: AppColors.textMuted)),
          Text(value,
              style: AppTextStyles.bodyStrong(context, color: color)),
        ],
      );
}

class _AdminFeeCard extends StatelessWidget {
  final FeeItem fee;
  final VoidCallback onLogPayment;
  final VoidCallback onDelete;
  const _AdminFeeCard({
    required this.fee,
    required this.onLogPayment,
    required this.onDelete,
  });
  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.currency(symbol: '', decimalDigits: 2);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(
                child: Text(fee.label,
                    style: AppTextStyles.bodyStrong(context)),
              ),
              IconButton(
                tooltip: 'Delete',
                onPressed: onDelete,
                icon: const Icon(Icons.delete_outline_rounded,
                    color: AppColors.textMuted),
                visualDensity: VisualDensity.compact,
              ),
            ]),
            Row(children: [
              Text('${fmt.format(fee.amount)} billed',
                  style: AppTextStyles.body(context)),
              const SizedBox(width: AppSpacing.sm),
              Text('${fmt.format(fee.paidAmount)} paid',
                  style: AppTextStyles.body(context,
                      color: AppColors.textSecondary)),
              const SizedBox(width: AppSpacing.sm),
              Text('${fmt.format(fee.balance)} left',
                  style: AppTextStyles.body(context,
                          color: fee.balance > 0
                              ? AppColors.danger
                              : AppColors.success)
                      .copyWith(fontWeight: FontWeight.w700)),
            ]),
            if (fee.dueDate != null)
              Text('Due ${DateFormat.yMMMd().format(fee.dueDate!)}',
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
            const SizedBox(height: AppSpacing.sm),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: OutlinedButton.icon(
                onPressed: fee.balance <= 0.001 ? null : onLogPayment,
                icon: const Icon(Icons.payments_outlined, size: 16),
                label: const Text('Log payment'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// Dialogs — Add fee + Log payment
// ============================================================================
class _NewFee {
  final String label;
  final double amount;
  final String currency;
  final DateTime? dueDate;
  final String? notes;
  _NewFee(this.label, this.amount, this.currency, this.dueDate, this.notes);
}

class _NewFeeDialog extends StatefulWidget {
  const _NewFeeDialog();
  @override
  State<_NewFeeDialog> createState() => _NewFeeDialogState();
}

class _NewFeeDialogState extends State<_NewFeeDialog> {
  final _label = TextEditingController();
  final _amount = TextEditingController();
  final _currency = TextEditingController(text: 'USD');
  final _notes = TextEditingController();
  DateTime? _due;
  @override
  void dispose() {
    _label.dispose();
    _amount.dispose();
    _currency.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add fee'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: _label,
            maxLength: 200,
            decoration: const InputDecoration(labelText: 'Label'),
          ),
          TextField(
            controller: _amount,
            keyboardType:
                const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Amount'),
          ),
          TextField(
            controller: _currency,
            maxLength: 8,
            decoration: const InputDecoration(labelText: 'Currency'),
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            Expanded(
              child: Text(_due == null
                  ? 'No due date'
                  : 'Due ${DateFormat.yMMMd().format(_due!)}'),
            ),
            TextButton(
              onPressed: () async {
                final picked = await showDatePicker(
                  context: context,
                  initialDate: _due ?? DateTime.now(),
                  firstDate: DateTime.now().subtract(const Duration(days: 30)),
                  lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
                );
                if (picked != null) setState(() => _due = picked);
              },
              child: const Text('Pick date'),
            ),
          ]),
          TextField(
            controller: _notes,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Notes (optional)'),
          ),
        ]),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel')),
        ElevatedButton(
          onPressed: () {
            final amt = double.tryParse(_amount.text.trim());
            if (_label.text.trim().isEmpty || amt == null || amt < 0) return;
            Navigator.pop(
                context,
                _NewFee(
                  _label.text.trim(),
                  amt,
                  _currency.text.trim().isEmpty
                      ? 'USD'
                      : _currency.text.trim(),
                  _due,
                  _notes.text.trim().isEmpty ? null : _notes.text.trim(),
                ));
          },
          child: const Text('Add'),
        ),
      ],
    );
  }
}

class _NewPayment {
  final double amount;
  final String? method;
  final String? note;
  _NewPayment(this.amount, this.method, this.note);
}

class _NewPaymentDialog extends StatefulWidget {
  final double maxAmount;
  const _NewPaymentDialog({required this.maxAmount});
  @override
  State<_NewPaymentDialog> createState() => _NewPaymentDialogState();
}

class _NewPaymentDialogState extends State<_NewPaymentDialog> {
  final _amount = TextEditingController();
  final _method = TextEditingController();
  final _note = TextEditingController();
  @override
  void initState() {
    super.initState();
    _amount.text = widget.maxAmount.toStringAsFixed(2);
  }

  @override
  void dispose() {
    _amount.dispose();
    _method.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Log payment'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('Outstanding: ${widget.maxAmount.toStringAsFixed(2)}',
              style: AppTextStyles.caption(context,
                  color: AppColors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            controller: _amount,
            keyboardType:
                const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Amount'),
          ),
          TextField(
            controller: _method,
            maxLength: 40,
            decoration: const InputDecoration(
                labelText: 'Method (cash, card, bank…)'),
          ),
          TextField(
            controller: _note,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Note (optional)'),
          ),
        ]),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel')),
        ElevatedButton(
          onPressed: () {
            final amt = double.tryParse(_amount.text.trim());
            if (amt == null || amt <= 0) return;
            // Client-side guard — server also refuses > balance.
            if (amt > widget.maxAmount + 0.001) return;
            Navigator.pop(
                context,
                _NewPayment(
                  amt,
                  _method.text.trim().isEmpty ? null : _method.text.trim(),
                  _note.text.trim().isEmpty ? null : _note.text.trim(),
                ));
          },
          child: const Text('Log'),
        ),
      ],
    );
  }
}
