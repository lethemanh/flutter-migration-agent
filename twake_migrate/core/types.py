"""Core typed schemas for the discovery agent (CapturedAPI, ScreenSnapshot, ScreenState, AgentAction)."""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CapturedAPI:
    """Sanitized representation of an intercepted HTTP API endpoint and its JSON schemas."""
    method: str
    path: str
    path_template: str
    category: str
    status: int = 200
    content_type: Optional[str] = None
    query_param_keys: List[str] = field(default_factory=list)
    request_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    route_id: Optional[str] = None
    journey_id: Optional[str] = None
    source_action_id: Optional[str] = None
    theme_mode: Optional[str] = None
    statuses: List[int] = field(default_factory=list)
    observed_paths: List[str] = field(default_factory=list)

    def to_record(self) -> Dict[str, Any]:
        return {
            'method': self.method,
            'path': self.path,
            'pathTemplate': self.path_template,
            'queryParamKeys': list(self.query_param_keys),
            'status': self.status,
            'contentType': self.content_type,
            'category': self.category,
            'requestSchema': self.request_schema,
            'responseSchema': self.response_schema,
            'routeId': self.route_id,
            'journeyId': self.journey_id,
            'sourceActionId': self.source_action_id,
            'themeMode': self.theme_mode,
        }

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenSnapshot:
    """Captured mobile viewport state, accessibility tree, and layout metrics for a screen."""
    route_id: str
    path: str
    landing_path: str = ''
    screen_ids: List[str] = field(default_factory=list)
    expected_screen_ids: List[str] = field(default_factory=list)
    theme_mode: str = 'light'
    screenshot_path: str = ''
    screenshot_sha256: str = ''
    dom_metrics: Dict[str, Any] = field(default_factory=dict)
    ui: Dict[str, Any] = field(default_factory=dict)
    network_calls_count: int = 0
    redirected: bool = False

    def to_capture_dict(self) -> Dict[str, Any]:
        return {
            'routeId': self.route_id,
            'screenIds': list(self.screen_ids),
            'expectedScreenIds': list(self.expected_screen_ids),
            'path': self.path,
            'landingPath': self.landing_path or self.path,
            'redirected': self.redirected,
            'themeMode': self.theme_mode,
            'screenshotPath': self.screenshot_path,
            'domMetrics': self.dom_metrics,
            'networkCallsCount': self.network_calls_count,
            'screenshotSha256': self.screenshot_sha256,
            'ui': self.ui,
        }

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


ScreenState = ScreenSnapshot


@dataclass
class AgentAction:
    """Single executed or attempted browser interaction step in the discovery FSM."""
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    source_action_id: Optional[str] = None
    state_changed: bool = False
    status: str = 'ok'
    message: str = ''
    screen_summary: Optional[Dict[str, Any]] = None

    def to_compact_log(self) -> str:
        target = self.selector or self.url or ''
        val_part = f' with "{self.value}"' if self.value else ''
        return f'User action: {self.action} "{target}"{val_part} -> {self.status}'

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnsupportedPatternFlag:
    """Web UI pattern flagged during exploration for native mobile conversion."""
    manifest_ref: str
    web_pattern: str
    description: str
    recommended_native_pattern: str
    source_file: Optional[str] = None

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)

