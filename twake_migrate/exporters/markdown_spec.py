"""Developer-ready mobile screen markdown and JSON specification exporters."""
from pathlib import Path
from ..core.common import write_json
from ..parsers.ui_mapper import (
    build_screen_inventory,
    build_ui_component_breakdown,
    extract_stores,
    extract_validation_and_persistence,
)
from .openapi import build_api_data_contracts


class MobileSpecExporter:
    """Serializes discovered screens, routing stack, and component breakdowns into Markdown specs."""

    @staticmethod
    def render_screens_markdown(screen_inventory: dict, ui_breakdown: dict = None, state_matrix: dict = None) -> str:
        lines = [
            f"# Mobile Screen Specification: {screen_inventory.get('app', 'App')}",
            f"- Source Router: `{screen_inventory.get('routerType', 'unknown')}`",
            f"- Target Flutter Router: `{screen_inventory.get('targetFlutterRouter', 'go_router')}`",
            '',
            '## Mobile Routing Stack',
        ]
        stack = screen_inventory.get('mobileRoutingStack', {})
        for key in ('shellRoutes', 'stackScreens', 'modalFlowScreens', 'authAndCallbackScreens'):
            lines.append(f"- **{key}**: {', '.join(stack.get(key, [])) or 'none'}")
        lines.append('\n## Screen Inventory')
        for screen in screen_inventory.get('screens', []):
            lines.append(
                f"- **{screen['screenId']}** (`{screen['name']}`): pattern=`{screen['mobileRoutingPattern']}`, "
                f"paths={screen.get('paths', [])}, states={screen.get('states', [])}, actions={len(screen.get('actionIds', []))}"
            )
        if ui_breakdown:
            lines.append('\n## UI Component Pattern Conversions')
            for comp in ui_breakdown.get('components', []):
                if not comp.get('patternConversions'):
                    continue
                patterns = ', '.join(
                    f"{p['webPattern']} -> {p['recommendedNativePattern']}"
                    for p in comp['patternConversions']
                )
                lines.append(f"- **{comp['manifestId']}** (`{comp['sourceFile']}`): {patterns}")
        if state_matrix:
            lines.append('\n## State & Validation Summary')
            lines.append(f"- Stores/Slices: {len(state_matrix.get('stores', []))}")
            lines.append(f"- Validation Rules: {len(state_matrix.get('validationRules', []))}")
            lines.append(f"- Persistence Requirements: {len(state_matrix.get('persistenceRequirements', []))}")
        return '\n'.join(lines) + '\n'

    @classmethod
    def export(cls, screen_inventory: dict, out_path: Path = None, ui_breakdown: dict = None, state_matrix: dict = None) -> Path:
        target = Path(out_path or 'docs/screens.md')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cls.render_screens_markdown(screen_inventory, ui_breakdown, state_matrix))
        return target


def generate_discovery_specs(web, parsed, manifest, gaps, behavior, out_dir, widget_map=None):
    """Emit all four structured mobile-dev specification artifacts from static discovery."""
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stores = extract_stores(web, parsed)
    validation_rules, persistence = extract_validation_and_persistence(web, parsed, behavior)

    screen_inventory = build_screen_inventory(manifest, behavior)
    ui_breakdown = build_ui_component_breakdown(manifest, gaps, behavior, widget_map)
    api_contracts = build_api_data_contracts(manifest, behavior)
    state_matrix = {
        'schemaVersion': '1.0.0',
        'app': manifest['app']['name'],
        'stateManagement': manifest['app']['stateManagement'],
        'targetFlutterStateManagement': manifest['app']['targetFlutterArchitecture']['stateManagement'],
        'stores': stores,
        'validationRules': validation_rules,
        'persistenceRequirements': persistence,
    }

    write_json(out / 'screen-inventory.json', screen_inventory)
    write_json(out / 'ui-component-breakdown.json', ui_breakdown)
    write_json(out / 'api-data-contracts.json', api_contracts)
    write_json(out / 'state-validation-matrix.json', state_matrix)

    return {
        'screenInventoryPath': str(out / 'screen-inventory.json'),
        'uiComponentBreakdownPath': str(out / 'ui-component-breakdown.json'),
        'apiDataContractsPath': str(out / 'api-data-contracts.json'),
        'stateValidationMatrixPath': str(out / 'state-validation-matrix.json'),
        'specCounts': {
            'stores': len(stores),
            'validationRules': len(validation_rules),
            'persistenceRequirements': len(persistence),
            'patternConversions': ui_breakdown['summary']['itemsRequiringPatternConversion'],
        },
    }

