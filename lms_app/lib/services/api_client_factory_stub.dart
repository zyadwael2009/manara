import 'package:http/http.dart' as http;

/// Native / non-web factory: a plain `http.Client`.
http.Client createApiClient() => http.Client();
