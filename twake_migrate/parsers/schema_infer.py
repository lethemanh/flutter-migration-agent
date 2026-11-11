"""JSON -> JSON Schema and TypeScript interface converter with credential redaction."""
import re
from urllib.parse import urlparse


SENSITIVE_KEY_PATTERN = re.compile(
    r'token|secret|password|passwd|authorization|cookie|session|credential|nonce|code_verifier|api_key|apikey|private_key',
    re.I,
)
UUID_SEGMENT = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
HEX_ID_SEGMENT = re.compile(r'^[0-9a-f]{16,64}$', re.I)
NUMERIC_SEGMENT = re.compile(r'^\d+$')
ISO_DATETIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
URI_RE = re.compile(r'^https?://', re.I)


def normalize_endpoint_path(path):
    """Replace dynamic entity IDs in a URL path with `{id}` placeholders."""
    if not path or not isinstance(path, str):
        return '/'
    clean = urlparse(path).path or '/'
    parts = []
    for segment in clean.split('/'):
        if not segment:
            continue
        if UUID_SEGMENT.match(segment) or HEX_ID_SEGMENT.match(segment) or NUMERIC_SEGMENT.match(segment):
            parts.append('{id}')
        elif segment.startswith(':') and len(segment) > 1:
            parts.append('{' + segment[1:] + '}')
        else:
            parts.append(segment)
    return '/' + '/'.join(parts)


def infer_json_schema(value, depth=0, max_depth=6):
    """Infer a structural JSON Schema without retaining any raw data values or credentials."""
    if depth >= max_depth:
        return {'type': 'object' if isinstance(value, dict) else 'array' if isinstance(value, list) else 'string'}
    if value is None:
        return {'type': 'null'}
    if isinstance(value, bool):
        return {'type': 'boolean'}
    if isinstance(value, int):
        return {'type': 'integer'}
    if isinstance(value, float):
        return {'type': 'number'}
    if isinstance(value, str):
        schema = {'type': 'string'}
        if UUID_SEGMENT.match(value):
            schema['format'] = 'uuid'
        elif ISO_DATETIME_RE.match(value):
            schema['format'] = 'date-time'
        elif EMAIL_RE.match(value):
            schema['format'] = 'email'
        elif URI_RE.match(value):
            schema['format'] = 'uri'
        return schema
    if isinstance(value, list):
        if not value:
            return {'type': 'array', 'items': {}}
        item_schema = None
        for element in value[:10]:
            current = infer_json_schema(element, depth + 1, max_depth)
            item_schema = merge_json_schemas(item_schema, current) if item_schema else current
        return {'type': 'array', 'items': item_schema or {}}
    if isinstance(value, dict):
        properties = {}
        required = []
        for k, v in list(value.items())[:60]:
            key = str(k)
            required.append(key)
            if SENSITIVE_KEY_PATTERN.search(key):
                properties[key] = {'type': 'string', 'format': 'redacted'}
            else:
                properties[key] = infer_json_schema(v, depth + 1, max_depth)
        return {
            'type': 'object',
            'required': sorted(required),
            'properties': dict(sorted(properties.items())),
        }
    return {'type': 'string'}


def merge_json_schemas(first, second):
    """Merge two inferred JSON schemas conservatively."""
    if not first:
        return second
    if not second or first == second:
        return first
    t1 = first.get('type')
    t2 = second.get('type')
    if t1 == 'object' and t2 == 'object':
        props1 = first.get('properties', {})
        props2 = second.get('properties', {})
        merged_props = {}
        for key in sorted(set(props1) | set(props2)):
            if key in props1 and key in props2:
                merged_props[key] = merge_json_schemas(props1[key], props2[key])
            else:
                merged_props[key] = props1.get(key) or props2.get(key)
        req1 = set(first.get('required', []))
        req2 = set(second.get('required', []))
        return {
            'type': 'object',
            'required': sorted(req1 & req2),
            'properties': merged_props,
        }
    if t1 == 'array' and t2 == 'array':
        return {
            'type': 'array',
            'items': merge_json_schemas(first.get('items', {}), second.get('items', {})),
        }
    types = set()
    for t in (t1, t2):
        if isinstance(t, list):
            types.update(t)
        elif t:
            types.add(t)
    if types == {'integer', 'number'}:
        return {'type': 'number'}
    return {'type': sorted(types) if len(types) > 1 else next(iter(types), 'string')}


def json_schema_to_ts_type(schema, indent=0) -> str:
    """Convert a JSON Schema dict into a TypeScript type expression."""
    if not schema or not isinstance(schema, dict):
        return 'unknown'
    kind = schema.get('type')
    if isinstance(kind, list):
        return ' | '.join(json_schema_to_ts_type({'type': k}, indent) for k in kind)
    if kind in {'integer', 'number'}:
        return 'number'
    if kind == 'boolean':
        return 'boolean'
    if kind == 'null':
        return 'null'
    if kind == 'string':
        return 'string'
    if kind == 'array':
        item_ts = json_schema_to_ts_type(schema.get('items', {}), indent)
        return f'Array<{item_ts}>'
    if kind == 'object':
        props = schema.get('properties', {})
        if not props:
            return 'Record<string, unknown>'
        required = set(schema.get('required', []))
        pad = '  ' * (indent + 1)
        closing_pad = '  ' * indent
        lines = ['{']
        for key, prop_schema in sorted(props.items()):
            safe_key = key if re.match(r'^[A-Za-z_$][A-Za-z0-9_$]*$', key) else f"'{key}'"
            opt = '' if key in required else '?'
            lines.append(f'{pad}{safe_key}{opt}: {json_schema_to_ts_type(prop_schema, indent + 1)};')
        lines.append(f'{closing_pad}}}')
        return '\n'.join(lines)
    return 'unknown'

