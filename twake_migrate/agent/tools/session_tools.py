"""Session control tools for finishing discovery and flagging web-only UI patterns."""
from ...core.state import DiscoveryState
from ...core.types import AgentAction, UnsupportedPatternFlag
from .base import Tool, ToolRegistry


def register_session_tools(registry: ToolRegistry, state: DiscoveryState) -> ToolRegistry:
    """Register finish_discovery and flag_unsupported_pattern tools."""

    def finish_discovery(reason: str = 'Discovery complete'):
        state.is_finished = True
        state.action_history.append(AgentAction(action='finish_discovery', value=reason, state_changed=False, status='ok'))
        return {'status': 'ok', 'isFinished': True, 'reason': reason}

    def flag_unsupported_pattern(
        manifest_ref: str,
        web_pattern: str,
        description: str,
        recommended_native_pattern: str,
        source_file: str = None,
    ):
        flag = UnsupportedPatternFlag(
            manifest_ref=manifest_ref,
            web_pattern=web_pattern,
            description=description,
            recommended_native_pattern=recommended_native_pattern,
            source_file=source_file,
        )
        state.flagged_patterns.append(flag)
        state.action_history.append(AgentAction(
            action='flag_unsupported_pattern',
            selector=manifest_ref,
            value=f'{web_pattern} -> {recommended_native_pattern}',
            state_changed=False,
            status='ok',
        ))
        return {'status': 'ok', 'flagged': flag.model_dump()}

    registry.register(Tool(
        name='finish_discovery',
        description='Mark the interactive discovery exploration session as finished.',
        parameters={'type': 'object', 'properties': {'reason': {'type': 'string'}}},
        execute=finish_discovery,
    ))
    registry.register(Tool(
        name='flag_unsupported_pattern',
        description='Flag a desktop/web-only UI pattern (table, complex sidebar, modal, hover) for native conversion.',
        parameters={
            'type': 'object',
            'required': ['manifest_ref', 'web_pattern', 'description', 'recommended_native_pattern'],
            'properties': {
                'manifest_ref': {'type': 'string'},
                'web_pattern': {'type': 'string'},
                'description': {'type': 'string'},
                'recommended_native_pattern': {'type': 'string'},
                'source_file': {'type': 'string'},
            },
        },
        execute=flag_unsupported_pattern,
    ))
    return registry

