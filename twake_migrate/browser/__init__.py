"""Browser lifecycle, DOM/A11y snapshotting, and network interception package."""
from .dom import METRICS, UI_SNAPSHOT, capture_state, crawl_sitemap, wait_for_deterministic_settle
from .driver import BrowserDriver, _capture_routes, _local_url, capture_journeys, discover_runtime, validate_journeys
from .interceptor import NetworkContractRecorder, NetworkInterceptor

__all__ = [
    'BrowserDriver',
    'METRICS',
    'NetworkContractRecorder',
    'NetworkInterceptor',
    'UI_SNAPSHOT',
    '_capture_routes',
    '_local_url',
    'capture_journeys',
    'capture_state',
    'crawl_sitemap',
    'discover_runtime',
    'validate_journeys',
    'wait_for_deterministic_settle',
]

