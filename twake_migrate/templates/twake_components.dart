// GENERATED FILE - DO NOT EDIT BY HAND.
// Source: @linagora/twake-mui ({{ mui_version }}) 1-to-1 Flutter widget equivalents
import 'package:flutter/material.dart';
import '../tokens/twake_palette.dart';
import '../tokens/twake_radius.dart';
import '../tokens/twake_spacing.dart';
import '../tokens/twake_typography.dart';
import '../icons/twake_icons.dart';
import 'twake_mui_compat.dart';

class TwakeLayout extends StatelessWidget {
  final Widget? drawer;
  final PreferredSizeWidget? topBar;
  final Widget body;
  final Widget? floatingActionButton;
  final GlobalKey<ScaffoldState>? scaffoldKey;

  const TwakeLayout({
    super.key,
    this.drawer,
    this.topBar,
    required this.body,
    this.floatingActionButton,
    this.scaffoldKey,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: scaffoldKey,
      drawer: drawer,
      appBar: topBar,
      body: SafeArea(child: body),
      floatingActionButton: floatingActionButton,
    );
  }
}

class TwakeAvatar extends StatelessWidget {
  final String displayName;
  final double radius;
  final TextStyle? initialsStyle;
  final Widget? child;

  const TwakeAvatar({
    super.key,
    required this.displayName,
    this.radius = 16.0,
    this.initialsStyle,
    this.child,
  });

  String get _initials => TwakeMuiCompat.contactInitials(displayName);

  @override
  Widget build(BuildContext context) {
    return CircleAvatar(
      radius: radius,
      backgroundColor: TwakePalette.primary500,
      foregroundColor: TwakePalette.commonWhite,
      child: SizedBox.expand(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: TwakeMuiCompat.avatarGradient(TwakeMuiCompat.nameToColor(displayName) ?? 'sunrise'),
            shape: BoxShape.circle,
          ),
          child: Center(child: child ?? Text(_initials, style: (initialsStyle ?? TwakeTypography.caption).copyWith(color: TwakePalette.commonWhite))),
        ),
      ),
    );
  }
}

class TwakeSearchBar extends StatelessWidget {
  final String placeholder;
  final ValueChanged<String>? onChanged;
  final TextEditingController? controller;
  final FocusNode? focusNode;

  const TwakeSearchBar({
    super.key,
    required this.placeholder,
    this.onChanged,
    this.controller,
    this.focusNode,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(height: TwakeSpacing.u2Half, child: TextField(
      style: TwakeTypography.body2,
      controller: controller,
      focusNode: focusNode,
      onChanged: onChanged,
      decoration: InputDecoration(
        hintText: placeholder,
        hintStyle: TwakeTypography.body2.copyWith(color: Theme.of(context).disabledColor),
        isDense: true,
        filled: true,
        fillColor: Theme.of(context).scaffoldBackgroundColor,
        prefixIconConstraints: const BoxConstraints(minWidth: TwakeSpacing.u2Half, minHeight: TwakeSpacing.u2Half),
        prefixIcon: const SizedBox(width: TwakeSpacing.u2Half, height: TwakeSpacing.u2Half,
          child: Center(child: TwakeIcon(icon: TwakeIcons.Magnifier, size: TwakeSpacing.m))),
        border: const OutlineInputBorder(borderRadius: TwakeRadius.borderPill),
        enabledBorder: OutlineInputBorder(borderRadius: TwakeRadius.borderPill, borderSide: BorderSide(color: Theme.of(context).dividerColor)),
        focusedBorder: OutlineInputBorder(borderRadius: TwakeRadius.borderPill, borderSide: BorderSide(color: Theme.of(context).colorScheme.primary)),
        contentPadding: TwakeSpacing.ph1,
      ),
    ));
  }
}

class TwakeEmptyState extends StatelessWidget {
  final TwakeIconData? illustration;
  final String title;
  final String? subtitle;
  final Widget? action;

  const TwakeEmptyState({
    super.key,
    this.illustration,
    required this.title,
    this.subtitle,
    this.action,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: TwakeSpacing.p2,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (illustration != null)
              TwakeIcon(icon: illustration!, size: TwakeSpacing.xxl),
            const SizedBox(height: TwakeSpacing.m),
            Text(title, style: TwakeTypography.h5, textAlign: TextAlign.center),
            if (subtitle != null) ...[
              const SizedBox(height: TwakeSpacing.xs),
              Text(subtitle!, style: TwakeTypography.body2, textAlign: TextAlign.center),
            ],
            if (action != null) ...[
              const SizedBox(height: TwakeSpacing.m),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

class TwakeSegmentedTabs<T> extends StatelessWidget {
  final T value;
  final Map<T, String> tabs;
  final ValueChanged<T> onChanged;

  const TwakeSegmentedTabs({
    super.key,
    required this.value,
    required this.tabs,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isDark ? TwakePalette.darkBackgroundContrast : TwakePalette.lightBackgroundContrast,
        borderRadius: TwakeRadius.borderPill,
      ),
      child: Padding(
        padding: const EdgeInsets.all(1),
        child: Row(children: tabs.entries.map((entry) => Expanded(
          child: Material(
            color: entry.key == value ? Theme.of(context).colorScheme.surface : Colors.transparent,
            elevation: entry.key == value ? 1 : 0,
            borderRadius: TwakeRadius.borderPill,
            child: Semantics(
              selected: entry.key == value,
              child: TextButton(
                style: TextButton.styleFrom(
                  foregroundColor: Theme.of(context).colorScheme.onSurface,
                  textStyle: TwakeTypography.body2,
                  minimumSize: const Size(0, 38),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderPill),
                ),
                onPressed: () => onChanged(entry.key),
                child: Text(entry.value, textAlign: TextAlign.center),
              ),
            ),
          ),
        )).toList()),
      ),
    );
  }
}
