---
name: twake-web-to-flutter-port-feature
description: Use when porting a screen, component, route, or user flow from a Twake React web app into Flutter. Enforces single-feature manifest gating, web mobile-view copying, and feature behavior checks and wave-end harness checks.
---

# Port a Feature from React Web to Flutter

**One port unit = one manifest feature.** Continue to the next approved feature after verification; one unit does not end the approved migration. Never invent features, screens, routes, actions, or translation keys that are not in `feature-manifest.json`.

## Step 1 — Pre-Flight Feature Gate

Before writing any Dart code for `<MANIFEST_ID>`, run `check-feature-gate`:

```bash
twake-migrate check-feature-gate \
  --manifest <manifest-path> \
  --gaps <gap-report-path> \
  --widget-map <widget-map-path> \
  --feature <MANIFEST_ID>
```

- If `check-feature-gate` exits with `BLOCKED_UNRESOLVED_MOBILE_GAP`, **stop immediately and ask the user** how the web-only pattern should work on mobile.
- If it exits with `BLOCKED_MISSING_COMPONENT`, **stop** and add the missing component to `twake_flutter_ui` or ask the user.
- If `hasWebMobileAdaptation` is `true`, read the source React file's `isMobile` / `useBreakpoints()` branch and **copy that exact mobile behavior**.

## Step 2 — Write Flutter Code with Mandatory Traceability Headers

Every Dart file under `lib/` MUST begin with:

```dart
// @manifest-id: <ID_1>, <ID_2>
// @source-react: <relative/path/to/ReactFile.tsx>
```

### Architecture & Token Rules
- **Token enforcement**: Follow the token rules while implementing. The wave-end harness validates app aliases and generated token values.
- **Architecture**: Feature-first folders (`lib/features/<feature>/screens/`, `widgets/`, `providers/`), `flutter_riverpod` for state, `go_router` for routing.
- **Colors**: Use `TwakePalette.*`, `AppColors.*` (`lib/core/theme/app_colors.dart`), or `Theme.of(context).colorScheme`. Never use `Color(0x...)`, `Colors.*`, or raw hex strings (`'#FF5733'`).
- **Typography**: Use `TwakeTypography.*`, `AppTypography.*` (`lib/core/theme/app_typography.dart`), or `Theme.of(context).textTheme`. Never pass `TextStyle(`, `fontSize:`, or `fontWeight:`.
- **Spacing**: Use `TwakeSpacing.*` (`TwakeSpacing.p1`, `TwakeSpacing.mb1`, `TwakeSpacing.m`) or `AppSpacing.*` (`lib/core/theme/app_spacing.dart`). Never pass numeric literals to `EdgeInsets.*` or `SizedBox(height/width: ...)`.
- **Radius**: Use `TwakeRadius.*` or `AppRadii.*` (`lib/core/theme/app_radii.dart`). Never pass numeric literals to `BorderRadius.circular`.
- **Icons**: Use `TwakeIcon(icon: TwakeIcons.<Name>)`. Never use Material `Icons.*`.
- **Strings**: Use `TwakeI18n.t('<key>')` with an existing key from `feature-manifest.json`.
- **Auth**: Follow the selected app skill’s source-traced authentication flow; see App-specific authentication below.

## App-specific authentication

Read the selected app's `apps/<app>/SKILL.md` authentication section before porting login, callbacks, session startup or logout. That app skill owns the source-traced sequence, protocol and native library choice, environment configuration, registered redirects, backend bootstrap, storage, lifecycle and recovery rules, plus verification evidence. Do not apply another app's flow, endpoints, callback adapter or platform settings by default.

During discovery, trace the target source and related authentication libraries, then record the findings in that app skill. If authentication is absent, record the source evidence for that finding. If it is unresolved, record the missing information and resolve it before implementing auth. Preserve credential confidentiality and the applicable protocol's security guarantees; verify the complete app-specific login/session/logout journey, including recovery, against the original behavior. Shared instructions do not select an authentication protocol or implementation.

## Step 3 — Verify Feature Behavior and Close the Wave

Run focused Flutter analysis, tests, and runtime checks for the feature. Record implementation and behavior evidence in the app workspace and continue with the next approved feature in the wave.

After finishing the wave's planned Flutter work, run `check-app --config <config> --development` once for the wave. If it fails, fix the findings and rerun at the same checkpoint. Defer the app-wide harness during individual feature edits and subtasks.

At final verification, run `verify-parity --flutter <app>` with the current original and native screenshots and flow results. Then run `complete-migration`, which runs the final harness and records the verified source revision on success. Final verification requires full coverage, an approved plan, reviewed discovery, current feature evidence and current parity. A development report cannot certify completion.
