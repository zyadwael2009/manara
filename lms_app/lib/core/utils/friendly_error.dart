import '../../services/api_service.dart';

/// Turn any thrown value into a user-facing string.
///
/// Introduced during the Phase 9 audit fix pass (F14). The CORS bug that
/// surfaced "ApiException(0): ClientException: Failed to fetch, uri=…" to
/// end users was the flag — raw `.toString()` should never reach a
/// screen. Every `Text(e.toString())` in error paths should route through
/// `friendlyError(e)` instead.
String friendlyError(Object? e) {
  if (e == null) return 'Something went wrong.';
  if (e is SessionExpiredException) {
    return 'Your session expired. Please sign in again.';
  }
  if (e is ApiException) {
    if (e.statusCode == 0) {
      // Network/CORS/DNS — anything the browser refused to send.
      return "We couldn't reach the server. Check your connection.";
    }
    if (e.isForbidden) {
      return "You don't have access to this.";
    }
    if (e.statusCode == 404) {
      return "Not found.";
    }
    if (e.statusCode >= 500) {
      return 'The server hit an unexpected error. Try again in a moment.';
    }
    // Everything else — trust the server's own error string, it went
    // through utils/validation.py or a `jsonify({"error": …})` and is
    // meant to be read.
    return e.message;
  }
  return 'Something went wrong.';
}
