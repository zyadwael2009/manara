import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/storage_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Prefs must be ready before any provider reads a cached session token.
  await StorageService.instance.init();
  runApp(const ProviderScope(child: LmsApp()));
}
