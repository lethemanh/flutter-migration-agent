// GENERATED FILE - DO NOT EDIT BY HAND.
// Source: @linagora/twake-utils (twake-ts-utils/src/uriTemplates)

class UriTemplateContext {
  final String localpart;
  final String workplaceFqdn;
  final String workplaceFqdnFallback;
  final String target;

  const UriTemplateContext({
    this.localpart = '',
    this.workplaceFqdn = '',
    this.workplaceFqdnFallback = '',
    this.target = '',
  });
}

class TwakeUtils {
  static String encodeDavSegment(String value) => Uri.encodeComponent(value)
    .replaceAllMapped(RegExp(r"[!*']"), (m) => '%${m[0]!.codeUnitAt(0).toRadixString(16).toUpperCase()}')
    .replaceAll('%40', '@').replaceAll('%3A', ':');

  static String _resolveWorkplaceFqdn(
    String workplaceFqdn,
    String localpart,
    String fallback,
  ) {
    if (workplaceFqdn.isNotEmpty) return workplaceFqdn;
    if (fallback.isEmpty) return '';
    return fallback.replaceAll('{localpart}', localpart);
  }

  static String resolveUriTemplate(
    String template, [
    UriTemplateContext context = const UriTemplateContext(),
  ]) {
    final effectiveFqdn = _resolveWorkplaceFqdn(
      context.workplaceFqdn,
      context.localpart,
      context.workplaceFqdnFallback,
    );
    final parts = effectiveFqdn.split('.');
    final fqdnLocalpart = parts.isNotEmpty ? parts.first : '';
    final fqdnDomain = parts.length > 1 ? parts.sublist(1).join('.') : '';

    final values = <String, String>{
      'localpart': context.localpart,
      'workplaceFqdn': effectiveFqdn,
      'workplaceFqdn.localpart': fqdnLocalpart,
      'workplaceFqdn.domain': fqdnDomain,
      'target': context.target,
    };

    return template.replaceAllMapped(RegExp(r'\{([^}]+)\}'), (match) {
      final key = match.group(1)!.trim();
      return values.containsKey(key) ? values[key]! : match.group(0)!;
    });
  }

  static String? resolveMailSpaUrl(
    String template, [
    UriTemplateContext context = const UriTemplateContext(),
  ]) {
    if (template.isEmpty) return null;
    return resolveUriTemplate(template, context);
  }

  static List<String> _addresses(Object addresses) => addresses is String ? [addresses] : List<String>.from(addresses as Iterable);

  static String? buildMailtoUri(Object addresses) {
    final valid = _addresses(addresses).map((a) => a.replaceFirst(RegExp(r'^mailto:', caseSensitive: false), '').trim())
      .where((a) => !RegExp(r'[?&,;#\s]').hasMatch(a) && RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(a))
      .map((a) => Uri.encodeComponent(a.toLowerCase()).replaceAll('%40', '@')).toList();
    return valid.isEmpty ? null : 'mailto:${valid.join(',')}';
  }

  static String? buildMailComposerUrl(String mailSpaUrl, Object addresses, {String? subject}) {
    final mailto = buildMailtoUri(addresses);
    if (mailto == null) return null;
    final extra = subject == null ? '' : '&subject=${Uri.encodeComponent(subject)}';
    return '$mailSpaUrl/mailto/?uri=${Uri.encodeComponent(mailto)}$extra';
  }

  static String? resolveChatSpaUrl(
    String template, [
    UriTemplateContext context = const UriTemplateContext(),
  ]) {
    if (template.isEmpty) return null;
    return resolveUriTemplate(template, context);
  }

  static String? resolveCalendarSpaUrl(
    String template, [
    UriTemplateContext context = const UriTemplateContext(),
  ]) {
    if (template.isEmpty) return null;
    return resolveUriTemplate(template, context);
  }

  static String? buildCalendarEventUrl(String calendarSpaUrl, Object addresses) {
    final valid = _addresses(addresses).map((a) => a.trim())
      .where((a) => !RegExp(r'[?&=#]').hasMatch(a) && RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(a))
      .map(Uri.encodeComponent).toList();
    return valid.isEmpty ? null : '$calendarSpaUrl/newEvent?attendee=${valid.join(',')}';
  }
}
