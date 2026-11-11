"""Network sniffing, route filtering, request body extraction, and non-blocking JSON schema capture."""
import json
from urllib.parse import urlparse
from ..core.types import CapturedAPI
from ..parsers.schema_infer import (
    SENSITIVE_KEY_PATTERN,
    infer_json_schema,
    merge_json_schemas,
    normalize_endpoint_path,
)


class NetworkContractRecorder:
    """Passively intercept Playwright XHR/Fetch responses and reverse-engineer sanitized JSON schemas."""

    def __init__(self, base_url, state=None):
        self.base_netloc = urlparse(base_url).netloc
        self.records = []
        self.state = state
        self.context = {'routeId': None, 'journeyId': None, 'sourceActionId': None, 'themeMode': None}

    def set_context(self, *, route_id=None, journey_id=None, source_action_id=None, theme_mode=None):
        self.context = {
            'routeId': route_id,
            'journeyId': journey_id,
            'sourceActionId': source_action_id,
            'themeMode': theme_mode,
        }

    def on_response(self, response):
        try:
            request = response.request
            resource_type = getattr(request, 'resource_type', None)
            if resource_type not in {'fetch', 'xhr'}:
                return
            parsed = urlparse(response.url)
            if self.base_netloc and parsed.netloc and parsed.netloc != self.base_netloc:
                return
            method = (getattr(request, 'method', 'GET') or 'GET').upper()
            path = parsed.path or '/'
            if path.endswith(('.js', '.css', '.png', '.svg', '.woff', '.woff2', '.ttf', '.ico', '.map')):
                return
            status = int(getattr(response, 'status', 0) or 0)
            headers = getattr(response, 'headers', {}) or {}
            content_type = (headers.get('content-type') or headers.get('Content-Type') or '').lower()
            req_schema = None
            post_data = getattr(request, 'post_data', None)
            if callable(post_data):
                post_data = post_data()
            if isinstance(post_data, str) and post_data.strip().startswith(('{', '[')):
                try:
                    req_schema = infer_json_schema(json.loads(post_data))
                except (ValueError, TypeError):
                    req_schema = {'type': 'string', 'contentEncoding': 'non-json-payload'}
            resp_schema = None
            if 'json' in content_type:
                try:
                    body_fn = getattr(response, 'json', None)
                    if callable(body_fn):
                        resp_schema = infer_json_schema(body_fn())
                except Exception:
                    resp_schema = None
            query_keys = sorted({
                part.split('=', 1)[0]
                for part in (parsed.query or '').split('&')
                if part and not SENSITIVE_KEY_PATTERN.search(part.split('=', 1)[0])
            })
            category = 'ui-state-query' if method in {'GET', 'HEAD'} else 'user-interaction-mutation'
            path_template = normalize_endpoint_path(path)
            record = {
                'method': method,
                'path': path,
                'pathTemplate': path_template,
                'queryParamKeys': query_keys,
                'status': status,
                'contentType': content_type.split(';', 1)[0].strip() or None,
                'category': category,
                'requestSchema': req_schema,
                'responseSchema': resp_schema,
                **self.context,
            }
            self.records.append(record)
            if self.state is not None:
                self.state.raw_api_records.append(record)
                key = f'{method} {path_template}'
                existing = self.state.captured_apis.get(key)
                if existing:
                    existing.request_schema = merge_json_schemas(existing.request_schema, req_schema)
                    existing.response_schema = merge_json_schemas(existing.response_schema, resp_schema)
                    if status and status not in existing.statuses:
                        existing.statuses.append(status)
                    if path not in existing.observed_paths:
                        existing.observed_paths.append(path)
                else:
                    self.state.captured_apis[key] = CapturedAPI(
                        method=method,
                        path=path,
                        path_template=path_template,
                        category=category,
                        status=status,
                        content_type=record['contentType'],
                        query_param_keys=query_keys,
                        request_schema=req_schema,
                        response_schema=resp_schema,
                        route_id=self.context['routeId'],
                        journey_id=self.context['journeyId'],
                        source_action_id=self.context['sourceActionId'],
                        theme_mode=self.context['themeMode'],
                        statuses=[status] if status else [],
                        observed_paths=[path],
                    )
        except Exception:
            # Never fail runtime UI capture if an arbitrary asset response cannot be inspected.
            return


NetworkInterceptor = NetworkContractRecorder

