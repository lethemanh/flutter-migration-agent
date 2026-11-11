"""Interactive browser primitive tools with deterministic throttling and loop-detection guards."""
from pathlib import Path
from urllib.parse import urlsplit
from ...browser.permissions import needs_confirmation, read_only_requests, same_origin
from ...browser.dom import UI_SNAPSHOT, ExplorationClicks, canonical_route, capture_state, wait_for_deterministic_settle
from ...config.settings import DiscoverySettings
from ...core.state import DiscoveryState, LOOP_GUARD_ERROR_MESSAGE
from ...core.types import AgentAction
from .base import Tool, ToolRegistry


def register_browser_tools(registry: ToolRegistry, page, state: DiscoveryState, settings: DiscoverySettings = None, route_targets=None, benign_selectors=None, screenshot_root=None) -> ToolRegistry:
    """Register navigate, click, fill, scroll, go_back, and take_screenshot primitives."""
    cfg = settings or DiscoverySettings(max_selector_attempts=state.max_selector_attempts)

    targets = dict(route_targets) if route_targets is not None else {urlsplit(state.start_url).path or '/': state.start_url}
    clicks = ExplorationClicks(tuple(targets))
    interactions = {}

    def approval_required():
        return {'status': 'approval_required',
                'message': 'Use an explicitly authorized scripted journey for this interaction.'}

    def permitted(action, selector):
        route = clicks.route(page)
        return (
            same_origin(page.url, state.start_url)
            and selector in (benign_selectors or {}).get(route, {}).get(action, ())
            and not needs_confirmation(page.locator(selector), selector, cfg.action_timeout_ms)
        )

    def navigate(url: str):
        target = urlsplit(url)
        origin = urlsplit(state.start_url)
        template = canonical_route(url, tuple(targets))
        fixture = targets.get(template)
        if (not fixture or (target.scheme, target.netloc) != (origin.scheme, origin.netloc)
                or not same_origin(fixture, state.start_url)
                or target.path != urlsplit(fixture).path or template in state.visited_urls):
            return {'status': 'error', 'message': 'Choose an unvisited manifest route fixture.'}
        state.visited_urls.add(template)
        page.goto(fixture, wait_until='domcontentloaded', timeout=cfg.navigation_timeout_ms)
        wait_for_deterministic_settle(page, timeout_ms=cfg.network_idle_timeout_ms)
        state.action_history.append(AgentAction(action='navigate', url=template, state_changed=True, status='ok'))
        return {'status': 'ok', 'url': template}

    def consume_interaction():
        route = clicks.route(page)
        actual, origin = urlsplit(page.url), urlsplit(state.start_url)
        if ((actual.scheme, actual.netloc) != (origin.scheme, origin.netloc)
                or route not in targets or actual.path != urlsplit(targets[route]).path
                or interactions.get(route, 0) >= 3):
            return False
        state.visited_urls.add(route)
        interactions[route] = interactions.get(route, 0) + 1
        return True

    def click(selector: str):
        if not consume_interaction():
            return {'status': 'error', 'message': 'Route interaction budget exhausted or outside the sitemap.'}
        if not permitted('click', selector):
            return approval_required()
        with read_only_requests(page, state.start_url):
            changed = clicks.click(page, selector, cfg.action_timeout_ms)
        if changed is None:
            state.action_history.append(AgentAction(action='click', selector=selector, status='error',
                                                    message=LOOP_GUARD_ERROR_MESSAGE))
            return {'status': 'error', 'message': LOOP_GUARD_ERROR_MESSAGE}
        state.visited_selectors.add(selector)
        state.action_history.append(AgentAction(action='click', selector=selector, state_changed=changed, status='ok'))
        return {'status': 'ok', 'selector': selector, 'stateChanged': changed}

    def fill(selector: str, value: str):
        if not consume_interaction():
            return {'status': 'error', 'message': 'Route interaction budget exhausted or outside the sitemap.'}
        if not permitted('fill', selector):
            return approval_required()
        with read_only_requests(page, state.start_url):
            page.locator(selector).fill(value, timeout=cfg.action_timeout_ms)
            page.wait_for_timeout(min(750, cfg.action_timeout_ms))
        state.visited_selectors.add(selector)
        state.action_history.append(AgentAction(action='fill', selector=selector, value='<redacted>', state_changed=True, status='ok'))
        return {'status': 'ok', 'selector': selector}

    def scroll(direction: str = 'down', amount: int = 400):
        if not consume_interaction():
            return {'status': 'error', 'message': 'Route interaction budget exhausted or outside the sitemap.'}
        delta = abs(amount) if direction == 'down' else -abs(amount)
        if hasattr(page, 'evaluate'):
            page.evaluate(f'window.scrollBy(0, {int(delta)})')
        state.action_history.append(AgentAction(action='scroll', value=f'{direction}:{amount}', state_changed=True, status='ok'))
        return {'status': 'ok', 'direction': direction, 'amount': amount}

    def take_screenshot(path: str):
        if not screenshot_root or not same_origin(page.url, state.start_url):
            return {'status': 'error', 'message': 'Screenshot requires the configured origin and artifact directory.'}
        root = Path(screenshot_root).resolve()
        output = (root / path).resolve()
        if not output.is_relative_to(root) or output.exists() or output.suffix.lower() != '.png':
            return {'status': 'error', 'message': 'Choose a new PNG path inside the artifact directory.'}
        info = capture_state(page, output)
        state.action_history.append(AgentAction(action='take_screenshot', value=path, state_changed=False, status='ok'))
        return {'status': 'ok', 'screenshotPath': str(output), **info}

    registry.register(Tool(
        name='navigate',
        description='Navigate to a local application route and wait for network idle.',
        parameters={'type': 'object', 'required': ['url'], 'properties': {'url': {'type': 'string'}}},
        execute=navigate,
    ))
    registry.register(Tool(
        name='open_link',
        description='Open a configured manifest route URL directly without a click or confirmation.',
        parameters={'type': 'object', 'required': ['url'], 'properties': {'url': {'type': 'string'}}},
        execute=navigate,
    ))
    registry.register(Tool(
        name='click',
        description='Click an interactive element by CSS/ARIA selector with loop-detection guard.',
        parameters={'type': 'object', 'required': ['selector'], 'properties': {'selector': {'type': 'string'}}},
        execute=click,
    ))
    registry.register(Tool(
        name='click_element',
        description='Alias for click: click an interactive element by selector.',
        parameters={'type': 'object', 'required': ['selector'], 'properties': {'selector': {'type': 'string'}}},
        execute=click,
    ))
    registry.register(Tool(
        name='fill',
        description='Fill an input field by selector.',
        parameters={
            'type': 'object',
            'required': ['selector', 'value'],
            'properties': {'selector': {'type': 'string'}, 'value': {'type': 'string'}},
        },
        execute=fill,
    ))
    registry.register(Tool(
        name='fill_input',
        description='Alias for fill: fill an input field by selector.',
        parameters={
            'type': 'object',
            'required': ['selector', 'value'],
            'properties': {'selector': {'type': 'string'}, 'value': {'type': 'string'}},
        },
        execute=fill,
    ))
    registry.register(Tool(
        name='scroll',
        description='Scroll the mobile viewport up or down.',
        parameters={
            'type': 'object',
            'properties': {'direction': {'type': 'string', 'enum': ['up', 'down']}, 'amount': {'type': 'integer'}},
        },
        execute=scroll,
    ))
    registry.register(Tool(
        name='take_screenshot',
        description='Capture a verified 390x844 mobile screenshot and A11y snapshot.',
        parameters={'type': 'object', 'required': ['path'], 'properties': {'path': {'type': 'string'}}},
        execute=take_screenshot,
    ))
    def get_screen_state():
        if not same_origin(page.url, state.start_url):
            return {'status': 'error', 'message': 'Screen is outside the configured origin.'}
        return page.evaluate(UI_SNAPSHOT)

    def extract_apis():
        return {'status': 'ok', 'apis': [record.to_record() for record in state.captured_apis.values()]}

    for name, execute in [('get_screen_state', get_screen_state), ('extract_apis', extract_apis)]:
        registry.register(Tool(name=name, description=name.replace('_', ' '),
                               parameters={'type': 'object', 'properties': {}}, execute=execute))
    return registry

