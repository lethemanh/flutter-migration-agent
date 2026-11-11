// GENERATED FILE - DO NOT EDIT BY HAND.
// Source: @linagora/twake-mui ({{ mui_version }}) & @linagora/twake-css ({{ css_version }})
import 'package:flutter/material.dart';
import '../tokens/twake_palette.dart';
import '../tokens/twake_typography.dart';
import '../tokens/twake_radius.dart';

class TwakeTheme {
  static ThemeData light() {
    final textTheme = TwakeTypography.toTextTheme(
      TwakePalette.lightTextPrimary,
      TwakePalette.lightTextSecondary,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: TwakePalette.lightBackgroundDefault,
      dividerColor: TwakePalette.lightDivider,
      fontFamily: TwakeTypography.fontFamily,
      disabledColor: TwakePalette.lightTextDisabled,
      iconTheme: const IconThemeData(color: TwakePalette.lightTextIcon),
      appBarTheme: AppBarTheme(
        backgroundColor: TwakePalette.lightBackgroundDefault,
        foregroundColor: TwakePalette.lightTextPrimary,
        surfaceTintColor: TwakePalette.lightBackgroundDefault,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: TwakeTypography.body1.copyWith(fontWeight: FontWeight.w700, color: TwakePalette.lightTextPrimary),
      ),
      filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
        textStyle: TwakeTypography.button,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        minimumSize: const Size(64, {{ button_height }}),
        padding: const EdgeInsets.symmetric(horizontal: {{ button_horizontal }}, vertical: {{ button_vertical }}),
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderButton),
        elevation: 0,
      )),
      textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(
        minimumSize: const Size(64, 40),
        textStyle: TwakeTypography.button,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderButton),
      )),
      outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(
        minimumSize: const Size(64, 40),
        textStyle: TwakeTypography.button,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderButton),
      )),
      inputDecorationTheme: InputDecorationTheme(
        border: const OutlineInputBorder(borderRadius: TwakeRadius.borderInput),
        enabledBorder: const OutlineInputBorder(borderRadius: TwakeRadius.borderInput,
          borderSide: BorderSide(color: TwakePalette.lightBorderMain)),
        focusedBorder: const OutlineInputBorder(borderRadius: TwakeRadius.borderInput,
          borderSide: BorderSide(color: TwakePalette.lightPrimaryMain)),
        labelStyle: TwakeTypography.body1.copyWith(color: TwakePalette.lightTextSecondary),
        hintStyle: TwakeTypography.body1.copyWith(color: TwakePalette.lightTextSecondary),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: TwakePalette.lightBackgroundPaper,
        surfaceTintColor: TwakePalette.lightBackgroundPaper,
        shape: RoundedRectangleBorder(borderRadius: TwakeRadius.borderShapeDefault),
      ),
      drawerTheme: const DrawerThemeData(
        backgroundColor: TwakePalette.lightBackgroundPaper,
        surfaceTintColor: TwakePalette.lightBackgroundPaper,
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: TwakePalette.lightBackgroundPaper,
        surfaceTintColor: TwakePalette.lightBackgroundPaper,
        textStyle: TwakeTypography.body1.copyWith(color: TwakePalette.lightTextPrimary),
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderInput),
      ),
      listTileTheme: ListTileThemeData(
        titleTextStyle: TwakeTypography.body1.copyWith(color: TwakePalette.lightTextPrimary),
        subtitleTextStyle: TwakeTypography.body2.copyWith(color: TwakePalette.lightTextSecondary),
        iconColor: TwakePalette.lightTextIcon,
        selectedTileColor: TwakePalette.grey900.withValues(alpha: 0.08),
        selectedColor: TwakePalette.lightTextPrimary,
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: TwakePalette.lightPrimaryLight,
        foregroundColor: TwakePalette.lightPrimaryDark,
        shape: RoundedRectangleBorder(borderRadius: TwakeRadius.borderFab),
      ),
      colorScheme: const ColorScheme.light(
        primary: TwakePalette.lightPrimaryMain,
        onPrimary: TwakePalette.lightPrimaryContrastText,
        secondary: TwakePalette.lightSecondaryMain,
        onSecondary: TwakePalette.secondaryContrastText,
        primaryContainer: TwakePalette.lightPrimaryLight,
        onPrimaryContainer: TwakePalette.lightPrimaryDark,
        secondaryContainer: TwakePalette.lightBackgroundContrast,
        onSecondaryContainer: TwakePalette.lightTextPrimary,
        onError: TwakePalette.errorContrastText,
        onSurfaceVariant: TwakePalette.lightTextSecondary,
        surfaceContainerLowest: TwakePalette.lightBackgroundPaper,
        surfaceContainerLow: TwakePalette.lightBackgroundPaper,
        surfaceContainer: TwakePalette.lightBackgroundPaper,
        surfaceContainerHigh: TwakePalette.lightBackgroundPaper,
        surfaceContainerHighest: TwakePalette.lightBackgroundContrast,
        surfaceTint: TwakePalette.lightBackgroundPaper,
        outline: TwakePalette.lightBorderMain,
        outlineVariant: TwakePalette.lightDivider,
        error: TwakePalette.lightErrorMain,
        surface: TwakePalette.lightBackgroundPaper,
        onSurface: TwakePalette.lightTextPrimary,
      ),
      textTheme: textTheme,
      cardTheme: const CardThemeData(
        color: TwakePalette.lightBackgroundPaper,
        shape: RoundedRectangleBorder(borderRadius: TwakeRadius.borderMd),
      ),
    );
  }

  static ThemeData dark() {
    final textTheme = TwakeTypography.toTextTheme(
      TwakePalette.darkTextPrimary,
      TwakePalette.darkTextSecondary,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: TwakePalette.darkBackgroundDefault,
      dividerColor: TwakePalette.darkDivider,
      fontFamily: TwakeTypography.fontFamily,
      disabledColor: TwakePalette.darkTextDisabled,
      iconTheme: const IconThemeData(color: TwakePalette.darkTextIcon),
      appBarTheme: AppBarTheme(
        backgroundColor: TwakePalette.darkBackgroundDefault,
        foregroundColor: TwakePalette.darkTextPrimary,
        surfaceTintColor: TwakePalette.darkBackgroundDefault,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: TwakeTypography.body1.copyWith(fontWeight: FontWeight.w700, color: TwakePalette.darkTextPrimary),
      ),
      filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
        textStyle: TwakeTypography.button,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        minimumSize: const Size(64, {{ button_height }}),
        padding: const EdgeInsets.symmetric(horizontal: {{ button_horizontal }}, vertical: {{ button_vertical }}),
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderButton),
        elevation: 0,
      )),
      textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(
        minimumSize: const Size(64, 40),
        textStyle: TwakeTypography.button,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderButton),
      )),
      outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(
        minimumSize: const Size(64, 40),
        textStyle: TwakeTypography.button,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderButton),
      )),
      inputDecorationTheme: InputDecorationTheme(
        border: const OutlineInputBorder(borderRadius: TwakeRadius.borderInput),
        enabledBorder: const OutlineInputBorder(borderRadius: TwakeRadius.borderInput,
          borderSide: BorderSide(color: TwakePalette.darkBorderMain)),
        focusedBorder: const OutlineInputBorder(borderRadius: TwakeRadius.borderInput,
          borderSide: BorderSide(color: TwakePalette.darkPrimaryMain)),
        labelStyle: TwakeTypography.body1.copyWith(color: TwakePalette.darkTextSecondary),
        hintStyle: TwakeTypography.body1.copyWith(color: TwakePalette.darkTextSecondary),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: TwakePalette.darkBackgroundPaper,
        surfaceTintColor: TwakePalette.darkBackgroundPaper,
        shape: RoundedRectangleBorder(borderRadius: TwakeRadius.borderShapeDefault),
      ),
      drawerTheme: const DrawerThemeData(
        backgroundColor: TwakePalette.darkBackgroundPaper,
        surfaceTintColor: TwakePalette.darkBackgroundPaper,
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: TwakePalette.darkBackgroundPaper,
        surfaceTintColor: TwakePalette.darkBackgroundPaper,
        textStyle: TwakeTypography.body1.copyWith(color: TwakePalette.darkTextPrimary),
        shape: const RoundedRectangleBorder(borderRadius: TwakeRadius.borderInput),
      ),
      listTileTheme: ListTileThemeData(
        titleTextStyle: TwakeTypography.body1.copyWith(color: TwakePalette.darkTextPrimary),
        subtitleTextStyle: TwakeTypography.body2.copyWith(color: TwakePalette.darkTextSecondary),
        iconColor: TwakePalette.darkTextIcon,
        selectedTileColor: TwakePalette.darkTextPrimary.withValues(alpha: 0.16),
        selectedColor: TwakePalette.darkTextPrimary,
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: TwakePalette.darkPrimaryLight,
        foregroundColor: TwakePalette.darkPrimaryDark,
        shape: RoundedRectangleBorder(borderRadius: TwakeRadius.borderFab),
      ),
      colorScheme: const ColorScheme.dark(
        primary: TwakePalette.darkPrimaryMain,
        onPrimary: TwakePalette.darkPrimaryContrastText,
        secondary: TwakePalette.darkSecondaryMain,
        onSecondary: TwakePalette.darkPrimaryContrastText,
        primaryContainer: TwakePalette.darkPrimaryLight,
        onPrimaryContainer: TwakePalette.darkPrimaryDark,
        secondaryContainer: TwakePalette.darkBackgroundContrast,
        onSecondaryContainer: TwakePalette.darkTextPrimary,
        onError: TwakePalette.darkPrimaryContrastText,
        onSurfaceVariant: TwakePalette.darkTextSecondary,
        surfaceContainerLowest: TwakePalette.darkBackgroundPaper,
        surfaceContainerLow: TwakePalette.darkBackgroundPaper,
        surfaceContainer: TwakePalette.darkBackgroundPaper,
        surfaceContainerHigh: TwakePalette.darkBackgroundPaper,
        surfaceContainerHighest: TwakePalette.darkBackgroundContrast,
        surfaceTint: TwakePalette.darkBackgroundPaper,
        outline: TwakePalette.darkBorderMain,
        outlineVariant: TwakePalette.darkDivider,
        error: TwakePalette.darkErrorMain,
        surface: TwakePalette.darkBackgroundPaper,
        onSurface: TwakePalette.darkTextPrimary,
      ),
      textTheme: textTheme,
      cardTheme: const CardThemeData(
        color: TwakePalette.darkBackgroundPaper,
        shape: RoundedRectangleBorder(borderRadius: TwakeRadius.borderMd),
      ),
    );
  }
}
