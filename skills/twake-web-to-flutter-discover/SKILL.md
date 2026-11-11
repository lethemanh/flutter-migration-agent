---
name: twake-web-to-flutter-discover
description: Use when starting a migration of a Twake React web app to a native Flutter app, or when refreshing the Feature Manifest and Gap Report. Runs static AST analysis and Playwright mobile-viewport (390x844) runtime discovery.
---

# Discover a Twake React Web App for Flutter Migration

## App workspace and continuity

Read the app's `migration.json`, `SKILL.md`, and `progress.json` before working. Create a workspace with `init-app --web <web> --mobile <mobile> --out apps/<app>`; launch with `start --config apps/<app>/migration.json`. Paths in config are relative to the config file unless absolute. `sourceAliases` optionally maps verified app import prefixes to source directories; static tsconfig and bundler aliases are read automatically, while dynamic factories require review. `librarySources` maps npm library names to implementation directories for source inspection; `dependencyRoot` selects installed lock-matched design packages. A sibling checkout is reference material, never permission to replace locked tokens.

Keep all discovery, decisions, plans, screenshots, logs, patches, evidence and reports under `apps/<app>/artifacts/`. Keep app-specific instructions in `apps/<app>/SKILL.md`. The Flutter app contains source, tests, platforms, runtime configuration and its generated `packages/twake_flutter_ui` build dependency. Do not create migration report folders inside it.

After each feature or before stopping, persist `checkpoint --config <config> --state <running|needs-user|blocked|stopped> --reason <specific reason> --next-action <exact next step> --feature <id>`. Continue approved work until complete or a concrete blocker requires user input. A single-feature port is a unit of work, not a reason to end the whole approved migration. Do not ask again for existing approval. Report what passed, what remains, why work stops, and how to resume; never claim silent automatic retries or completion interception in an interactive CLI session.

## Two discovery passes with different sources of truth

**Logic and feature scope come from source code. UI appearance and interaction states come from the running original app.** Do both before presenting a final plan for human approval. A screenshot cannot establish that a function was migrated, and a source import cannot establish what a widget actually looks like.

### Pass 1 — Source behavior inventory

```bash
twake-migrate discover-static --config apps/<app>/migration.json --out apps/<app>/artifacts/<discovery-run>
```

Use a new output directory when refreshing an approved manifest; preserve existing decisions and approvals. This pass emits:

- `feature-manifest.json`: routes, named/inline components, source-linked action flows, service/API candidates, libraries, locales and a `behavior` inventory.
- `source-behavior.json`: every parsed function/callback/method, call edges, argument expressions, branches, event/configuration handlers, permission/disabled conditions and JSX element props, with exact source files and lines. Direct imports, aliases, named barrel re-exports and namespace calls are linked where statically resolvable.
- `discovery-audit.json`: source hashes and unresolved/dynamic references. Function count is not feature count. Every function must belong to a feature or have a reasoned shared-utility/framework-glue/excluded disposition; reconcile unassigned functions using `functionDispositions[functionId] = {disposition, reason}`. Record `featureReconciliation[manifestId] = {status: reconciled, reviewedBy: agent, notes: ...}` after tracing the feature and its dependencies. Record the app-wide `sourceReconciliation` when all source review is complete. Start original UI discovery for reviewed features while the rest of source reconciliation continues.
- `gap-report.json` and `discovery-summary.md`: candidate mobile gaps and inventory summary.
- `screen-inventory.json`: list of screens, route parameters, and mobile routing stack classification (`shell-drawer-or-tab-root`, `detail-or-parameterized-stack`, `modal-or-fullscreen-form`, `auth-callback-or-login`).
- `ui-component-breakdown.json`: web tables, complex sidebars, modals, nested dropdowns, and hover triggers flagged for conversion to native mobile patterns (`table -> card-list`, `modal -> bottom-sheet`, etc.).
- `api-data-contracts.json`: static API/thunk/WebSocket inventory, enriched during `discover-runtime` with sanitized JSON schemas and OpenAPI 3.1 paths categorized into `uiStateQueries` (`GET`) and `userInteractionMutations` (`POST`/`PUT`/`PATCH`/`DELETE`).
- `state-validation-matrix.json`: extracted state management stores/slices (`createSlice`, `configureStore`, `createContext`), client-side validation rules (regexes, validator calls, JSX field constraints), and client/offline persistence requirements (`localStorage`, `sessionStorage`, `indexedDB`, online/offline listeners).
- `runtime-capture-plan.template.json`: route fixture requirements, bounded sitemap `crawl` settings, and an action checklist. Fill selectors and journeys by inspecting the original app; do not guess them from filenames.

Follow each user action through its handler, callbacks/hooks, store/provider, service/DAO, API/WebSocket operations and resulting state. Inspect validation, authorization/read-only restrictions, confirmation, cancellation, loading, empty, failure, retry and success paths where present. Include secondary menus, dialogs, forms and inline components. Do not replace Copy, Move and Delete with one generic row-action flow or count a button as working because it renders.

Inventory is evidence to guide source review, not a proof of exhaustive static understanding. Resolve callback props, spread props, aliases, higher-order wrappers, object methods, dynamic routes, conditional registrations and library internals before sign-off. JSX routes and static object-router arrays are extracted; unresolved factories/spreads/paths remain explicit review items. Inspect configured library implementations and bundler aliases. Record the agent reconciliation in `discovery-audit.json.sourceReconciliation`. After both passes and explicit human scope approval, record `review.status: reviewed`, `reviewedBy` and `notes`; this human review is separate from the agent reconciliation. Changed source files invalidate it.

### Pass 2 — Observe the original UI and action outcomes

Run the web app itself. At 390×844, inspect the relevant source-derived screens and action states in light and dark mode. Capture the first feature slice early and finish app-wide observation before final verification. Use the app's real theme controls, persisted theme setting or system color scheme. Never force a `data-theme` attribute, inject guessed styles, or assume an unchanged screenshot proves dark mode.

```bash
twake-migrate discover-runtime --url <running-web-url> \
  --manifest <discovery-dir>/feature-manifest.json --gaps <discovery-dir>/gap-report.json \
  --capture-plan <discovery-dir>/runtime-capture-plan.json --out <discovery-dir>
```

Supply authorized browser session/route fixtures when authentication or real entity IDs are needed. Each configured journey selects a manifest route and explicit browser steps (`click`, `fill`, `press`, `selectOption`, `check`, `uncheck`). Link the initiating or resulting callback using `sourceActionId`. Every step must assert a visible/hidden/enabled/disabled/text outcome; `expectResponse` can assert a same-origin endpoint's method and HTTP status without recording tokens or response bodies.

Example structure (replace IDs/selectors with observed app values):

```json
{
  "journeys": [{
    "id": "open-action-dialog",
    "routeId": "ROUTE_EXAMPLE",
    "readOnly": true,
    "steps": [{
      "sourceActionId": "ACTION_FROM_SOURCE_INVENTORY",
      "action": "click", "selector": "[data-testid=observed-action]",
      "expect": [{"selector": "[role=dialog]", "state": "visible"}]
    }]
  }]
}
```

Confirm read-only journeys from source behavior. Opening a dialog and cancelling can usually be inspected without changing data. Do not submit create/update/move/delete operations against real data without explicit authorization; `--allow-mutations` is only for already-authorized journeys. Use disposable fixtures or controlled failure responses for mutation/error branches when authorized.

Capture before/after screenshots, computed styles, layout bounds, compact ARIA accessibility trees (`ui.accessibilityTree`), accessible control labels and disabled/required/read-only states. Observe conditional menus, dialogs, validation/errors and permission variants using appropriate fixtures. Do not infer invisible states from the default screen. Input values, credentials and raw response bodies are not part of DOM metrics; `page.on('response')` records only structural JSON schemas and HTTP status codes into `api-data-contracts.json`, and the sitemap records visited manifest routes and observed local links.

Use the static manifest as the runtime sitemap. Visit each configured route fixture directly. Record links for review without following them. Drop query strings and fragments from sitemap identity and collapse concrete paths into their manifest templates. Preserve approved query values in explicit capture fixtures and journeys.

For optional exploration, add up to three source-verified read-only CSS selectors in a route fixture's `explore` list. These clicks run once per route template after the light baseline. Exploration stops at 30 steps or 60 seconds of probe time. Lower limits through `crawl.maxSteps`, `crawl.timeoutSeconds` and `crawl.maxPages`. Block an element for the rest of exploration when its click changes neither the canonical route nor produces a network response. Keep scripted assertions for modal and other DOM-only states in `journeys`. Their evidence remains separate from exploration. For integrations using the synchronous discovery loop, send the initial prompt and at most the last two steps to each decision, and keep full history on disk.

Discovery permission tiers apply at execution. Run routine discovery commands, launch the Playwright browser, and open configured app links without asking. Use `navigate` or `open_link` for direct visits to manifest route fixtures. Read-only tools run automatically within the configured origin and artifact directory. Interactive clicks and fills require a source-verified selector allowlist supplied by the host as `benign_selectors[routeTemplate][action]`. Runtime probes use each route fixture's `explore` allowlist. During unattended interactions, intercept HTTP requests and allow same-origin read methods only. Use mock inputs for exploratory fills.

Unknown interactive selectors stop the exploration loop for a decision. Delete, cancel-subscription, checkout, submit controls and declared write requests require explicit human authorization even if a selector is listed as benign. Run these as scoped scripted journeys with `--allow-mutations` after authorization. The browser request guard supplements source review. It covers routed HTTP requests during the interaction window.

`runtime-discovery.json` maps screenshots/assertions to source action IDs. A route screenshot alone cannot cover an action. Missing action themes, missing screens, skipped routes, disabled theme verification or failed expectations keep discovery partial or failed. Partial evidence can support scope approval and readiness for individual features. Only explicit user approval authorizes Flutter implementation. Discovery observations describe original behavior and do not certify native parity.

### Record the app's authentication flow

Trace login, session initialization and logout from this app's source and related libraries. Record the mechanism, sequence, environment/redirect configuration, bootstrap requirements, storage, native lifecycle/recovery behavior and evidence in `apps/<app>/SKILL.md`. Authentication may differ between apps; shared instructions do not prescribe another app's protocol, native library, callback adapter, backend endpoint or platform settings. Record source evidence when authentication is absent, and keep unresolved findings explicit until traced. Never put secrets or runtime credentials in the skill.

### Reconcile before planning

Compare both passes: every source action/function needs a feature disposition, and every observed control/state needs a source explanation. Correct missing manifest entries, merge callbacks into meaningful user-facing features, and preserve existing mobile decisions. List unresolved code, unavailable UI states or required fixtures explicitly. Then run `plan-migration`; if evidence is incomplete, produce a draft with blockers rather than silently excluding behavior.

## Step 3 — Human Review & Gap Resolution Gate

1. Present the scope inventory, verified original UI evidence, missing evidence and generated feature/task plan to the user. A source-only summary is a draft.
2. Ask how unresolved mobile gaps should behave. Pause their affected features until the user decides.
3. Once the user approves the scope, set `approval.status` to `"approved"` in `feature-manifest.json`. Record the user’s mobile decisions in `gap-report.json`. Run the feature gate before each port and finish the outstanding discovery before final verification.


## Reuse discovery evidence

Set `preflightRouteId` to a representative authenticated route with a source-verified `readySelector`. The driver checks that route first before collecting new evidence. Keep a reusable browser session or fixture in the app workspace. List fixture scripts and data as paths relative to the capture plan in `evidenceInputs` so edits invalidate cached evidence.

Use `discover-runtime --reuse-evidence` to retain verified route captures and complete journey/theme pairs. The report fingerprints source, capture settings, fixture inputs and each journey. New or failed journeys can run alongside retained evidence. Run status and failures are written to `runtime-discovery-run.json`. Keep the runtime report, screenshots, manifest, source audit and approval record together in the workspace backup.

Group source-linked steps by user outcome. Where one step reaches additional handlers, use `reachedActions` entries with `sourceActionId`, `sourceReason` and a specific `expect` assertion. The handler must be reachable from the primary action. A reached handler is separate from direct invocation evidence. Record unreachable controls through reviewed guard evidence.

## Human review and completed source revision

`migration-plan.md` is the short human feature/function checklist only. Curate `humanFeatures` in the manifest from source-backed scope; retain source mappings, waves, dependencies, guards and acceptance criteria in the agent JSON files. Do not present the long technical inventory as the human plan.

After the full migration passes final verification, run `complete-migration --config apps/<app>/migration.json --artifacts <verified-artifacts>`. It records `lastMigratedCommit` and the verified baseline manifest; never advance this value for discovery, partial work or development-only checks. Discovery records `sourceCommit`, and completion requires the same clean source revision.

On later runs, first run `discover-changes --config <config>`. Inspect the diff from `lastMigratedCommit`, including deletions/renames and affected importers, service/library dependencies and UI states. Reuse the completed inventory for unchanged scope. The current static discovery command still performs a full scan; use the change list to direct agent reconciliation rather than claiming an incremental parser is implemented. Missing history, changed dependency/theme/router configuration or broad shared changes can require a wider refresh.
