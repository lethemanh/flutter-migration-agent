"""FSM execution loop (Observe -> Decide -> Act -> Verify) with sliding-window context compression and resilient artifact dumping."""
from pathlib import Path
import signal
from typing import Any, Callable, Dict, Optional
from ..browser.permissions import same_origin
from ..browser.dom import UI_SNAPSHOT
from ..config.settings import DiscoverySettings
from ..core.state import DiscoveryState
from .prompts import DISCOVERY_FSM_SYSTEM_PROMPT
from .tools.base import ToolRegistry
from .tools.browser_tools import register_browser_tools
from .tools.session_tools import register_session_tools


class DiscoveryAgentLoop:
    """Orchestrated state-machine loop: Observe -> Decide -> Act -> Verify."""

    def __init__(
        self,
        page,
        state: DiscoveryState,
        settings: Optional[DiscoverySettings] = None,
        checkpoint_path: Optional[Path] = None,
        registry: Optional[ToolRegistry] = None,
        route_targets: Optional[Dict[str, str]] = None,
        benign_selectors=None,
    ):
        self.page = page
        self.state = state
        self.settings = settings or DiscoverySettings(
            target_url=state.start_url,
            max_depth=state.max_depth,
            max_selector_attempts=state.max_selector_attempts,
        )
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.registry = registry or ToolRegistry()
        register_browser_tools(
            self.registry, self.page, self.state, self.settings, route_targets,
            benign_selectors, self.checkpoint_path.parent if self.checkpoint_path else None,
        )
        register_session_tools(self.registry, self.state)

    def observe(self) -> Dict[str, Any]:
        """Extract compact Accessibility Tree and interactable elements from the current viewport."""
        url = getattr(self.page, 'url', self.state.start_url)
        snapshot = self.page.evaluate(UI_SNAPSHOT) if same_origin(url, self.state.start_url) and hasattr(self.page, 'evaluate') else {}
        observation = {
            'url': getattr(self.page, 'url', self.state.start_url),
            'accessibilityTree': snapshot.get('accessibilityTree', []),
            'discoveredLinks': snapshot.get('discoveredLinks', []),
            'interactableCount': len(snapshot.get('elements', [])),
        }
        if self.state.action_history:
            self.state.action_history[-1].screen_summary = observation
        return observation

    def get_compressed_messages(self, system_prompt: str = DISCOVERY_FSM_SYSTEM_PROMPT):
        """Return sliding-window compressed conversation history retaining only the latest screen snapshot."""
        return self.state.compress_context_messages(
            system_prompt=system_prompt,
            window_size=self.settings.sliding_window_size,
        )

    def step(self, decision_fn: Callable[[Dict[str, Any], list, list], Dict[str, Any]]) -> Dict[str, Any]:
        """Execute one Observe -> Decide -> Act -> Verify cycle and flush intermediate state to disk."""
        observation = self.observe()
        messages = self.get_compressed_messages()
        tools = self.registry.get_definitions()
        decision = decision_fn(observation, messages, tools)
        tool_name = decision.get('name') or decision.get('tool')
        tool_args = decision.get('arguments') or decision.get('args') or {}
        if not tool_name:
            self.state.is_finished = True
            result = {'status': 'ok', 'isFinished': True}
        else:
            result = self.registry.run_sync(tool_name, **tool_args)
        post_observation = self.observe()
        if self.checkpoint_path is not None:
            self.state.dump_to_disk(self.checkpoint_path)
        return {
            'tool': tool_name,
            'arguments': tool_args,
            'result': result,
            'observation': post_observation,
        }

    def run(self, decision_fn: Callable[[Dict[str, Any], list, list], Dict[str, Any]],
            max_steps: int = 30, timeout_seconds: float = 60):
        """Run synchronous exploration under a main-thread POSIX watchdog."""
        steps = []
        limit = min(30, max(0, max_steps))
        timeout = min(60, max(0, timeout_seconds))
        if not limit or not timeout or self.state.is_finished:
            return steps

        class WatchdogExpired(TimeoutError):
            pass

        def expire(signum, frame):
            raise WatchdogExpired

        previous = signal.signal(signal.SIGALRM, expire)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            for _ in range(limit):
                if self.state.is_finished:
                    break
                step = self.step(decision_fn)
                steps.append(step)
                if step['result'].get('status') == 'approval_required':
                    break
        except WatchdogExpired:
            self.state.is_finished = True
            steps.append({'result': {'status': 'stopped', 'reason': 'time-budget'}})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
            if previous_timer[0]:
                signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        if len(steps) == limit and not self.state.is_finished:
            self.state.is_finished = True
        if self.checkpoint_path is not None:
            self.state.dump_to_disk(self.checkpoint_path)
        return steps
