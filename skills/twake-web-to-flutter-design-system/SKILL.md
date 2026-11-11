---
name: twake-web-to-flutter-design-system
description: Use when generating or updating the twake_flutter_ui package from @linagora/twake-css, @linagora/twake-mui, @linagora/twake-icons, @linagora/twake-utils, and twake-i18n locales.
---

# Generate and Maintain `twake_flutter_ui`

Flutter cannot import npm packages directly. Instead, `twake_flutter_ui` is deterministically generated from the Twake repositories so the mobile app uses the exact same tokens, icons, utilities, and translation keys.

## Step 1 — Run the Deterministic Generator

```bash
twake-migrate generate-design-system \
  --web <path-to-react-repo> \
  --out <path-to-twake_flutter_ui>
```

## What Is Generated (Never Hand-Edit)

| Source Package | Generated Flutter Artifact | Purpose |
|---|---|---|
| `@linagora/twake-css` (`palette.json`, `vars.scss`) | `lib/src/tokens/twake_palette.dart` | Full color ramps + semantic light/dark tokens |
| `@linagora/twake-mui` (`makeTypography.ts`) | `lib/src/tokens/twake_typography.dart` | `Inter` typography scale (`h1`–`overline`) |
| `@linagora/twake-mui` (`radius.ts`) | `lib/src/tokens/twake_radius.dart` | Border radii (`none`, `sm`, `shapeDefault`, `md`, `lg`, `pill`) |
| `@linagora/twake-css` (`config.scss`, `spaces.scss`) | `lib/src/tokens/twake_spacing.dart` | Named spacing (`xs`–`xxl`), utility steps (`u0`–`u3`), `EdgeInsets` presets (`p1`, `mb1`, etc.) |
| `@linagora/twake-mui` + `twake-css` | `lib/src/theme/twake_theme.dart` | `TwakeTheme.light()` and `TwakeTheme.dark()` |
| `@linagora/twake-icons` (`assets/ui/*.svg`, `assets/illus/*.svg`) | `lib/src/icons/twake_icons.dart` + SVG assets | `TwakeIcons.<Name>` and `TwakeIcon` widget |
| `@linagora/twake-mui` components | `lib/src/components/twake_components.dart` + `widget-map.json` | 1-to-1 widgets (`TwakeLayout`, `TwakeAvatar`, `TwakeSearchBar`, `TwakeEmptyState`, `TwakeSegmentedTabs`) |
| `@linagora/twake-utils` (`twake-ts-utils`) | `lib/src/utils/twake_utils.dart` | `TwakeUtils.resolveUriTemplate`, `buildMailComposerUrl`, `buildCalendarEventUrl`, `resolveChatSpaUrl` |
| `twake-i18n` (`locales/*.json`) | `lib/src/l10n/app_<locale>.arb` + `twake_i18n.dart` | All 7 locales (`de`, `en`, `es`, `fr`, `it`, `ru`, `vi`) + `TwakeI18n.t()` |

## Missing Component Rule

Before porting a feature, check `widget-map.json`. If a `@linagora/twake-mui` component has `status: "unimplemented"`, stop and either ask the user or add the 1-to-1 widget to `twake_flutter_ui` first. Never improvise ad-hoc widget styling inside feature code.


## Preserve Values and Effective Widget Styles

Read the actual source token definitions; importing token names alone does not establish parity. Extract typography variants from `makeTypography.ts` rather than maintaining handwritten values. Preserve font size, weight, line height (convert pixel line heights to Flutter height ratios), letter spacing, and every variant present in the resolved version. Do not add variants from a newer version. Fail explicitly when the source shape is unsupported instead of silently using stale values.

Map semantic roles into the effective Flutter component themes in both light and dark modes. Flutter Material defaults can introduce unrelated surface tints, colors, typography, field borders, button shapes, and dialog radii even when the palette file is correct. Inspect `makePalette.ts`, `makeTheme.ts`, component overrides, and the web screen's mobile classes; do not assume a Flutter AppBar title uses the same variant as the web mobile title. Fix the generator and regenerate; never patch generated files.

Verify resolved styles on rendered widgets as well as source token values. Run light/dark checks and compare 390×844 captures before claiming visual parity. Record remaining component/layout differences separately from token fixes.

## Resolve and Validate the Web Dependency Versions

Use the target web app's lockfile and resolved packages as the design source. Never silently substitute the latest sibling Twake checkout. Check package versions and lockfile integrity against the target web lockfile before generation. Stale `node_modules` must block generation. If necessary, install exact locked packages into an isolated cache and pass `--dependency-root <cache>`; do not upgrade the web app to make extraction convenient. Investigate bundler aliases if they override normal package resolution.

The generator parses installed `dist/lib/*.js` token expressions with a Python tree-sitter AST and reads compiled CSS utility dimensions and the installed icon sprite. Unsupported expressions must fail explicitly. Source paths, versions, hashes and generated-file hashes are recorded in `version-lock.json`. Run `twake-migrate validate-design-tokens --ui <package>` after generation; the harness also checks source-to-Dart typography, semantic colors, spacing and radii and detects stale or modified generated files.

`harness-check` requires decoded-pixel visual parity by default. `--skip-parity` is for development only and must never be reported as completion. Supply real 390×844 light and dark screenshots named `<screen-id-lowercase>-<theme>.png`, together with flow results, to `verify-parity`. Invalid PNGs, missing themes, incorrect dimensions and missing baselines must fail. PNG encoding/compression differences alone must not count as visual differences.
