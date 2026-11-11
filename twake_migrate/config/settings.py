"""Configuration settings for the mobile discovery agent."""
from dataclasses import asdict, dataclass
import os


@dataclass
class DiscoverySettings:
    """Typed runtime settings with environment variable overrides."""
    target_url: str = 'http://localhost:5000'
    viewport_width: int = 390
    viewport_height: int = 844
    navigation_timeout_ms: int = 30000
    action_timeout_ms: int = 15000
    network_idle_timeout_ms: int = 15000
    max_depth: int = 3
    max_pages: int = 25
    max_selector_attempts: int = 2
    sliding_window_size: int = 2
    model_name: str = 'inherit'

    @classmethod
    def from_env(cls, **overrides) -> 'DiscoverySettings':
        env_map = {
            'target_url': os.environ.get('TWAKE_TARGET_URL', cls.target_url),
            'viewport_width': int(os.environ.get('TWAKE_VIEWPORT_WIDTH', cls.viewport_width)),
            'viewport_height': int(os.environ.get('TWAKE_VIEWPORT_HEIGHT', cls.viewport_height)),
            'navigation_timeout_ms': int(os.environ.get('TWAKE_NAVIGATION_TIMEOUT_MS', cls.navigation_timeout_ms)),
            'action_timeout_ms': int(os.environ.get('TWAKE_ACTION_TIMEOUT_MS', cls.action_timeout_ms)),
            'network_idle_timeout_ms': int(os.environ.get('TWAKE_NETWORK_IDLE_TIMEOUT_MS', cls.network_idle_timeout_ms)),
            'max_depth': int(os.environ.get('TWAKE_MAX_DEPTH', cls.max_depth)),
            'max_pages': int(os.environ.get('TWAKE_MAX_PAGES', cls.max_pages)),
            'max_selector_attempts': int(os.environ.get('TWAKE_MAX_SELECTOR_ATTEMPTS', cls.max_selector_attempts)),
            'sliding_window_size': int(os.environ.get('TWAKE_SLIDING_WINDOW_SIZE', cls.sliding_window_size)),
            'model_name': os.environ.get('TWAKE_MODEL_NAME', cls.model_name),
        }
        env_map.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**env_map)

    def model_dump(self) -> dict:
        return asdict(self)

