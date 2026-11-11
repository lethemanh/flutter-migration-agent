"""Centralized state machine for discovery runs, loop detection, sliding-window compression, and resilient disk dumps."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from .common import write_json
from .types import AgentAction, CapturedAPI, ScreenSnapshot, UnsupportedPatternFlag


LOOP_GUARD_ERROR_MESSAGE = 'Element already clicked with no state change. Choose a different element.'


@dataclass
class DiscoveryState:
    """Typed state machine tracking visited routes, selector loop guards, captured APIs, and screens."""
    start_url: str
    visited_urls: Set[str] = field(default_factory=set)
    visited_selectors: Set[str] = field(default_factory=set)
    selector_no_change_counts: Dict[str, int] = field(default_factory=dict)
    captured_apis: Dict[str, CapturedAPI] = field(default_factory=dict)
    raw_api_records: List[Dict[str, Any]] = field(default_factory=list)
    screens: List[ScreenSnapshot] = field(default_factory=list)
    action_history: List[AgentAction] = field(default_factory=list)
    flagged_patterns: List[UnsupportedPatternFlag] = field(default_factory=list)
    current_depth: int = 0
    max_depth: int = 5
    max_selector_attempts: int = 2
    is_finished: bool = False

    def can_interact_selector(self, selector: str) -> bool:
        """Return False when a selector has already been tried >= max_selector_attempts times without a state change."""
        return self.selector_no_change_counts.get(selector, 0) < self.max_selector_attempts

    def record_selector_attempt(self, selector: str, state_changed: bool) -> Optional[Dict[str, str]]:
        """Update loop-detection counters; return an error payload if the selector is stuck in a no-op loop."""
        self.visited_selectors.add(selector)
        if state_changed:
            self.selector_no_change_counts[selector] = 0
            return None
        count = self.selector_no_change_counts.get(selector, 0) + 1
        self.selector_no_change_counts[selector] = count
        if count > self.max_selector_attempts:
            return {'status': 'error', 'message': LOOP_GUARD_ERROR_MESSAGE}
        return None

    def compress_context_messages(self, system_prompt: str, window_size: int = 2) -> List[Dict[str, str]]:
        """Sliding-window context compression: retain up to two actions and the latest screen state."""
        messages: List[Dict[str, str]] = [{'role': 'system', 'content': system_prompt}]
        window_size = min(2, max(0, window_size))
        recent = self.action_history[-window_size:] if window_size else []
        for idx, step in enumerate(recent):
            is_latest = idx == len(recent) - 1
            content = step.to_compact_log()
            if is_latest and step.screen_summary:
                content += f"\nLatest screen state: {step.screen_summary}"
            messages.append({'role': 'user', 'content': content})
        return messages

    def dump_to_disk(self, path: Path) -> Path:
        """Resiliently flush intermediate discovery state to disk after each step."""
        target = Path(path)
        payload = {
            'startUrl': self.start_url,
            'visitedUrls': sorted(self.visited_urls),
            'visitedSelectors': sorted(self.visited_selectors),
            'selectorNoChangeCounts': dict(self.selector_no_change_counts),
            'capturedApis': {k: v.to_record() for k, v in self.captured_apis.items()},
            'screens': [s.to_capture_dict() for s in self.screens],
            'actionHistory': [a.model_dump() for a in self.action_history],
            'flaggedPatterns': [f.model_dump() for f in self.flagged_patterns],
            'currentDepth': self.current_depth,
            'maxDepth': self.max_depth,
            'isFinished': self.is_finished,
        }
        write_json(target, payload)
        return target

    def model_dump(self) -> Dict[str, Any]:
        return {
            'start_url': self.start_url,
            'visited_urls': sorted(self.visited_urls),
            'visited_selectors': sorted(self.visited_selectors),
            'selector_no_change_counts': dict(self.selector_no_change_counts),
            'captured_apis': {k: v.model_dump() for k, v in self.captured_apis.items()},
            'screens': [s.model_dump() for s in self.screens],
            'action_history': [a.model_dump() for a in self.action_history],
            'flagged_patterns': [f.model_dump() for f in self.flagged_patterns],
            'current_depth': self.current_depth,
            'max_depth': self.max_depth,
            'is_finished': self.is_finished,
        }

