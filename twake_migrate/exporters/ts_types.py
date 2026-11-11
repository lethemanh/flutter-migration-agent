"""Exports TypeScript interfaces for mobile models from captured API schemas."""
from pathlib import Path
from ..core.common import pascal
from ..parsers.schema_infer import json_schema_to_ts_type


class TypeScriptExporter:
    """Generates TypeScript type/interface definitions from reverse-engineered API schemas."""

    @staticmethod
    def _interface_name(method: str, path_template: str, suffix: str) -> str:
        import re
        cleaned = path_template.replace('{id}', 'ById').replace('{', '').replace('}', '')
        cleaned = re.sub(r'[^A-Za-z0-9]+', '_', cleaned).strip('_') or 'Root'
        return pascal(f'{method.lower()}_{cleaned}_{suffix}')

    @classmethod
    def render(cls, contracts: dict) -> str:
        lines = ['// Auto-generated mobile model contracts from intercepted API schemas.']
        items = [
            *contracts.get('uiStateQueries', []),
            *contracts.get('userInteractionMutations', []),
        ]
        for item in items:
            method = item.get('method', 'GET')
            path_template = item.get('pathTemplate', '/')
            req_schema = item.get('requestSchema')
            resp_schema = item.get('responseSchema')
            if req_schema:
                name = cls._interface_name(method, path_template, 'Request')
                ts_body = json_schema_to_ts_type(req_schema)
                if ts_body.startswith('{'):
                    lines.append(f'export interface {name} {ts_body}')
                else:
                    lines.append(f'export type {name} = {ts_body};')
            if resp_schema:
                name = cls._interface_name(method, path_template, 'Response')
                ts_body = json_schema_to_ts_type(resp_schema)
                if ts_body.startswith('{'):
                    lines.append(f'export interface {name} {ts_body}')
                else:
                    lines.append(f'export type {name} = {ts_body};')
        return '\n\n'.join(lines) + '\n'

    @classmethod
    def export(cls, contracts_or_apis, out_path: Path = None) -> Path:
        target = Path(out_path or 'types/api.d.ts')
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contracts_or_apis, dict) and ('uiStateQueries' in contracts_or_apis or 'userInteractionMutations' in contracts_or_apis):
            contracts = contracts_or_apis
        elif isinstance(contracts_or_apis, dict):
            # Support passing state.captured_apis dict directly
            queries = [v.to_record() for v in contracts_or_apis.values() if getattr(v, 'category', '') == 'ui-state-query']
            mutations = [v.to_record() for v in contracts_or_apis.values() if getattr(v, 'category', '') != 'ui-state-query']
            contracts = {'uiStateQueries': queries, 'userInteractionMutations': mutations}
        else:
            contracts = {'uiStateQueries': [], 'userInteractionMutations': []}
        target.write_text(cls.render(contracts))
        return target
