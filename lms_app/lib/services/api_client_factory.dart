// Conditional-import shim so we can pick the right `http.Client` at compile
// time. Web uses `BrowserClient` with `withCredentials=true` (needed for
// cookie-based auth to travel cross-origin, though we primarily use
// `X-Session-Token` on web); native platforms use the default `http.Client`.
//
// Callers just `import 'api_client_factory.dart' show createApiClient;`.
export 'api_client_factory_stub.dart'
    if (dart.library.html) 'api_client_factory_web.dart';
