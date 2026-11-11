"""OpenAPI 3.1.0 and API & Data Contract exporter."""
from pathlib import Path
from ..core.common import write_json
from ..parsers.schema_infer import merge_json_schemas


def build_api_data_contracts(manifest, behavior, runtime_records=None):
    """Build API & Data Contracts combining static AST API calls with runtime-intercepted GET/POST/PUT/DELETE schemas."""
    runtime_records = runtime_records or []
    grouped = {}
    for rec in runtime_records:
        key = (rec['method'], rec['pathTemplate'])
        entry = grouped.setdefault(key, {
            'method': rec['method'],
            'pathTemplate': rec['pathTemplate'],
            'observedPaths': set(),
            'queryParamKeys': set(),
            'category': rec['category'],
            'statuses': set(),
            'contentTypes': set(),
            'routeIds': set(),
            'journeyIds': set(),
            'sourceActionIds': set(),
            'requestSchema': None,
            'responseSchema': None,
        })
        entry['observedPaths'].add(rec['path'])
        entry['queryParamKeys'].update(rec.get('queryParamKeys', []))
        if rec.get('status'):
            entry['statuses'].add(rec['status'])
        if rec.get('contentType'):
            entry['contentTypes'].add(rec['contentType'])
        if rec.get('routeId'):
            entry['routeIds'].add(rec['routeId'])
        if rec.get('journeyId'):
            entry['journeyIds'].add(rec['journeyId'])
        if rec.get('sourceActionId'):
            entry['sourceActionIds'].add(rec['sourceActionId'])
        if rec.get('requestSchema'):
            entry['requestSchema'] = merge_json_schemas(entry['requestSchema'], rec['requestSchema'])
        if rec.get('responseSchema'):
            entry['responseSchema'] = merge_json_schemas(entry['responseSchema'], rec['responseSchema'])

    ui_state_queries = []
    mutation_contracts = []
    openapi_paths = {}

    for (method, path_template), info in sorted(grouped.items()):
        contract = {
            'method': method,
            'pathTemplate': path_template,
            'observedPaths': sorted(info['observedPaths']),
            'queryParamKeys': sorted(info['queryParamKeys']),
            'category': info['category'],
            'statuses': sorted(info['statuses']),
            'contentTypes': sorted(info['contentTypes']),
            'routeIds': sorted(info['routeIds']),
            'journeyIds': sorted(info['journeyIds']),
            'sourceActionIds': sorted(info['sourceActionIds']),
            'requestSchema': info['requestSchema'],
            'responseSchema': info['responseSchema'],
        }
        if info['category'] == 'ui-state-query':
            ui_state_queries.append(contract)
        else:
            mutation_contracts.append(contract)

        path_item = openapi_paths.setdefault(path_template, {})
        responses_spec = {}
        for st in sorted(info['statuses']) or [200]:
            resp_entry = {'description': f'Observed HTTP {st} response'}
            if info['responseSchema']:
                resp_entry['content'] = {'application/json': {'schema': info['responseSchema']}}
            responses_spec[str(st)] = resp_entry
        op_spec = {
            'summary': f"Observed {method} {path_template} ({info['category']})",
            'x-category': info['category'],
            'x-routeIds': sorted(info['routeIds']),
            'x-sourceActionIds': sorted(info['sourceActionIds']),
            'responses': responses_spec,
        }
        if info['requestSchema']:
            op_spec['requestBody'] = {
                'required': True,
                'content': {'application/json': {'schema': info['requestSchema']}},
            }
        path_item[method.lower()] = op_spec

    static_apis = manifest.get('apiCalls', [])
    return {
        'schemaVersion': '1.0.0',
        'app': manifest['app']['name'],
        'staticApiCalls': static_apis,
        'runtimeObservedCount': len(runtime_records),
        'uiStateQueries': ui_state_queries,
        'userInteractionMutations': mutation_contracts,
        'realtimeOperations': [a for a in static_apis if a.get('kind') == 'websocket-op'],
        'openapi': {
            'openapi': '3.1.0',
            'info': {
                'title': f"{manifest['app']['name']} Reverse-Engineered API Contract",
                'version': manifest['app'].get('version', '0.1.0'),
            },
            'paths': openapi_paths,
        },
    }


class OpenAPIExporter:
    """Exports reverse-engineered API and OpenAPI 3.1 contracts."""

    @staticmethod
    def build_contracts(manifest, behavior, runtime_records=None):
        return build_api_data_contracts(manifest, behavior, runtime_records)

    @classmethod
    def export(cls, manifest, behavior, runtime_records=None, out_path: Path = None) -> Path:
        contracts = cls.build_contracts(manifest, behavior, runtime_records)
        target = Path(out_path or 'api-data-contracts.json')
        write_json(target, contracts)
        return target

    @classmethod
    def export_from_state(cls, state, manifest=None, behavior=None, out_path: Path = None) -> Path:
        manifest = manifest or {'app': {'name': 'discovered-app', 'version': '0.1.0'}, 'apiCalls': []}
        records = list(state.raw_api_records) or [api.to_record() for api in state.captured_apis.values()]
        return cls.export(manifest, behavior or {}, records, out_path)

