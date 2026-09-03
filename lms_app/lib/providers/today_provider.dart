import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/today.dart';
import '../services/api_service.dart';

/// Phase 18 — student "Today" landing (`GET /api/students/today`). Powers
/// the inline TodayCard at the top of My classes.
final todayProvider = FutureProvider.autoDispose<TodayView>((ref) async {
  return ApiService.instance.getToday();
});
