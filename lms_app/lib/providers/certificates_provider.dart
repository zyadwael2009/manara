import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';

final myCertificatesProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.listMyCertificates();
});

final certificateProvider =
    FutureProvider.autoDispose.family((ref, String id) async {
  return ApiService.instance.getCertificate(id);
});
