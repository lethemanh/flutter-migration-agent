"""Tool abstraction and function registry with OpenAI/Anthropic schema export."""
from dataclasses import dataclass
import inspect
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    """Decoupled tool definition with JSON Schema parameters and executable callback."""
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Callable[..., Any]


class ToolRegistry:
    """Registry managing agent tools, schema definitions, and async/sync execution."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                'type': 'function',
                'function': {
                    'name': t.name,
                    'description': t.description,
                    'parameters': t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def run(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            raise ValueError(f'Tool {name} not found.')
        result = self._tools[name].execute(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    def run_sync(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            raise ValueError(f'Tool {name} not found.')
        return self._tools[name].execute(**kwargs)

