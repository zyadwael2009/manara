import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/assignment.dart';
import '../services/api_service.dart';

/// Phase 18 — student "My assignments" hub. Cross-course, sorted by
/// due date. Filtered client-side into Past due / Open / Upcoming.
final myAssignmentsAllProvider =
    FutureProvider.autoDispose<List<MyAssignmentRow>>((ref) async {
  return ApiService.instance.myAssignmentsAll();
});
