import 'package:http/browser_client.dart';
import 'package:http/http.dart' as http;

/// Web factory: BrowserClient with `withCredentials=true` so browser cookies
/// travel cross-origin. We still rely on `X-Session-Token` for auth on web
/// (belt-and-suspenders), but leaving cookies enabled lets a same-origin
/// deploy work with the cookie session too.
http.Client createApiClient() {
  final c = BrowserClient();
  c.withCredentials = true;
  return c;
}
