"""Playwright browser driver, mobile viewport setup, storage-state reuse, and deterministic journey execution."""
from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from time import monotonic
from urllib.parse import parse_qsl, urljoin, urlparse

from ..core.common import digest, discovery_fingerprint, load, write_json
from ..config.settings import DiscoverySettings
from ..core.state import DiscoveryState
from ..core.types import ScreenSnapshot
from .dom import (METRICS, ExplorationClicks, capture_state, crawl_sitemap,
                  route_pattern, wait_for_deterministic_settle)
from .interceptor import NetworkContractRecorder
from .evidence import evidence_key, fingerprint, reuse_runtime
from .permissions import RISKY_ACTION, needs_confirmation, read_only_requests


def _local_url(base_url, path, allowed_query_params=None):
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
        raise ValueError('Capture paths must be local absolute paths')
    target = urljoin(base_url, path)
    base, actual = urlparse(base_url), urlparse(target)
    if (base.scheme, base.netloc) != (actual.scheme, actual.netloc):
        raise ValueError('Capture paths must stay on the configured origin')
    if actual.fragment:
        raise ValueError('Capture paths cannot contain fragments; never capture OAuth credentials')
    if actual.query:
        allowed = allowed_query_params or {}
        if not isinstance(allowed, dict):
            raise ValueError('Allowed capture query parameters must be a mapping')
        pairs = parse_qsl(actual.query, keep_blank_values=True, strict_parsing=True)
        if not pairs or len({key for key, _ in pairs}) != len(pairs):
            raise ValueError('Capture query parameters cannot be repeated')
        for key, value in pairs:
            if re.search(r'token|code|state|secret|password|nonce|assertion|session|auth|credential', key, re.I):
                raise ValueError('Authentication query parameters cannot be captured')
            values = allowed.get(key)
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values) or value not in values:
                raise ValueError('Capture query is not explicitly allowed by the capture plan')
    return target


def _capture_routes(manifest, plan, base_url):
    fixtures = plan.get('routes', {})
    known = {route['id'] for route in manifest['routes']}
    if set(fixtures) - known:
        raise ValueError('Capture plan references unknown manifest routes')
    result = []
    for route in manifest['routes']:
        fixture = fixtures.get(route['id'], {})
        if fixture.get('skipReason'):
            continue
        path = fixture.get('path', route['path'])
        probes = fixture.get('explore', [])
        if not isinstance(probes, list) or len(probes) > 3 or any(not isinstance(probe, str) or not probe.strip() for probe in probes):
            raise ValueError('Route explore must list up to three verified read-only selectors')
        if ':' in path or re.search(r'\[[A-Za-z_][A-Za-z_0-9]*\]', urlparse(path).path):
            raise ValueError(f"Route {route['id']} requires an explicit real route fixture or skipReason")
        target = _local_url(base_url, path, plan.get('allowedQueryParams'))
        if not route_pattern(route['path']).fullmatch(urlparse(target).path):
            raise ValueError(f"Fixture does not match manifest route {route['id']}")
        expected = _local_url(base_url, fixture.get('expectedPath', path), plan.get('allowedQueryParams'))
        result.append((route, fixture, target, expected))
    if not result:
        raise ValueError('Capture plan selects no routes')
    preflight = plan.get('preflightRouteId')
    if preflight:
        if not any(route['id'] == preflight for route, _, _, _ in result):
            raise ValueError('preflightRouteId must identify a configured, non-skipped route')
        result.sort(key=lambda entry: entry[0]['id'] != preflight)
    return result


def validate_journeys(manifest, plan, allow_mutations=False):
    actions = {a['id']: a for a in manifest.get('behavior', {}).get('actions', [])}
    routes = {r['id'] for r in manifest['routes']}
    journeys = plan.get('journeys', [])
    seen = set()
    for journey in journeys:
        name = journey.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in seen:
            raise ValueError('Journey IDs must be unique filename-safe names')
        seen.add(name)
        if journey.get('routeId') not in routes:
            raise ValueError(f'Unknown route in journey {name}')
        if journey.get('readOnly') is not True and not allow_mutations:
            raise ValueError(f'Journey {name} requires explicit mutation authorization (--allow-mutations), or a verified readOnly declaration')
        if not journey.get('steps'):
            raise ValueError(f'Journey {name} has no steps')
        for step in journey['steps']:
            if step.get('action') not in {'click', 'fill', 'press', 'selectOption', 'check', 'uncheck'}:
                raise ValueError(f'Unsupported browser action in journey {name}')
            if not step.get('selector'):
                raise ValueError(f'Missing selector in journey {name}')
            if step.get('sourceActionId') and step['sourceActionId'] not in actions:
                raise ValueError(f'Unknown source action in journey {name}')
            response = step.get('expectResponse')
            if not allow_mutations and (RISKY_ACTION.search(step['selector']) or
                    (response and response.get('method') in {'POST', 'PUT', 'PATCH', 'DELETE'})):
                raise ValueError(f'Journey {name} requires explicit authorization (--allow-mutations)')
            if response and (not isinstance(response.get('path'), str) or not response['path'].startswith('/') or '?' in response['path'] or '#' in response['path'] or response.get('method') not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'} or not isinstance(response.get('status'), int)):
                raise ValueError(f'Invalid response assertion in journey {name}')
            linked = step.get('reachedActions', [])
            primary = actions.get(step.get('sourceActionId'), {})
            reachable = set(primary.get('reachableFunctionIds', []))
            seen_actions = {step.get('sourceActionId')}
            for link in linked:
                action_id = link.get('sourceActionId')
                target = actions.get(action_id, {})
                if (action_id in seen_actions or not link.get('sourceReason')
                        or not reachable.intersection(target.get('handlerFunctionIds', []))
                        or not link.get('expect')):
                    raise ValueError(f'Additional actions need a unique source-linked handler and outcome assertion: {name}')
                seen_actions.add(action_id)
            expects = step.get('expect', [])
            if not expects:
                raise ValueError(f'Every journey step needs an observable assertion: {name}')
            for expected in [*expects, *(e for link in linked for e in link['expect'])]:
                if not expected.get('selector') or expected.get('state') not in {'visible', 'hidden', 'enabled', 'disabled', 'text'}:
                    raise ValueError(f'Invalid UI assertion in journey {name}')
                if expected['state'] == 'text' and not isinstance(expected.get('text'), str):
                    raise ValueError('Text assertion requires expected text')
    return journeys


def capture_journeys(page, journeys, routes, theme, staging, local_url, apply_theme, set_phase, network_recorder=None, allow_mutations=False):
    from playwright.sync_api import expect
    observations = []
    for journey in journeys:
        journey_phase = f"journey:{journey['id']}:{theme}"
        set_phase(f'{journey_phase}:navigation')
        route, fixture, target, expected = next((r for r in routes if r[0]['id'] == journey['routeId']), (None, None, None, None))
        if route is None:
            raise ValueError(f"Journey route was skipped: {journey['id']}")
        if network_recorder:
            network_recorder.set_context(route_id=route['id'], journey_id=journey['id'], source_action_id=None, theme_mode=theme)
        page.goto(target, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_url(expected, timeout=30000)
        if fixture.get('readySelector'):
            page.locator(fixture['readySelector']).wait_for(state='visible', timeout=30000)
        apply_theme(page, theme)
        for index, step in enumerate(journey['steps']):
            set_phase(f'{journey_phase}:step:{index + 1}')
            if network_recorder:
                network_recorder.set_context(route_id=route['id'], journey_id=journey['id'], source_action_id=step.get('sourceActionId'), theme_mode=theme)
            before = staging / f"journey_{journey['id']}_{index}_before-{theme}.png"
            before_info = capture_state(page, before)
            locator = page.locator(step['selector'])
            action = step['action']
            if not allow_mutations and needs_confirmation(locator, step['selector'], 15000):
                raise ValueError(f"Journey {journey['id']} requires explicit authorization (--allow-mutations)")
            expected_response = step.get('expectResponse')
            response_context = page.expect_response(lambda r: urlparse(r.url).path == expected_response['path'] and urlparse(r.url).netloc == urlparse(target).netloc and r.request.method == expected_response['method'], timeout=15000) if expected_response else nullcontext()
            requests = nullcontext() if allow_mutations else read_only_requests(page, target)
            with requests, response_context as pending:
                if action in ('click', 'check', 'uncheck'):
                    getattr(locator, action)(timeout=15000)
                elif action == 'fill':
                    locator.fill(step.get('value', ''), timeout=15000)
                elif action == 'press':
                    locator.press(step['value'], timeout=15000)
                elif action == 'selectOption':
                    locator.select_option(step['value'], timeout=15000)
                if not allow_mutations and not expected_response:
                    page.wait_for_timeout(750)
            response_result = None
            if expected_response:
                response = pending.value
                if response.status != expected_response['status']:
                    raise ValueError(f"Unexpected HTTP status in journey {journey['id']}")
                response_result = dict(path=expected_response['path'], method=expected_response['method'], status=response.status)
            linked = step.get('reachedActions', [])
            for expected_state in [*step['expect'], *(e for link in linked for e in link['expect'])]:
                assertion = expect(page.locator(expected_state['selector']))
                state = expected_state['state']
                if state == 'text':
                    assertion.to_have_text(expected_state['text'], timeout=15000)
                else:
                    getattr(assertion, 'to_be_' + state)(timeout=15000)
            if step.get('expectedPath'):
                expected = local_url(step['expectedPath'])
                page.wait_for_url(expected, timeout=30000)
            actual, want = urlparse(page.url), urlparse(expected)
            if (actual.scheme, actual.netloc, actual.path, actual.query) != (want.scheme, want.netloc, want.path, want.query) or actual.fragment:
                raise ValueError(f"Unexpected navigation during journey {journey['id']}")
            after = staging / f"journey_{journey['id']}_{index}_after-{theme}.png"
            after_info = capture_state(page, after)
            observation = dict(
                journeyId=journey['id'],
                routeId=route['id'],
                step=index,
                sourceActionId=step.get('sourceActionId'),
                themeMode=theme,
                passed=True,
                response=response_result,
                assertions=[dict(selector=e['selector'], state=e['state']) for e in step['expect']],
                before=dict(screenshotPath='baselines/' + before.name, **before_info),
                after=dict(screenshotPath='baselines/' + after.name, **after_info),
            )
            observations.append(observation)
            for link in linked:
                observations.append(dict(
                    observation, sourceActionId=link['sourceActionId'], coverageKind='reached-handler',
                    callbackInvoked=False, sourceReason=link['sourceReason'],
                    assertions=[dict(selector=e['selector'], state=e['state']) for e in link['expect']],
                ))
    return observations


class BrowserDriver:
    """Manages Playwright mobile context lifecycle, storage_state, and theme configuration."""

    def __init__(self, settings: DiscoverySettings = None, headed: bool = False, executable_path: str = None, storage_state: str = None):
        self.settings = settings or DiscoverySettings()
        self.headed = headed
        self.executable_path = executable_path
        self.storage_state = storage_state

    def create_mobile_context(self, browser, color_scheme='light'):
        return browser.new_context(
            viewport=dict(width=self.settings.viewport_width, height=self.settings.viewport_height),
            is_mobile=True,
            has_touch=True,
            service_workers='block',
            device_scale_factor=1,
            color_scheme=color_scheme,
            **({'storage_state': self.storage_state} if self.storage_state else {}),
        )


def discover_runtime(base_url, manifest_path, out_dir, gap_report_path=None,
                     storage_state=None, executable_path=None, capture_plan=None,
                     headed=False, interactive_login=False, login_timeout=300, allow_mutations=False,
                     crawl_depth=0, reuse_evidence=False):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright
    from ..exporters.openapi import OpenAPIExporter
    manifest = load(manifest_path)
    plan = load(capture_plan) if capture_plan else {}
    routes = _capture_routes(manifest, plan, base_url)
    journeys = validate_journeys(manifest, plan, allow_mutations)
    crawl_cfg = plan.get('crawl', {})
    max_explore_routes = min(30, max(0, int(crawl_cfg.get('maxPages', 25))))
    max_explore_steps = min(30, max(0, int(crawl_cfg.get('maxSteps', 30))))
    explore_seconds = min(60, max(0, float(crawl_cfg.get('timeoutSeconds', 60))))
    exploration = ExplorationClicks(tuple(route['path'] for route in manifest['routes']))
    probe_results = []
    probed_routes = set()
    probe_time = 0.0
    if interactive_login and not headed:
        raise ValueError('Interactive login requires --headed')
    login = plan.get('login', {})
    if interactive_login and not all(login.get(key) for key in ('path', 'expectedPath', 'readySelector')):
        raise ValueError('Interactive login requires login path, expectedPath and readySelector in the capture plan')
    if not 1 <= login_timeout <= 1800:
        raise ValueError('Login timeout must be between 1 and 1800 seconds')
    gaps = load(gap_report_path) if gap_report_path else dict(schemaVersion='1.0.0', app=manifest['app']['name'], gaps=[])
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    settings = DiscoverySettings(target_url=base_url, max_depth=0, max_pages=max_explore_routes)
    state = DiscoveryState(start_url=base_url, max_depth=0, max_selector_attempts=settings.max_selector_attempts)
    driver = BrowserDriver(settings=settings, headed=headed, executable_path=executable_path, storage_state=storage_state)
    report_path = out / 'runtime-discovery.json'
    run_status = out / 'runtime-discovery-run.json'
    key = evidence_key(manifest, plan, base_url, storage_state, executable_path, allow_mutations, capture_plan)
    route_keys = {route['id']: fingerprint(fixture) for route, fixture, _, _ in routes}
    captures, observations, records, reused_journeys = (
        reuse_runtime(report_path, key, journeys, route_keys) if reuse_evidence and not interactive_login
        else ([], [], [], set())
    )
    reused_routes = {(c['routeId'], c['themeMode']) for c in captures}
    network_recorder = NetworkContractRecorder(base_url, state=state)
    network_recorder.records.extend(records)
    initial_links = {c['landingPath']: c['ui'].get('discoveredLinks', []) for c in captures
                     if c['themeMode'] == 'light'}
    journey_failures = []
    route_failures = []
    sitemap = {}

    def apply_theme(page, theme):
        selector = plan.get('themeSelectors', {}).get(theme)
        if selector:
            page.locator(selector).click(timeout=15000)

    phase = 'browser-launch'

    def set_phase(value):
        nonlocal phase
        phase = value
        write_json(run_status, dict(status='in-progress', viewport=dict(width=390, height=844),
                                     captures=[], phase=phase))

    set_phase(phase)
    try:
        with tempfile.TemporaryDirectory(prefix='.runtime-', dir=out) as staging, sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not headed, **({'executable_path': executable_path} if executable_path else {}))
            try:
                context = driver.create_mobile_context(browser, color_scheme='light')
                try:
                    page = context.new_page()
                    if interactive_login:
                        set_phase('interactive-login')
                        print('Capture browser opened. Sign in there; capture starts after the protected ready selector appears.', flush=True)
                        page.goto(_local_url(base_url, login['path'], plan.get('allowedQueryParams')), wait_until='domcontentloaded')
                        page.wait_for_url(_local_url(base_url, login['expectedPath'], plan.get('allowedQueryParams')), timeout=login_timeout * 1000)
                        page.locator(login['readySelector']).wait_for(state='visible', timeout=login_timeout * 1000)
                    for theme in ('light', 'dark'):
                        if theme == 'dark':
                            page.close()
                            page = context.new_page()
                        page.emulate_media(color_scheme=theme)
                        storage_key = plan.get('themeStorageKey')
                        if storage_key:
                            script = 'localStorage.setItem(%s, %s)' % (json.dumps(storage_key), json.dumps(theme))
                            page.add_init_script(script)
                        page.on('response', network_recorder.on_response)
                        try:
                            for route, fixture, target, expected in routes:
                                if (route['id'], theme) in reused_routes:
                                    continue
                                set_phase(route['id'] + ':' + theme + ':navigation')
                                network_recorder.set_context(route_id=route['id'], journey_id=None, source_action_id=None, theme_mode=theme)
                                requests = []

                                def on_request(req):
                                    if req.resource_type in ('fetch', 'xhr', 'websocket'):
                                        requests.append(req.resource_type)

                                page.on('request', on_request)
                                try:
                                    page.goto(target, wait_until='domcontentloaded', timeout=30000)
                                    if fixture.get('expectedPath') or fixture.get('readySelector'):
                                        page.wait_for_url(expected, timeout=30000)
                                    actual = urlparse(page.url)
                                    want = urlparse(expected)
                                    if (actual.scheme, actual.netloc, actual.path, actual.query) != (want.scheme, want.netloc, want.path, want.query) or actual.fragment:
                                        raise ValueError(f"Baseline capture redirected away from {route['id']}; authenticate and configure expectedPath explicitly")
                                    if fixture.get('readySelector'):
                                        set_phase(route['id'] + ':' + theme + ':ready-selector')
                                    wait_for_deterministic_settle(page, fixture.get('readySelector'), timeout_ms=30000 if fixture.get('readySelector') else 15000)
                                    apply_theme(page, theme)
                                    filename = route['id'].lower() + '-' + theme + '.png'
                                    set_phase(route['id'] + ':' + theme + ':screenshot')
                                    file = Path(staging) / filename
                                    ui_state = capture_state(page, file)
                                    if theme == 'light':
                                        initial_links[want.path] = ui_state.get('ui', {}).get('discoveredLinks', [])
                                    metrics = page.evaluate(METRICS)
                                    if (metrics['viewportWidth'], metrics['viewportHeight']) != (390, 844):
                                        raise ValueError('Runtime viewport must be exactly 390x844')
                                    screens = [s['id'] for s in manifest['screens'] if route['id'] in s.get('routeIds', [])]
                                    redirected = urlparse(target).path != want.path
                                    baseline_screens = [] if redirected else screens
                                    for screen_id in baseline_screens:
                                        screen_file = Path(staging) / (screen_id.lower() + '-' + theme + '.png')
                                        if not screen_file.exists():
                                            screen_file.write_bytes(file.read_bytes())
                                    if metrics['hasHorizontalOverflow'] and theme == 'light':
                                        gap_id = 'GAP_' + route['id'] + '_RUNTIME_OVERFLOW'
                                        if not any(g['id'] == gap_id for g in gaps['gaps']):
                                            gaps['gaps'].append(dict(id=gap_id, manifestRef=route['id'], sourceFile=route['sourceFile'], category='wide-table', description='Route overflows the 390px viewport', webHasMobileView=False, webMobileAlternative=None, status='unresolved-ask-user', resolution=None))
                                    snapshot = ScreenSnapshot(
                                        route_id=route['id'],
                                        screen_ids=baseline_screens,
                                        expected_screen_ids=screens,
                                        path=urlparse(target).path,
                                        landing_path=want.path,
                                        redirected=redirected,
                                        theme_mode=theme,
                                        screenshot_path='baselines/' + filename,
                                        screenshot_sha256=ui_state['screenshotSha256'],
                                        dom_metrics=metrics,
                                        ui=ui_state['ui'],
                                        network_calls_count=len(requests),
                                    )
                                    state.screens.append(snapshot)
                                    captures.append(snapshot.to_capture_dict())
                                    probes = fixture.get('explore', [])
                                    template = route['path']
                                    if (theme == 'light' and probes and exploration.route(page) == template
                                            and template not in probed_routes
                                            and len(probed_routes) < max_explore_routes):
                                        probed_routes.add(template)
                                        for selector in probes:
                                            remaining = explore_seconds - probe_time
                                            if remaining < 0.01 or len(probe_results) >= max_explore_steps:
                                                break
                                            started = monotonic()
                                            try:
                                                timeout = min(2000, int(remaining * 1000 / 4))
                                                if needs_confirmation(page.locator(selector), selector, timeout):
                                                    outcome = 'approval_required'
                                                else:
                                                    with read_only_requests(page, base_url):
                                                        changed = exploration.click(page, selector, timeout)
                                                    outcome = 'blocked' if changed is None else 'changed' if changed else 'no-op'
                                            except PlaywrightTimeout:
                                                outcome = 'timeout'
                                            finally:
                                                probe_time += monotonic() - started
                                            probe_results.append(dict(routeId=route['id'], outcome=outcome))
                                            if exploration.route(page) != template:
                                                break
                                except (ValueError, PlaywrightTimeout) as error:
                                    if route['id'] == plan.get('preflightRouteId') and theme == 'light':
                                        raise
                                    route_failures.append(dict(routeId=route['id'], themeMode=theme,
                                                                phase=phase, failureType=type(error).__name__))
                                finally:
                                    page.remove_listener('request', on_request)
                            for journey in journeys:
                                if (journey['id'], theme) in reused_journeys:
                                    continue
                                with tempfile.TemporaryDirectory(dir=staging) as journey_dir:
                                    try:
                                        result = capture_journeys(
                                            page, [journey], routes, theme, Path(journey_dir),
                                            lambda path: _local_url(base_url, path, plan.get('allowedQueryParams')),
                                            apply_theme, set_phase, network_recorder, allow_mutations,
                                        )
                                    except (AssertionError, ValueError, PlaywrightTimeout) as error:
                                        journey_failures.append(dict(journeyId=journey['id'], themeMode=theme,
                                                                     phase=phase, failureType=type(error).__name__))
                                        continue
                                    observations.extend(result)
                                    for file in Path(journey_dir).glob('*.png'):
                                        file.replace(Path(staging) / file.name)
                        finally:
                            page.remove_listener('response', network_recorder.on_response)
                    set_phase('sitemap-crawl')
                    sitemap = crawl_sitemap(
                        page,
                        [route['path'] for route, _, _, _ in routes],
                        lambda path: _local_url(base_url, path, plan.get('allowedQueryParams')),
                        manifest['routes'],
                        max_pages=max_explore_routes,
                        initial_links=initial_links,
                        state=state,
                    )
                    sitemap['exploration'] = dict(maxSteps=max_explore_steps, timeoutSeconds=explore_seconds,
                                                  results=probe_results)
                    if plan.get('requireThemeColorChange', True):
                        for route, _, _, _ in routes:
                            set_phase(route['id'] + ':theme-verification')
                            pair = [c for c in captures if c['routeId'] == route['id']]
                            if len(pair) != 2:
                                continue
                            styles = [json.dumps(dict(background=c['domMetrics']['backgroundColor'], text=c['domMetrics']['textColor'], controls=[e['styles'] for e in c['ui']['elements']]), sort_keys=True) for c in pair]
                            if len(set(styles)) != 2:
                                raise ValueError(f"No effective light/dark color change for {route['id']}")
                finally:
                    context.close()
            finally:
                browser.close()
            set_phase('publish-baselines')
            baselines = out / 'baselines'
            baselines.mkdir(parents=True, exist_ok=True)
            managed = {file.name for file in Path(staging).glob('*.png')}
            history = out / 'baseline-history' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            for name in managed:
                old = baselines / name
                if old.exists():
                    history.mkdir(parents=True, exist_ok=True)
                    old.replace(history / name)
            for file in Path(staging).glob('*.png'):
                file.replace(baselines / file.name)
        captured_screens = {screen for capture in captures for screen in capture['screenIds']}
        missing = sorted({s['id'] for s in manifest['screens']} - captured_screens)
        skipped = {key: value['skipReason'] for key, value in plan.get('routes', {}).items() if value.get('skipReason')}
        source_actions = {a['id'] for a in manifest.get('behavior', {}).get('actions', [])}
        covered = {a for a in source_actions if all(any(o['sourceActionId'] == a and o['themeMode'] == theme and o['passed'] for o in observations) for theme in ('light', 'dark'))}
        missing_actions = sorted(source_actions - covered)
        status = 'partial' if missing or skipped or missing_actions or journey_failures or route_failures or not plan.get('requireThemeColorChange', True) else 'ok'
        state.is_finished = True
        api_contracts = OpenAPIExporter.build_contracts(manifest, manifest.get('behavior', {}), network_recorder.records)
        api_contracts_path = OpenAPIExporter.export(manifest, manifest.get('behavior', {}), network_recorder.records, out / 'api-data-contracts.json')
        write_json(report_path, dict(schemaVersion='2.0.0', manifestContentSha256=discovery_fingerprint(manifest), manifestSha256=digest(manifest_path), observations=observations, missingActionIds=missing_actions, themeMechanism='app-toggle' if plan.get('themeSelectors') else 'app-storage' if plan.get('themeStorageKey') else 'system-color-scheme', status=status, viewport=dict(width=390, height=844), baseUrl=base_url,
                                     captures=captures, missingScreenIds=missing, skippedRoutes=skipped,
                                     sitemap=sitemap, journeyFailures=journey_failures, routeFailures=route_failures,
                                     themeVerificationEnabled=plan.get('requireThemeColorChange', True),
                                     evidenceKey=key, routeKeys=route_keys, journeyKeys={j['id']: fingerprint(j) for j in journeys},
                                     networkRecords=network_recorder.records,
                                     reusedRouteCaptures=len(reused_routes), reusedJourneyThemes=len(reused_journeys),
                                     networkContractsSummary=dict(
                                         observedResponses=len(network_recorder.records),
                                         uiStateQueries=len(api_contracts['uiStateQueries']),
                                         userInteractionMutations=len(api_contracts['userInteractionMutations']),
                                         apiDataContractsPath=str(api_contracts_path),
                                     ),
                                     flowParityVerified=False))
        write_json(run_status, dict(status=status, journeyFailures=journey_failures, routeFailures=route_failures))
        if gap_report_path:
            write_json(gap_report_path, gaps)
        return dict(runtimeReportPath=str(report_path), capturesCount=len(captures), captureStatus=status,
                    missingScreenIds=missing, missingActionIds=missing_actions,
                    apiDataContractsPath=str(api_contracts_path), flowParityVerified=False)
    except Exception as error:
        failure = dict(status='failed', viewport=dict(width=390, height=844), captures=[],
                       failureType=type(error).__name__, phase=phase, message='Runtime capture failed')
        write_json(run_status, failure)
        if not report_path.exists():
            write_json(report_path, failure)
        if isinstance(error, ValueError):
            raise
        raise RuntimeError('Runtime capture failed during ' + phase + ' (' + type(error).__name__ + '); no new baselines published') from None
