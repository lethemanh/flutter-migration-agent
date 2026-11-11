"""Tests for hybrid discovery architecture: config, core state machine, browser driver/interceptor/dom, agent loop/tools, parsers, and exporters."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from twake_migrate.agent import DiscoveryAgentLoop, Tool, ToolRegistry
from twake_migrate.browser import NetworkContractRecorder, crawl_sitemap
from twake_migrate.config import DiscoverySettings
from twake_migrate.core import DiscoveryState, LOOP_GUARD_ERROR_MESSAGE
from twake_migrate.exporters import (
    MobileSpecExporter,
    OpenAPIExporter,
    TypeScriptExporter,
    build_api_data_contracts,
)
from twake_migrate.parsers import (
    infer_json_schema,
    merge_json_schemas,
    normalize_endpoint_path,
)


def test_infer_and_merge_json_schemas_redact_secrets_and_preserve_structure():
    payload = {
        'id': '550e8400-e29b-41d4-a716-446655440000',
        'email': 'alice@linagora.com',
        'createdAt': '2026-11-04T10:20:30Z',
        'avatarUrl': 'https://twake.example/avatar.png',
        'accessToken': 'super-secret-jwt-value',
        'count': 3,
        'tags': ['work', 'vip'],
    }
    schema = infer_json_schema(payload)
    serialized = json.dumps(schema)
    assert 'super-secret-jwt-value' not in serialized
    assert 'alice@linagora.com' not in serialized
    assert schema['properties']['id'] == {'type': 'string', 'format': 'uuid'}
    assert schema['properties']['email'] == {'type': 'string', 'format': 'email'}
    assert schema['properties']['createdAt'] == {'type': 'string', 'format': 'date-time'}
    assert schema['properties']['avatarUrl'] == {'type': 'string', 'format': 'uri'}
    assert schema['properties']['accessToken'] == {'type': 'string', 'format': 'redacted'}
    assert schema['properties']['count'] == {'type': 'integer'}

    second = infer_json_schema({'id': '550e8400-e29b-41d4-a716-446655440000', 'count': 4.5, 'extra': True})
    merged = merge_json_schemas(schema, second)
    assert merged['required'] == ['count', 'id']
    assert merged['properties']['count'] == {'type': 'number'}
    assert merged['properties']['extra'] == {'type': 'boolean'}


def test_network_contract_recorder_and_exporters(tmp_path: Path):
    assert normalize_endpoint_path('/api/contacts/550e8400-e29b-41d4-a716-446655440000/books/42') == '/api/contacts/{id}/books/{id}'
    state = DiscoveryState(start_url='http://localhost:5000')
    recorder = NetworkContractRecorder('http://localhost:5000', state=state)
    recorder.set_context(route_id='ROUTE_CONTACTS', journey_id=None, source_action_id=None, theme_mode='light')

    get_resp = SimpleNamespace(
        url='http://localhost:5000/api/contacts/42?limit=20&access_token=secret',
        status=200,
        headers={'content-type': 'application/json; charset=utf-8'},
        request=SimpleNamespace(resource_type='fetch', method='GET', post_data=None),
        json=lambda: {'items': [{'id': '1', 'displayName': 'Alice'}]},
    )
    recorder.on_response(get_resp)

    recorder.set_context(route_id='ROUTE_CONTACTS', journey_id='create-contact', source_action_id='ACTION_SAVE', theme_mode='light')
    post_resp = SimpleNamespace(
        url='http://localhost:5000/api/contacts',
        status=201,
        headers={'content-type': 'application/json'},
        request=SimpleNamespace(
            resource_type='xhr',
            method='POST',
            post_data=json.dumps({'displayName': 'Bob', 'password': 'hidden'}),
        ),
        json=lambda: {'id': '2', 'displayName': 'Bob'},
    )
    recorder.on_response(post_resp)

    manifest = {'app': {'name': 'contacts', 'version': '1.0.0'}, 'apiCalls': []}
    contracts = build_api_data_contracts(manifest, {}, recorder.records)
    assert len(contracts['uiStateQueries']) == 1
    assert len(contracts['userInteractionMutations']) == 1
    assert len(state.captured_apis) == 2

    openapi_file = OpenAPIExporter.export_from_state(state, manifest, {}, tmp_path / 'openapi.json')
    assert openapi_file.is_file()

    ts_file = TypeScriptExporter.export(state.captured_apis, tmp_path / 'types' / 'api.d.ts')
    ts_code = ts_file.read_text()
    assert 'export interface GetApiContactsByIdResponse' in ts_code
    assert 'export interface PostApiContactsRequest' in ts_code
    assert 'displayName: string;' in ts_code


def test_sitemap_canonicalizes_routes_without_following_links():
    def unexpected_navigation(*args, **kwargs):
        raise AssertionError('Discovered links must never trigger navigation')

    page = SimpleNamespace(goto=unexpected_navigation)
    routes = [{'path': '/contacts'}, {'path': '/contacts/:id'}, {'path': '/contacts/new'}]
    state = DiscoveryState(start_url='http://localhost:5000')
    result = crawl_sitemap(
        page, ['/contacts?page=2', '/contacts/123', '/contacts/456'], unexpected_navigation, routes,
        max_depth=3,
        initial_links={'/contacts': ['/contacts/123?sort=asc', '/contacts/456', '/contacts/new',
                                     '/settings?page=3', '//evil.example/phish']},
        state=state,
    )
    assert result['visitedUrls'] == ['/contacts', '/contacts/:id']
    assert result['allDiscoveredPaths'] == ['/contacts', '/contacts/:id', '/contacts/new', '/settings']
    assert result['unmappedPaths'] == ['/settings']
    assert len(result['discoveredLinks']) == 3
    assert state.visited_urls == {'/contacts', '/contacts/:id'}


def test_agent_loop_detects_no_op_selector_loops_and_compresses_context(tmp_path: Path):
    page = SimpleNamespace(
        url='http://localhost:5000/contacts',
        goto=lambda url, **kw: None,
        wait_for_load_state=lambda state, **kw: None,
        evaluate=lambda script: {'accessibilityTree': [{'role': 'button', 'name': 'Dead Button'}], 'elements': [1], 'discoveredLinks': []},
        context=SimpleNamespace(route=lambda *args: None, unroute=lambda *args: None),
        locator=lambda sel: SimpleNamespace(
            evaluate=lambda *args, **kw: False,
            wait_for=lambda **kw: None,
            click=lambda **kw: None,
            fill=lambda val, **kw: None,
        ),
    )
    state = DiscoveryState(start_url='http://localhost:5000/contacts', max_selector_attempts=2)
    settings = DiscoverySettings(sliding_window_size=2, max_selector_attempts=2)
    checkpoint = tmp_path / 'discovery-checkpoint.json'
    loop = DiscoveryAgentLoop(page=page, state=state, settings=settings, checkpoint_path=checkpoint,
                              benign_selectors={'/contacts': {'click': ['#dead-btn', '#delete']}})

    denied = loop.run(lambda *_: {'name': 'click', 'arguments': {'selector': '#delete'}})
    assert len(denied) == 1
    assert denied[0]['result']['status'] == 'approval_required'

    # A no-op click blocks the element immediately.
    r1 = loop.step(lambda obs, msgs, tools: {'name': 'click', 'arguments': {'selector': '#dead-btn'}})
    r2 = loop.step(lambda obs, msgs, tools: {'name': 'click', 'arguments': {'selector': '#dead-btn'}})
    r3 = loop.step(lambda obs, msgs, tools: {'name': 'click', 'arguments': {'selector': '#dead-btn'}})
    assert r1['result']['status'] == 'ok'
    assert r2['result'] == {'status': 'error', 'message': LOOP_GUARD_ERROR_MESSAGE}
    assert r3['result']['message'] == 'Route interaction budget exhausted or outside the sitemap.'

    # Verify resilient disk checkpointing and sliding-window context compression
    assert checkpoint.is_file()
    dumped = json.loads(checkpoint.read_text())
    assert '#dead-btn' in dumped['visitedSelectors']

    compressed = loop.get_compressed_messages('System prompt')
    assert compressed[0] == {'role': 'system', 'content': 'System prompt'}
    assert len(compressed) == 3
    assert all("Previous actions summary:" not in m["content"] for m in compressed)
    assert 'Latest screen state:' in compressed[-1]['content']

    # Verify async ToolRegistry execution as well
    registry = ToolRegistry()
    registry.register(Tool(name='ping', description='Ping tool', parameters={'type': 'object'}, execute=lambda x=1: x + 1))
    assert registry.get_definitions()[0]['function']['name'] == 'ping'
    assert asyncio.run(registry.run('ping', x=5)) == 6


def test_exploration_click_guard_uses_element_identity_and_ignores_query_changes():
    from twake_migrate.browser.dom import ExplorationClicks

    hits = []
    page = SimpleNamespace(url='http://localhost:5000/contacts/123')
    def click(**kwargs):
        hits.append(True)
        page.url = 'http://localhost:5000/contacts/123?page=2'

    page.locator = lambda selector: SimpleNamespace(evaluate=lambda *args, **kw: 'same-element', click=click)
    guard = ExplorationClicks(('/contacts/:id',))
    assert guard.click(page, '#button', 1000) is False
    assert guard.click(page, 'button', 1000) is None
    assert len(hits) == 1


def test_exploration_loop_enforces_step_limit_and_interrupts_slow_decision():
    from time import sleep

    page = SimpleNamespace(url='http://localhost:5000', evaluate=lambda script: {})
    loop = DiscoveryAgentLoop(page, DiscoveryState(start_url=page.url))
    steps = loop.run(lambda *_: {'name': 'scroll'}, max_steps=100)
    assert len(steps) == 30
    assert loop.state.is_finished

    loop = DiscoveryAgentLoop(page, DiscoveryState(start_url=page.url))
    steps = loop.run(lambda *_: sleep(2), timeout_seconds=0.01)
    assert steps == [{'result': {'status': 'stopped', 'reason': 'time-budget'}}]


def test_discover_static_emits_all_four_structured_specs(tmp_path: Path):
    from twake_migrate.parsers import discover_static
    web = tmp_path / 'web'
    src = web / 'src'
    src.mkdir(parents=True)
    (web / 'package.json').write_text(json.dumps({
        'name': 'twake-contacts',
        'version': '1.2.0',
        'dependencies': {
            '@linagora/twake-mui': '1.0.0',
            '@reduxjs/toolkit': '2.0.0',
            'react-router-dom': '6.0.0',
        },
    }))
    (src / 'ContactsSlice.ts').write_text('''
import { createSlice } from '@reduxjs/toolkit';
const initialState = { items: [], loading: false, selectedId: null };
export const contactsSlice = createSlice({
  name: 'contacts',
  initialState,
  reducers: {
    selectContact(state, action) { state.selectedId = action.payload; },
  },
});
''')
    (src / 'AppRoutes.tsx').write_text('''
import React from 'react';
import { Route, Routes } from 'react-router-dom';
import { ContactsPage } from './ContactsPage';
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/contacts" element={<ContactsPage />} />
    </Routes>
  );
}
''')
    (src / 'ContactsPage.tsx').write_text('''
import React from 'react';
import { VirtualizedTable, Dialog, Drawer, useBreakpoints } from '@linagora/twake-mui';
const EMAIL_RE = /^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/;
export function ContactsPage() {
  const { isMobile } = useBreakpoints();
  const saveTheme = (theme: string) => {
    localStorage.setItem('theme', theme);
    return EMAIL_RE.test('a@b.co');
  };
  return (
    <div>
      <Drawer open={isMobile} />
      <VirtualizedTable columns={[]} />
      <Dialog open={false}>
        <input name="email" type="email" required minLength={3} onChange={() => saveTheme('dark')} />
      </Dialog>
    </div>
  );
}
''')
    out = tmp_path / 'out'
    res = discover_static(web, out)
    assert Path(res['screenInventoryPath']).is_file()
    assert Path(res['uiComponentBreakdownPath']).is_file()
    assert Path(res['apiDataContractsPath']).is_file()
    assert Path(res['stateValidationMatrixPath']).is_file()

    state_matrix = json.loads(Path(res['stateValidationMatrixPath']).read_text())
    assert len(state_matrix['stores']) == 1
    assert state_matrix['stores'][0]['name'] == 'contacts'
    assert state_matrix['stores'][0]['initialStateKeys'] == ['items', 'loading', 'selectedId']
    assert 'selectContact' in state_matrix['stores'][0]['reducers']
    assert any(r['kind'] == 'regex-literal' for r in state_matrix['validationRules'])
    assert any(r['kind'] == 'ui-field-constraint' and r['fieldName'] == 'email' for r in state_matrix['validationRules'])
    assert any(p['mechanism'] == 'localStorage' and p['storageKey'] == 'theme' for p in state_matrix['persistenceRequirements'])

    breakdown = json.loads(Path(res['uiComponentBreakdownPath']).read_text())
    assert breakdown['summary']['tablesCount'] >= 1
    assert breakdown['summary']['modalsCount'] >= 1
    assert breakdown['summary']['sidebarsCount'] >= 1

    screen_inventory = json.loads(Path(res['screenInventoryPath']).read_text())
    md_path = MobileSpecExporter.export(screen_inventory, out / 'docs' / 'screens.md', breakdown, state_matrix)
    assert md_path.is_file()
    assert 'Mobile Routing Stack' in md_path.read_text()


def test_unattended_request_guard_blocks_writes_and_other_origins():
    from twake_migrate.browser.permissions import read_only_requests

    handlers = {}
    context = SimpleNamespace(
        route=lambda pattern, handler: handlers.update({pattern: handler}),
        unroute=lambda pattern, handler: handlers.pop(pattern),
    )
    page = SimpleNamespace(context=context)
    origin = 'http://localhost:5000'

    def request(method, url):
        result = []
        handlers['**/*'](SimpleNamespace(
            request=SimpleNamespace(method=method, url=url),
            fallback=lambda: result.append('allowed'),
            abort=lambda: result.append('blocked'),
        ))
        return result[0]

    with read_only_requests(page, origin):
        assert request('GET', origin + '/contacts') == 'allowed'
        assert request('POST', origin + '/contacts') == 'blocked'
        assert request('GET', 'https://example.com/contacts') == 'blocked'
    assert handlers == {}
