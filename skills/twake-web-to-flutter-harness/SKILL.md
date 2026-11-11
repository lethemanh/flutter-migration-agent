---
name: twake-web-to-flutter-harness
description: Guardrail reference for the Twake Web-to-Flutter Migration Agent. Defines the 8 mechanical checks enforced by harness-check.
---

# Twake Web-to-Flutter Harness Guardrails

The harness enforces 8 mechanical checks (`twake-migrate harness-check`) to check whether the Flutter app preserves the Twake UI system and web feature set without hallucinating or dropping behavior:

1. **Manifest-Gated Generation (`[MISSING_MANIFEST_ID]`, `[MANIFEST_NOT_APPROVED]`)**
   - `feature-manifest.json` must have `approval.status === "approved"`.
   - Every `.dart` file in `lib/` must have a `// @manifest-id: <ID>` header referencing valid IDs from `feature-manifest.json`.
2. **Source Traceability (`[MISSING_SOURCE_TRACEABILITY]`, `[BROKEN_SOURCE_TRACEABILITY]`)**
   - Every `.dart` file in `lib/` must have a `// @source-react: <path>` header pointing to the actual React `.tsx`/`.ts` file in the web repository.
3. **Reverse Check — No Invented Features (`[REVERSE_CHECK_INVENTED_*]`)**
   - Any `GoRoute(path: ...)` not in `manifest.routes` fails the build.
   - Any `@manifest-id` not in `feature-manifest.json` fails the build.
   - Any `TwakeI18n.t('...')` key not in `manifest.i18n.keys` fails the build.
4. **Coverage Check (`[INCOMPLETE_COVERAGE]`)**
   - Final checks require full `routes`, `screens`, `components`, `flows`, and `apiCalls` coverage by default. Development checks with `--skip-parity` may be partial.
   - Headers count traceability only. Use `record-feature --manifest <manifest> --flutter <app> --feature <id> --implementation lib/<file>.dart --verification <test-or-runtime-log> --out <workspace>/artifacts/feature-evidence.json` for each item. Final harness requires `--evidence <file>`, current implementation/verification hashes, and the matching manifest hash. Evidence files must describe behavior tested; their existence alone is not proof of feature correctness.
   - Newly generated plans track discovery readiness per feature. The development harness checks readiness for referenced features. The final harness requires complete, current app-wide discovery. Task dependencies and action outcome checks live in `migration-tasks.json`.
   - Final verification requires a human-reviewed discovery audit and unchanged source fingerprints. Unrecognized/dynamic source patterns require manual reconciliation before approval.
5. **Token Value Validation and Linter (`[TOKEN_LINT_*]`)**
   - Validates generated token values against lock-matched web sources and rejects source/generated-file drift.
   - Run the app-wide checks explicitly at the end of each implementation wave and at final verification. `HarnessOrchestrator` only intercepts completion in integrations that call its API; the launcher does not connect it to Codex. This API checks token syntax, not overall migration completion.
   - App theme/token definition files are scanned too; renaming a file cannot exempt hardcoded widget styles. Generated library tokens are checked separately against web sources.
   - Forbids `Color(0x...)`, `Colors.*`, and raw hex strings -> require `TwakePalette`, `AppColors` (`lib/core/theme/app_colors.dart`), or `ThemeData`.
   - Forbids `TextStyle(`, `fontSize:`, and `fontWeight:` -> require `TwakeTypography`, `AppTypography` (`lib/core/theme/app_typography.dart`), or `Theme.of(context).textTheme`.
   - Forbids numeric `EdgeInsets.*` and `SizedBox(height/width: ...)` -> require `TwakeSpacing` or `AppSpacing` (`lib/core/theme/app_spacing.dart`).
   - Forbids numeric `BorderRadius.circular` -> require `TwakeRadius` or `AppRadii` (`lib/core/theme/app_radii.dart`).
   - Forbids `Icons.*` -> require `TwakeIcons`.
6. **Missing-Component Gate (`[BLOCKED_MISSING_COMPONENT]`)**
   - Fails if a referenced manifest item uses a `@linagora/twake-mui` component marked `unimplemented` in `widget-map.json`.
7. **Mobile-View & Gap Gate (`[BLOCKED_UNRESOLVED_MOBILE_GAP]`)**
   - If the web app has a mobile view (`isMobile` / `useBreakpoints`), copy it.
   - If a component has an entry in `gap-report.json` with `status: "unresolved-ask-user"`, the harness blocks porting until the user resolves it.
8. **Parity Gate (`[PARITY_GATE_FAILED]`)**
   - Required by default: compares decoded pixels in valid 390×844 light/dark screenshots plus interaction flows. `--skip-parity` is explicitly development-only; it cannot certify completion.


Use `check-app --config apps/<app>/migration.json --development` once at the end of each implementation wave. At migration completion, use `complete-migration --config apps/<app>/migration.json`, which runs the final harness itself. Reports are written in the app workspace. A passing development check never certifies completion. Final parity must cover every screen and associated flow; reports are tied to manifest, Flutter source and screenshot/flow input hashes. Generate final parity with `verify-parity --flutter <app>` so Flutter source changes invalidate it. Mechanical checks cannot establish that a handler or screenshot represents the intended behavior; retain source review and real device/runtime validation.
