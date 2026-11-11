# Twake Web-to-Flutter Migration Agent

Python toolkit and agent workflows for migrating Twake React apps to Flutter. The web source and its locked dependencies define the behavior and design system. Static discovery, token validation, behavior evidence and screenshot comparisons provide different checks; none alone proves parity.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m playwright install chromium
```

Python 3.11+ is required. `requirements.lock` records tested dependency versions. JavaScript/TypeScript parsing uses Python tree-sitter bindings; the toolkit does not need Node.js. Web npm packages are input data, and token expressions are parsed without executing them.

## App workspaces

Every app has one migration workspace outside its Flutter project:

```text
apps/contacts/
  migration.json       Web/mobile paths, locked dependency root, library source paths
  SKILL.md             App-specific decisions and instructions
  progress.json        Current step, stop reason, next action and history
  artifacts/           Manifest, gaps, plan, screenshots, logs, evidence and checks
  cache/               Restorable locked dependency inputs (ignored)
```

The mobile project contains `lib/`, `test/`, platform directories, runtime config and `packages/twake_flutter_ui/`. The generated UI package is a build dependency and stays with the app. Migration reports do not belong in the mobile project.

```bash
.venv/bin/twake-migrate init-app --web /path/to/web --mobile /path/to/mobile --out apps/my-app
.venv/bin/twake-migrate start --config apps/my-app/migration.json
```

The two-path `start <web> <mobile>` form also works and creates a workspace under `apps/<web-directory-name>`. Use `init-app` and `--config` for a stable app name. The launcher opens an interactive Codex CLI session, reads the app skill, grants write access to the app workspace and records CLI exit status. Set `TWAKE_CODEX_BIN` for a custom CLI. It does not automatically restart sessions or intercept completion. Existing approvals remain valid unless scope changes; approved manifests/plans cannot be overwritten by rediscovery/replanning into the same directory.

Config paths resolve relative to `migration.json`. `librarySources` maps package names to implementation directories, including related local repositories:

```json
{
  "schemaVersion": "1.0.0",
  "webRoot": "/path/to/web",
  "mobileRoot": "/path/to/mobile",
  "dependencyRoot": "cache/design-dependencies",
  "sourceAliases": {"@app": "/path/to/web/src"},
  "librarySources": {
    "@linagora/twake-utils": "/path/to/twake-ts-utils",
    "@linagora/twake-mui": "cache/design-dependencies/node_modules/@linagora/twake-mui"
  }
}
```

Each app’s `SKILL.md` owns its authentication and session flow. Discovery records source-backed login, bootstrap, logout, native lifecycle/configuration and verification there; the shared workflow does not prescribe one app’s protocol or backend endpoints for another.

Source references guide behavior inspection. They never override the target app's dependency lockfile for design generation.

## Migration and verification

1. Establish logic scope from source with `discover-static --config <config>`. Review `source-behavior.json`: functions, callbacks, branches, call edges, service effects, handlers and unresolved references have exact source locations. Static JSX and object routes, inline components, import aliases and named re-exports are included. Static TypeScript/bundler aliases are read without executing app code; use verified `sourceAliases` overrides for dynamic mappings. Reconcile unassigned functions and record their disposition/reason in `discovery-audit.json`; record the agent reconciliation as `sourceReconciliation: {status: reconciled, reviewedBy: agent, notes: ...}`. Human review follows both source and UI passes, with `review.status`, `review.reviewedBy`, and `review.notes` recorded after explicit approval. Function counts include source/test helpers and are not feature counts.
2. Establish UI references using the original running app with `discover-runtime` at 390×844 in both themes. Fill the generated `runtime-capture-plan.template.json` with observed selectors and asserted journeys. The report captures real computed styles, control geometry and before/after action states. It uses original app theme settings, without forcing a theme attribute. A route screenshot cannot count as observing a source action; missing screens/action themes or wrong outcomes leave discovery incomplete.
3. Run `plan-migration` after reconciling source and UI observations. Present grouped features/actions, library usage, UI references, waves and mobile gaps. `feature-review.json` includes the source/function review ledger; `migration-tasks.json` includes per-feature logic/UI/verification tasks and nested action subtasks with dependencies and observable acceptance criteria. Obtain human approval before Flutter implementation. Incomplete evidence produces a blocked draft and cannot be approved. Configured library references and related dependencies outside the built-in mapping catalog must also be inspected.
4. Run `generate-design-system --config <config>` and `validate-design-tokens --ui <mobile>/packages/twake_flutter_ui`. Stale installed dependencies, unsupported expressions and generated/source drift fail validation. The lock records versions, paths and hashes. Fix the generator and regenerate rather than patching generated Dart.
5. Port one approved feature at a time after `check-feature-gate`. Copy existing web mobile behavior. Continue through the approved migration; one feature is a work unit, not a session stopping condition.
6. Run Flutter analysis/tests and real runtime journeys. Record per-feature implementation and verification evidence with `record-feature`. Run `verify-parity --flutter <mobile>` for current baselines, native captures and flow results.
7. Run `check-app --config <config> --development` at the end of each implementation wave. After final parity verification, run `complete-migration --config <config>`. It runs the final harness, writes `artifacts/harness-final.json`, and records the verified source revision when all completion checks pass.

Useful commands:

```bash
# End of an implementation wave. Development verification only.
.venv/bin/twake-migrate check-app --config apps/contacts/migration.json --development

# Record one feature after verifying its behavior; repeat flags for multiple files.
.venv/bin/twake-migrate record-feature --manifest <artifacts>/feature-manifest.json \
  --flutter <mobile> --feature <ID> --implementation lib/features/example.dart \
  --verification <artifacts>/behavior-test.log --out <artifacts>/feature-evidence.json

.venv/bin/twake-migrate checkpoint --config apps/contacts/migration.json \
  --state blocked --reason 'Specific failing prerequisite' --next-action 'Exact recovery step'
```

Final `harness-check` defaults to full coverage. Supply `--evidence` and `--parity-report`; its plan defaults to `migration-plan.json` beside the manifest. `--skip-parity` allows partial development checks unless `--strict-coverage` is also passed. Development results explicitly set `completionVerified: false`. Headers establish traceability, not behavior. Hashes reject stale evidence but cannot judge whether a log describes a valid test; source review and live validation remain necessary.

App theme/token alias files are also linted. Generated library tokens are checked against locked web sources. Matching token names does not guarantee effective widget styles: Material defaults, layout, component overrides and state behavior still require rendered checks.

Screenshots must be valid 390×844 PNGs named `<screen-id-lowercase>-light.png` and `-dark.png`. Comparison uses decoded pixels, channel tolerance 8/255 and default mismatch threshold 0.08. Every screen and associated flow must pass. Reports fingerprint the manifest, Flutter source, screenshots and flow inputs. Final checks reject parity reports without matching Flutter source fingerprints. Use `--storage-state` for an authorized runtime browser session; never commit private session data.

Browser journeys support explicit `click`, `fill`, `press`, `selectOption`, `check` and `uncheck` steps with `expect` assertions (`visible`, `hidden`, `enabled`, `disabled`, `text`). `sourceActionId` links an observation to its handler inventory. Optional `expectResponse` asserts endpoint path, request method and status; input values and response bodies are excluded from DOM metrics. See the discovery skill for a journey example. Read-only inspection is the default; `--allow-mutations` is for explicitly authorized data-changing journeys with disposable fixtures.

A reviewed function disposition is recorded as:

```json
{"functionDispositions": {"FUNC_FROM_INVENTORY": {"disposition": "shared-utility", "reason": "Inspected source; this helper belongs to the shared model layer"}}}
```

Use `feature`, `shared-utility`, `framework-glue`, or `excluded` with a concrete reason. Dynamic references are never evidence that a feature does not exist. Task paths/grouping are provisional until human review. Source or configuration changes invalidate discovery readiness; approval metadata alone does not invalidate unchanged UI observations.

## Toolkit structure

- `twake_migrate/`: CLI, parsers, checks, packaged schemas/assets and generator templates; the single source for schemas and bundled fonts.
- `skills/`: shared migration instructions. Regenerate `AGENTS.md` and packaged rules with `scripts/gen_agents.py`; never edit the generated copies.
- `apps/`: app-specific migration context and evidence.
- `tests/`: toolkit regressions and their fixtures.
- `scripts/` and `bin/`: maintenance and entry points.

```bash
.venv/bin/python -m pytest
TWAKE_BROWSER='/path/to/chromium' .venv/bin/python -m pytest tests/test_runtime.py
```

Start Contacts with `start --config apps/contacts/migration.json`. The app skill extends the shared workflow with Contacts-specific source and runtime guidance. Discovery and progress are recorded in the app workspace.

Interactive sessions use on-request approval in the workspace sandbox. The agent proceeds with routine work and asks for required decisions, risky actions outside existing authorization, or access that a necessary step still needs.

Use `start --batch --config apps/contacts/migration.json` to run a phase without interactive prompts. The command waits for the result, saves diagnostics under the app's `artifacts/` directory, and stops after one hour if the phase stalls. The agent runs routine scripts and makes reversible decisions on its own. When the plan is ready, the batch presents it and explicitly asks for approval. Use interactive `start` to give approval, then resume batch work from the saved checkpoint. If evidence is missing, the batch reports the blocker and the next action.
