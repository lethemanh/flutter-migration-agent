"""Parsers for AST static discovery, JSON schema inference, Web-to-Mobile UI/state mapping, and design tokens."""
from .behavior import FUNCTIONS, discover_behavior, guards, identifier, location, owner
from .discovery import discover_static, imports, routes_from_ast, source_files
from .javascript import descendants, evaluate, parse, prop, string, text, variable
from .route_discovery import routes_from_objects
from .schema_infer import (
    SENSITIVE_KEY_PATTERN,
    infer_json_schema,
    json_schema_to_ts_type,
    merge_json_schemas,
    normalize_endpoint_path,
)
from .source_resolution import alias_definitions, module_target, source_config_hashes
from .token_linter import (
    DesignTokenValidator,
    REPLACEMENT_RULES,
    TokenViolation,
    is_token_definition_file,
    lint_dart_code,
    lint_dart_file,
    lint_flutter_tokens,
)
from .tokens import color, pixels, read_sources, semantic_roles, validate_tokens
from .ui_mapper import (
    build_screen_inventory,
    build_ui_component_breakdown,
    extract_stores,
    extract_validation_and_persistence,
)

__all__ = [
    'DesignTokenValidator',
    'FUNCTIONS',
    'REPLACEMENT_RULES',
    'SENSITIVE_KEY_PATTERN',
    'TokenViolation',
    'alias_definitions',
    'build_screen_inventory',
    'build_ui_component_breakdown',
    'color',
    'descendants',
    'discover_behavior',
    'discover_static',
    'evaluate',
    'extract_stores',
    'extract_validation_and_persistence',
    'guards',
    'identifier',
    'imports',
    'infer_json_schema',
    'is_token_definition_file',
    'json_schema_to_ts_type',
    'lint_dart_code',
    'lint_dart_file',
    'lint_flutter_tokens',
    'location',
    'merge_json_schemas',
    'module_target',
    'normalize_endpoint_path',
    'owner',
    'parse',
    'pixels',
    'prop',
    'read_sources',
    'routes_from_ast',
    'routes_from_objects',
    'semantic_roles',
    'source_config_hashes',
    'source_files',
    'string',
    'text',
    'validate_tokens',
    'variable',
]
