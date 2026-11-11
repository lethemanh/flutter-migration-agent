// GENERATED FILE - DO NOT EDIT BY HAND.
// Compatibility helpers for @linagora/twake-mui ({{ mui_version }}).
import 'package:flutter/material.dart';
class TwakeMuiCompat {
  static const supportedAvatarColors = <String>[
{% for color in avatar_colors %}    '{{ color }}',
{% endfor %}  ];
  static const avatarGradients = <String, LinearGradient>{
{% for name, gradient in avatar_gradients.items() %}    '{{ name }}': LinearGradient(begin: Alignment({{ gradient.beginX }}, {{ gradient.beginY }}), end: Alignment({{ gradient.endX }}, {{ gradient.endY }}), colors: [Color(0xFF{{ gradient.colors[0][1:] }}), Color(0xFF{{ gradient.colors[1][1:] }})], stops: [{{ gradient.stops[0] }}, {{ gradient.stops[1] }}]),
{% endfor %}  };
  static LinearGradient avatarGradient(String color) => avatarGradients[color] ?? avatarGradients['sunrise']!;
  static String contactInitials(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((part) => part.isNotEmpty).toList();
    if (parts.isEmpty) return '';
    return '${parts.first[0]}${parts.length > 1 ? parts.last[0] : ''}'.toUpperCase();
  }

  static String? nameToColor(String? name) {
    if (name == null || name.isEmpty) return null;
    final sum = name.toUpperCase().runes.fold<int>(0, (total, rune) => total + rune);
    return supportedAvatarColors[sum % supportedAvatarColors.length];
  }

  static String getInitials(String? name, [String? email]) {
    if (name == null || name.isEmpty || name == email) {
      final localPart = (email ?? '').split('@').first;
      return localPart.length <= 2 ? localPart.toUpperCase() : localPart.substring(0, 2).toUpperCase();
    }
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.length == 1) return parts.first.length <= 2 ? parts.first.toUpperCase() : parts.first.substring(0, 2).toUpperCase();
    return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
  }
}
