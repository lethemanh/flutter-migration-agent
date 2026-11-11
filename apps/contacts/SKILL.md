---
name: contacts-migration
description: Apply Contacts-specific source and runtime guidance when migrating the configured Twake Contacts web app to Flutter.
---

# Twake Contacts migration

This skill extends the [core migration workflow](../../AGENTS.md). Read [migration.json](migration.json) for the active web checkout, Flutter target, and library paths. Use discovery evidence and approvals for this workspace and the current source revision. With no completed source baseline, start with full discovery.

## Contacts session

- Trace the current OIDC setup in `apps/private/src/index.tsx`, the callback route in `apps/private/src/AppRoutes.tsx`, and the login callback in `apps/private/src/features/User/LoginCallback.tsx`. Verify the resolved `@linagora/twake-oidc` implementation for authorization, token exchange, userinfo validation, session storage, and logout.
- Follow startup through `common/src/features/User/useInitializeApp.ts`. The web app keeps tokens in memory and re-enters SSO on reload. Trace the callback through `getOpenPaasUserData` to `common/src/features/User/UserDao.ts` and its authenticated `api/user` request. Verify profile normalization and account language before treating the protected Contacts route as ready.
- Derive native callback registration, browser handoff, storage, and recovery from the current source and the target environment. Record the verified sequence, redirect and logout configuration, and native decisions here as discovery establishes them. Keep credentials out of the skill and artifacts.

## Runtime evidence

For an authenticated Contacts capture, assert a loaded address book with a known fixture row or the expected loaded empty state. The shell, tabs, and search field can appear while session or address-book loading is still in progress. Label synthetic backend evidence separately from live SSO and backend verification.

## Source-traced session findings (2026-11-03; runtime verification pending)

- Source revision: `2d46126cd593907a6c8f86e556e8e7cedb3c30c1`. The source worktree has a modified `package-lock.json`; do not overwrite it or treat the revision alone as a reproducible clean baseline.
- `apps/private/src/index.tsx` configures `@linagora/twake-oidc` with `SSO_BASE_URL`, `SSO_CLIENT_ID`, `SSO_SCOPE`, `SSO_REDIRECT_URI`, `SSO_POST_LOGOUT_REDIRECT`, and `SIDE_SERVICE_BASE_URL`. Do not copy runtime credentials into migration artifacts.
- Resolved `@linagora/twake-oidc/dist/oidc.js` (package version 1.3.0) discovers the issuer with `openid-client`, starts authorization-code login with S256 PKCE and random state, and stores only pending redirect state/verifier/return path in sessionStorage. The callback consumes that state once, verifies state and PKCE during code exchange, requires an ID-token subject, and validates userinfo against that subject. No pending state returns null. The app does not configure the library's optional framed/relay-state modes.
- Tokens are held in library memory and Redux, not persisted. `common/src/features/User/useInitializeApp.ts` removes legacy token/user sessionStorage entries and restarts SSO on reload. It skips initialization on `/callback`. Native storage, browser handoff, registered redirect URI, app resume/cancellation, process death, and recovery are **not selected or verified yet**; do not invent platform settings or inherit another application's implementation.
- `LoginCallback.tsx` prevents duplicate callback execution, dispatches userinfo/tokens, and awaits `getOpenPaasUserData`. The thunk fetches authenticated `api/user`, normalizes `_id` to `id`, merges profile/domain data, and applies core language and datetime/timezone configuration. Navigation waits for user data and tokens with loading cleared, strips callback query parameters, and restricts return navigation to `/contacts` paths. Callback errors route to `/error`; missing pending state routes to `/`.
- `apiUtils.ts` uses ky with backend prefix and retry limit 10. `dist/http.js` attaches a bearer token only to the configured API origin. An authenticated backend 401 outside the callback triggers one SSO redirect; duplicate redirects abort. Do not generalize this into a refresh-token flow for the Contacts API.
- OIDC logout discovers the end-session endpoint, includes the ID-token hint when present, clears local tokens, broadcasts session termination, and redirects to the configured post-logout destination. Discovery failure still clears local state and returns to `/`. Cross-tab notification support exists in the library; the app currently does not import its listener.
- Twake Bar has a **separate** platform SDK session: `sdkSession.ts` coalesces ID-token exchange per platform and sets a 5-second waiting fallback. Resolved SDK 1.2.0 exchanges through `/auth/token_exchange`, keeps platform credentials in memory, refreshes through `/auth/access_token` after a 401, and retries once. Preserve this distinction from Contacts OIDC. Platform exchange failures leave fallback navigation/account/logout usable. Native handling of platform client credentials remains a security/design review item.
- Evidence and incomplete discovery: `artifacts/discovery-20261103-reconciled/`. Source authentication findings are not proof of live login/bootstrap/logout or native recovery parity.

## User mobile decisions (2026-11-03)

- Open configured email, calendar and chat URLs in the system browser.
- A contact tap opens its details; retain actions in the existing row menu. Do not create a long-press preview.
- `AddressBookNavItem.tsx` already keeps its overflow button visible on mobile (`isHovered || isMenuOpen || isMobile`); copy that source branch. Runtime confirmation is pending.

## Recovery continuity update (2026-11-03)

- The earlier `artifacts/discovery-20261103-reconciled/` reference is historical and its directory is absent. Current evidence is `artifacts/discovery-20261103-recovery/`. Resume from its `plan-handoff.md`, generated plan, `source-action-review.json`, audit and progress checkpoint.
- Current source/configuration fingerprints match the recovery inventory. The lockfile remains modified. Nine installed Twake package version fields match current lockfile entries, as recorded in `dependency-review.json`. Integrity and token generation validation remain pending.
- Partial source review records 56 function dispositions, leaving 450 unassigned functions. Copy, Move, Delete and Import were traced through handlers and services with distinct outcomes. Import displays an upload notification before its import request completes. Push import result counts are console output in the source. Do not add an unobserved results dialog or content validator to the scope.
- The original endpoint probe failed, the browser access host was unavailable, and native Chrome computer use was rejected as unapproved. Runtime evidence remains unavailable. Restore reachable original app and authorized browser access/session/fixtures, finish source reconciliation, capture asserted light/dark screens and actions, and rerun plan-migration before requesting current scope approval.

## Resumed discovery update (2026-11-03)

- Forms and address-book source review is appended to `artifacts/discovery-20261103-recovery/source-action-review.json`; 178 function dispositions are recorded, with 328 still unassigned. Preserve previous findings and mobile decisions.
- Source/configuration hashes remain unchanged. `plan-migration` and manifest validation passed for the blocked draft; `discoveryReview.readyForApproval` remains false. No current-scope approval or native parity is established.
- Runtime probe still failed. Serving the existing original web build was denied at local socket bind (`PermissionError`). No browser retry or mutation was performed. See `runtime-access-status.json`. Resume with reachable original app and authorized loaded session/fixtures, finish reconciliation and asserted light/dark discovery, then regenerate the plan for explicit approval.

## Supporting-source continuity update (2026-11-03)

- Current recovery artifacts now record 506 reasoned function dispositions and zero unassigned functions. Supporting review covers listing/paging/direct links, serialization, profile/configuration, app shell, user search, SDK/socket registration and test/build infrastructure. Source reconciliation remains pending for unresolved call references and component/library behavior; do not equate zero unassigned functions with completed discovery.
- Source/configuration fingerprints remain unchanged. plan-migration and validate-manifest passed for the blocked draft; readyForApproval is false. Endpoint probe remains curl exit 7/HTTP 000; the original e2e generated stack descriptor is absent. No test fixture provisioning, runtime captures, token generation or Flutter changes were performed.
- Resume from artifacts/discovery-20261103-recovery/plan-handoff.md and source-action-review.json. Finish source-reference/library review and restore authorized original runtime access plus loaded session/entity/permission fixtures, capture asserted 390×844 light/dark states, regenerate the plan, then request explicit approval when gates pass.

## Component/library continuity update (2026-11-03)

- Focused review is saved in `artifacts/discovery-20261103-recovery/library-source-review.json`, with 37 hashed sources, 79 contextual unresolved-call reviews and eight handler/spread reviews. Raw parser edges and pending source-reconciliation status are preserved.
- Installed mobile action menus use bottom sheets; dialogs default to full-screen on mobile unless small/overridden. Contacts search is controlled with the app 300ms delay. Table uses server sorting and no long-press handler. Alias factory has no current private overrides.
- Name popover library includes email clipboard feedback. Keep the existing mobile tap-to-details/no-preview decision; do not invent a preview to expose library behavior. Runtime reconciliation is pending.
- Source/config fingerprints match. Draft generation and manifest validation pass, but readyForApproval remains false. Endpoint probe remains curl 7/HTTP 000. Restore authorized loaded original runtime/fixtures, finish references/library review, capture asserted light/dark states, regenerate plan and request approval only after evidence gates pass. No Flutter changes.

## Callback continuation (2026-11-03)

- Resume from `artifacts/discovery-20261103-recovery/callback-source-review.json` and `pending-source-review.json` as well as the earlier reports. The continuation records 53 hashed source files and, together with prior library review, contextual explanations for all 67 non-call parser items. Unresolved call edges remain pending; neither parser edges nor source reconciliation status were changed to imply completeness.
- Preserve label/chevron callbacks separately: installed NavDropdown has two click targets despite the app comment. Book navigation closes the mobile drawer; MyContacts label navigation does not explicitly close it. Create closes the drawer before opening its dialog; Subscribe only opens its dialog.
- Copy/Move disables cancellation during transfer. Create-book permits dismissal while its request runs. Rename and delete/remove-book confirmation close before dispatching their requests. Subscription candidate removal is local selection state, not server deletion. Bottom-sheet drag, safe-area, height and dismiss details are source-reviewed; rendered geometry remains unobserved.
- Outside-sandbox bounded localhost:5000 probe returned HTTP 200. Sandboxed probe returned curl 7/HTTP 000. The prior stopped browser operation was not repeated; read-only browser-access clarification was requested. No original UI captures or Flutter changes were made.
- The existing user approval is recorded in `user-plan-approval.json`. Regenerating the draft preserved all five approved artifact hashes exactly. Do not ask for the same approval again. `readyForApproval` remains false until source reconciliation and complete original route/action light/dark observations pass. Native auth configuration/recovery, SDK session handling and dependency integrity remain later prerequisites.

## Read-only runtime and DAO continuation (2026-11-04)

- User explicitly reauthorized read-only browser inspection. Native Chrome showed loaded Contacts rows at CSS 390×844; connector host remains unavailable. The first retained screenshot is 780×1688 (2× DPR), a partial light observation only. Chrome switched to another user tab during capture; UI work paused pending availability. See artifacts/discovery-20261103-recovery/manual-runtime-observations-20261104.json.
- dao-call-review.json records 67 additional contextual call reviews; pending-source-review.json retains 1447 unreviewed calls. Review preserves distinct DAV methods/IDs, best-effort owner/member enrichment, subscription read-back rights and installed ky method-specific retry behavior. No raw parser resolutions were rewritten.
- Source/config fingerprints match, draft generation passes and all five approved artifact hashes match. readyForApproval remains false until reconciliation and complete original light/dark route/action evidence pass. Existing scope approval remains valid; no Flutter changes or parity certification.

## Available-page continuation (2026-11-04)

- User confirmed Contacts availability; native read-only inspection resumed. Five valid 390×844 PNGs now cover loaded list in light/dark, empty create-book dialog in light/dark, and new-contact form in dark. Details/hashes are in manual-runtime-observations-20261104.json. These partial manual observations do not replace discover-runtime or certify parity.
- ThemeToggle is DEBUG-only in ContactsPage.tsx. Used SettingsSlice source-defined localStorage theme=dark through DevTools UI, reload and verified effective dark surface/text changes plus loaded rows. The browser is currently left in dark mode on /contacts/new with an unchanged empty form.
- Create-book opens full-screen with Create disabled when empty; close returns to list. Account menu offers logout; logout was not invoked. Network log visibly records successful OIDC/profile/book/contact requests, without storing credentials or response bodies.
- User selected an isolated local test backend for app mutation outcomes, then questioned backend scope. Clarified that only app behavior is under verification. Docker Desktop was started and existing images inventoried; no stack/services/users or mutations were created. Prefer controlled API fixtures over standing up the full stack.

## Fixture-backed app discovery continuation (2026-11-04)

- The user directed native auth to “follow the web flow”. Preserve the recorded OIDC/PKCE/callback/profile/in-memory-session/logout sequence; do not ask again which flow to use or invent callback registrations. See artifacts/discovery-20261103-recovery/native-session-decision.json.
- Current source/config hashes match. translation-hook-call-review.json adds 223 contextual calls, leaving 1224 unresolved call reviews. Source reconciliation is still pending.
- Browser-context fixtures exercise the unchanged original app while fulfilling disposable OIDC/API data and blocking external requests. The toolkit discover-runtime report at fixture-runtime/runtime-discovery.json is partial: 16 route captures, 42 asserted action states, 194 missing action IDs, missing Error/HandleLogin screen evidence, skipped callback/error routes. Fixture DEBUG=true/LANG=en and incomplete SDK/WebSocket branches are explicit. These are original-app synthetic observations, not live/backend/native parity.
- fixture-runtime/outcomes/app-outcome-results.json records 10 passing app-outcome cases (Copy/Move/Delete/Create/Edit × light/dark). All 140 capture/outcome PNGs decode at 390×844; outcome hashes verified. Delete error produces both a page alert and a row snackbar. The snackbar covers the confirmation footer until Ok; modal aria-hidden affects accessible name queries. Preserve distinct source behavior rather than a generic action handler.
- Existing manifest/human scope/mobile decisions remain unchanged and approval retained. Generated machine plan/tasks now reference partial evidence; readyForApproval remains false. Continue from resumed-discovery-status-20261104.json and plan-handoff.md. No Flutter changes.

## Source reconciliation and edge-state continuation (2026-11-04)

- Source reconciliation is complete with 1593 contextual call reviews and 506 function dispositions; source/config hashes and approved manifest/human scope/gap decisions are unchanged. Raw parser edges remain intact.
- `fixture-runtime/runtime-discovery.extended.json` now covers all seven screens and 205 invoked/reached source action IDs in light/dark. There are 94 selected passing fixture cases including two guard-only cases; failed attempts are retained. All captures remain390×844 as explicitly requested. This is synthetic API/OIDC/socket evidence, not live backend/native parity.
- `guard-state-review.json` records four callbacks that cannot be invoked in the observed mobile UI: two desktop-only Edit controls and two MUI Alert default Close callbacks suppressed by explicit Ok actions. Both-theme hidden/absence assertions are saved separately, without invocation credit. The current toolkit gate remains false; explicit guard coverage handling is required. Separate SDK platform session exchange/failure/recovery observations remain pending.
- WebSocket fixture observations verify registration, push-driven contact refresh, import counts in console, offline and reconnect. Role-menu Escape closes both menu and sharing dialog; row bottom-sheet Escape does not close it, while outside click does. Snackbar timeout pauses under pointer hover; notifications can disappear on route unmount. Preserve these observed distinctions.
- User confirmed Android and iOS and prefers the web return URI if supported. Native directory is empty; no identifiers, callback handlers or domain associations exist. Same Contacts destination is distinct from native browser-return registration. `native-session-decision.json` records the RFC8252 explanation; no URI, issuer registration or platform identifiers were invented.
- Latest draft/manifest validation pass, source reconciliation gate passes, runtime gate remains incomplete. Resume from `artifacts/discovery-20261103-recovery/resumed-discovery-status-20261104.json` and `plan-handoff.md`. Existing approval remains valid for unchanged scope; do not request it again. No Flutter code or generated package changed.

## Evidence-loss recovery (2026-11-04, current)

- At startup, configured artifacts and dependency cache were absent; user confirmed no backup. Historical recovery paths above are unavailable. Current evidence is `artifacts/recovery-20261104-current/`. Preserve recorded scope approval/mobile choices; do not request the same approval again. Original hash records cannot be reconstructed from prose.
- Native Flutter source/platforms/tests and generated UI now exist and were preserved. Current web revision remains `2d46126cd593907a6c8f86e556e8e7cedb3c30c1`; worktree is now clean, including lockfile. Current token validation passes; nine installed Twake package version fields match lockfile. Registry tarball integrity is not established.
- Source review rebuilt:506 function dispositions,1593 contextual unresolved-call records,52 hashed library sources. Raw parser resolutions retained. Source reconciliation passes; machine plan remains blocked pending runtime evidence. See source-review-session.json, contextual-call-review.json, library-source-review.json and generated plan/tasks.
- Isolated Playwright bootstrap of unchanged original app passes synthetic OIDC callback/profile/loaded fixture row in light/dark at390x844. Probes are not a complete toolkit runtime report. Browser connector host unavailable; isolated browser sandbox access was granted. External requests and unconfigured writes blocked.
- Read-only native review found auth bypass (root/callback navigate without OIDC/profile readiness), hardcoded current_user bootstrap and DAO failure masking; see existing-native-review.json. No native files changed. Continue asserted fixture journeys and toolkit discover-runtime, preserving distinct OIDC/SDK/socket behavior.

- Recovery runtime update: all7 screens/20 route captures,70 action observations;20 mutation-outcome cases,6 auth-edge cases,8 SDK cases pass.190 action IDs remain. Resume current plan-handoff.md and resumed-discovery-status.json. Prior passes retained; no app code changed. User again confirms web flow; platform IDs now exist as com.linagora.twake.contacts, registered native return URI still unspecified. Source-reviewed unforwarded mobile ActionsMenu callbacks remain explicit pending guard items.

## Runtime restart and export decision (2026-11-06)

- Contacts dev server was started with `npm run start:private`; `http://localhost:5000/contacts` returns HTTP 200 and title Twake Contacts. Before startup port 5000 answered from macOS AirTunes with HTTP 403.
- Current source is `fa8e9efde60275c4bb549e95e8ea546adb9f3763`. Separate refresh evidence is in `artifacts/discovery-20261105-refresh/`; historical `recovery-20261104-current` evidence remains preserved. New source/config changes invalidate old reconciliation and token checks; do not use historical passing counts as current certification.
- User selected the system Save file picker for individual-contact and address-book vCard exports on Android and iOS. See `artifacts/discovery-20261105-refresh/mobile-export-decision.json`. Preserve existing approval and all five mobile decisions; only new scope needs focused review. No native files changed.

## Current discovery handoff (2026-11-06)

- Active evidence is `artifacts/discovery-20261106-current/`; see `plan-handoff.md`. Current source revision is `fa8e9efde60275c4bb549e95e8ea546adb9f3763` with pre-existing package.json/package-lock.json edits preserved. Historical approval/mobile decisions remain intact.
- Current source/action discovery and manifest validation pass: all seven screens/20 route captures,214 actions (208 invoked/reached plus six separately observed guards),194 action cases plus six OIDC/eight SDK/20 mutation cases pass. There are1,622 asserted observations; synthetic API/OIDC/socket evidence remains distinct from live backend/native parity.
- Contact/book vCard export is new source scope:12 light/dark download/error-dismissal cases pass, including filenames and vCard bytes. User selected system Save file picker on Android/iOS. Focused approval of these additions to the existing plan is pending; do not request approval again for unchanged scope.
- Updated menu library traps focus and stops Escape propagation: top role sheet closes first, parent sharing dialog remains until second Escape. Exact installed library chain is reviewed. Toolkit guard-validator extension was installed with filesystem approval;41 fail-closed tests pass. It preserves non-invocation status of two discarded propagation callbacks.
- Current design-system preview validates against installed lock-matched sources. Target native generated UI remains stale; no native files changed. Eight parser/helper/component candidates still lack individual UI/nonvisual disposition mapping; see machine plan. Registered native return URI and platform association/handler configuration remain missing. Final parity, clean source revision and registry tarball integrity are not established.
- Resume focused scope review, then correct candidate task grouping and feature-gate approved work. Keep all current/historical evidence and failed attempts. Do not advance lastMigratedCommit.


## Current discovery and Wave 0 refresh (2026-11-09)

- Active evidence is `artifacts/discovery-20261109-current/`; read `plan-handoff.md`, `verification-summary.json` and `candidate-dispositions.json`. Source advanced to clean `4f546b849a821fa9de7e0bd76ed0c4ec98cfe941`; app runtime sources unchanged except two test/build files, dependencies refreshed (MUI 19.5.0). Prior export-inclusive approval was present in user-plan-approval.json and reaffirmed by user; do not request it again.
- Current full source/action discovery passes with seven screens, 20 captures, 214 actions (208 invoked/reached, six guards), 194 action cases and 1,622 assertions. Six OIDC/eight SDK/20 mutation cases pass. Evidence remains synthetic original app, not live/native parity.
- Native generated UI refreshed from current installed lock-matched sources; token validation passes. Installed MUI package index changed while menu implementations are unchanged; narrowly reviewed guard-validator update installed with filesystem approval and 42 passing tests.
- Native contact DELETE now preserves backend prefix/trailing slash and encodes DAV IDs. Fourteen DAO tests, all 39 native tests and Flutter analysis pass. Feature evidence recorded for API_DELETE_CONTACT. Development harness still fails eight helper/callback/unused/nonvisual component mappings; explicit dispositions are saved without bypassing gates.
- Exact registered full native return URI and domain association remain unprovided. User asked which URL is needed; explained the SSO-registered full redirect address including scheme/host/path, rather than /callback alone. Follow web OIDC flow; no registration invented. Final native auth/runtime/feature/visual parity remains outstanding. lastMigratedCommit remains null.


## Callback path decision (2026-11-09)

- User explicitly confirms no native URI is registered and directs using `/callback`. Keep this existing application callback path; do not keep asking for a registered URI to continue independent work.
- `/callback` remains a path, not a verified native browser-return registration. Do not invent scheme/host, SSO client registration or platform associations. Keep live/native SSO verification outstanding while correcting feature mappings and implementing approved independent behavior. See `artifacts/discovery-20261109-current/callback-path-decision.json`.


## Native session implementation choice (2026-11-09)

- Use Flutter AppAuth 12.1 for the source-traced authorization-code flow with external browser, S256 PKCE/state and native AppAuth token validation, followed by subject-matched userinfo and authenticated api/user bootstrap. Keep tokens in memory; do not add Contacts refresh-token behavior. Separate SDK platform session remains independent.
- Keep the application callback route `/callback`. No absolute return address or platform association has been supplied. The adapter must reject incomplete runtime configuration before opening a browser, while tests inject a controlled authorization client to verify session/routing logic. No fake successful login or fabricated callback registration is permitted.
- References inspected: installed Flutter AppAuth package 12.1.0 and platform interface, plus https://pub.dev/packages/flutter_appauth and official package API documentation.
