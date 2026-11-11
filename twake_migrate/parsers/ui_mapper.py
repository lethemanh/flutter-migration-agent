"""Web layout -> Mobile component mapper, static store extractor, and client validation/persistence parser."""
from collections import defaultdict
import re
from ..core.common import snake
from .behavior import FUNCTIONS, guards, identifier, location, owner
from .javascript import descendants, string, text
from .schema_infer import SENSITIVE_KEY_PATTERN


def _ast_object_schema(node):
    """Infer a shallow structural schema from an AST object literal."""
    if node is None or node.type != 'object':
        return {}, []
    keys = []
    properties = {}
    for pair in node.named_children:
        if pair.type != 'pair':
            continue
        key_node = pair.child_by_field_name('key')
        val_node = pair.child_by_field_name('value')
        key = text(key_node).strip("'\"")
        if not key:
            continue
        keys.append(key)
        vtype = val_node.type if val_node else 'unknown'
        if vtype in {'string', 'template_string'}:
            properties[key] = {'type': 'string'}
        elif vtype == 'number':
            properties[key] = {'type': 'number'}
        elif vtype in {'true', 'false'}:
            properties[key] = {'type': 'boolean'}
        elif vtype == 'array':
            properties[key] = {'type': 'array'}
        elif vtype == 'object':
            sub_props, _ = _ast_object_schema(val_node)
            properties[key] = {'type': 'object', 'properties': sub_props}
        elif vtype == 'null':
            properties[key] = {'type': 'null'}
        else:
            properties[key] = {'type': 'any', 'expression': text(val_node)[:80]}
    return properties, sorted(dict.fromkeys(keys))


def extract_stores(web, parsed):
    """Extract state management stores and slices (Redux Toolkit, Zustand, React Context) from AST."""
    stores = []
    for file, root in sorted(parsed.items()):
        relative = file.relative_to(web).as_posix()
        variables = {
            text(n.child_by_field_name('name')): n.child_by_field_name('value')
            for n in descendants(root, 'variable_declarator')
            if n.child_by_field_name('name') and n.child_by_field_name('value')
        }
        for call in descendants(root, 'call_expression'):
            callee = text(call.child_by_field_name('function'))
            short = callee.split('.')[-1]
            args = call.child_by_field_name('arguments')
            first_arg = args.named_children[0] if args and args.named_children else None
            if short == 'createSlice' and first_arg and first_arg.type == 'object':
                props = {}
                for p in first_arg.named_children:
                    if p.type == 'pair':
                        props[text(p.child_by_field_name('key')).strip("'\"")] = p.child_by_field_name('value')
                    elif p.type == 'shorthand_property_identifier':
                        props[text(p)] = p
                slice_name = None
                if props.get('name') and props['name'].type in {'string', 'template_string'}:
                    try:
                        slice_name = string(props['name'])
                    except ValueError:
                        slice_name = text(props['name']).strip("'\"")
                if not slice_name:
                    slice_name = file.stem
                init_node = props.get('initialState')
                if init_node and init_node.type in {'identifier', 'shorthand_property_identifier'} and text(init_node) in variables:
                    init_node = variables[text(init_node)]
                schema, init_keys = _ast_object_schema(init_node)
                reducers = []
                if props.get('reducers') and props['reducers'].type == 'object':
                    for member in props['reducers'].named_children:
                        if member.type in {'pair', 'method_definition'}:
                            k = member.child_by_field_name('key') or member.child_by_field_name('name')
                            if k:
                                reducers.append(text(k).strip("'\""))
                extra_triggers = []
                if props.get('extraReducers'):
                    for subcall in descendants(props['extraReducers'], 'call_expression'):
                        fn = text(subcall.child_by_field_name('function'))
                        if fn.endswith('.addCase'):
                            subargs = subcall.child_by_field_name('arguments')
                            if subargs and subargs.named_children:
                                extra_triggers.append(text(subargs.named_children[0]))
                stores.append({
                    'id': identifier('STORE', relative, slice_name),
                    'name': slice_name,
                    'kind': 'redux-slice',
                    'initialStateKeys': init_keys,
                    'initialStateSchema': schema,
                    'reducers': sorted(dict.fromkeys(reducers)),
                    'extraReducerTriggers': sorted(dict.fromkeys(extra_triggers)),
                    'targetFlutterProvider': f'{snake(slice_name).lower()}_provider',
                    **location(relative, call),
                })
            elif short in {'configureStore', 'createStore'}:
                reducer_keys = []
                if first_arg and first_arg.type == 'object':
                    for p in first_arg.named_children:
                        if p.type == 'pair' and text(p.child_by_field_name('key')).strip("'\"") == 'reducer':
                            rval = p.child_by_field_name('value')
                            if rval and rval.type == 'object':
                                for rp in rval.named_children:
                                    if rp.type == 'pair':
                                        reducer_keys.append(text(rp.child_by_field_name('key')).strip("'\""))
                                    elif rp.type == 'shorthand_property_identifier':
                                        reducer_keys.append(text(rp))
                stores.append({
                    'id': identifier('STORE', relative, f'{short}:{call.start_byte}'),
                    'name': file.stem,
                    'kind': 'redux-store',
                    'initialStateKeys': sorted(dict.fromkeys(reducer_keys)),
                    'initialStateSchema': {},
                    'reducers': [],
                    'extraReducerTriggers': [],
                    'targetFlutterProvider': 'app_store_provider',
                    **location(relative, call),
                })
            elif short == 'createContext':
                parent_name = file.stem
                if call.parent and call.parent.type == 'variable_declarator':
                    parent_name = text(call.parent.child_by_field_name('name'))
                stores.append({
                    'id': identifier('STORE', relative, parent_name),
                    'name': parent_name,
                    'kind': 'react-context',
                    'initialStateKeys': [],
                    'initialStateSchema': {},
                    'reducers': [],
                    'extraReducerTriggers': [],
                    'targetFlutterProvider': f'{snake(parent_name).lower()}_provider',
                    **location(relative, call),
                })
    return stores


def extract_validation_and_persistence(web, parsed, behavior):
    """Extract client-side validation rules (regex, field constraints, validators) and offline/storage persistence."""
    validation_rules = []
    persistence = []
    functions_by_file = defaultdict(dict)
    for func in behavior.get('functions', []):
        functions_by_file[func['sourceFile']][(func['sourceLine'], func['sourceEndLine'])] = func

    for file, root in sorted(parsed.items()):
        relative = file.relative_to(web).as_posix()
        records = {}
        for node in descendants(root):
            if node.type in FUNCTIONS:
                line = node.start_point.row + 1
                end_line = node.end_point.row + 1
                match = functions_by_file[relative].get((line, end_line))
                if match:
                    records[node.start_byte] = match

        for node in descendants(root, 'regex'):
            func_owner = owner(node, records)
            raw = text(node)
            validation_rules.append({
                'id': identifier('VALID', relative, f'regex:{node.start_byte}'),
                'kind': 'regex-literal',
                'pattern': raw,
                'ownerFunctionId': func_owner['id'] if func_owner else None,
                'manifestRefs': list(func_owner['manifestRefs']) if func_owner else [],
                'guards': guards(node),
                **location(relative, node),
            })

        for node in descendants(root, 'new_expression'):
            ctor = text(node.child_by_field_name('constructor'))
            if ctor == 'RegExp':
                func_owner = owner(node, records)
                args = node.child_by_field_name('arguments')
                arg_texts = [text(a) for a in args.named_children] if args else []
                validation_rules.append({
                    'id': identifier('VALID', relative, f'regexp:{node.start_byte}'),
                    'kind': 'regexp-constructor',
                    'pattern': arg_texts[0] if arg_texts else '',
                    'flags': arg_texts[1] if len(arg_texts) > 1 else '',
                    'ownerFunctionId': func_owner['id'] if func_owner else None,
                    'manifestRefs': list(func_owner['manifestRefs']) if func_owner else [],
                    'guards': guards(node),
                    **location(relative, node),
                })

        for call in descendants(root, 'call_expression'):
            callee = text(call.child_by_field_name('function'))
            func_owner = owner(call, records)
            args_node = call.child_by_field_name('arguments')
            args = [text(a) for a in args_node.named_children] if args_node else []

            if re.search(r'(?:^|\.)(?:yup|zod|z|Joi|validator)\.|(?:\.test|\.match|validate\w*|check\w*)$', callee):
                validation_rules.append({
                    'id': identifier('VALID', relative, f'{callee}:{call.start_byte}'),
                    'kind': 'validator-call',
                    'callee': callee,
                    'argumentExpressions': args[:4],
                    'ownerFunctionId': func_owner['id'] if func_owner else None,
                    'manifestRefs': list(func_owner['manifestRefs']) if func_owner else [],
                    'guards': guards(call),
                    **location(relative, call),
                })

            storage_match = re.match(
                r'^(?:window\.)?(localStorage|sessionStorage|indexedDB|caches|localforage|idb)\.(\w+)$',
                callee,
            )
            if storage_match:
                mechanism, op = storage_match.group(1), storage_match.group(2)
                key_expr = args[0].strip("'\"") if args else None
                flutter_target = (
                    'flutter_secure_storage'
                    if key_expr and SENSITIVE_KEY_PATTERN.search(key_expr)
                    else 'shared_preferences'
                    if mechanism in {'localStorage', 'sessionStorage'}
                    else 'drift_or_hive_offline_cache'
                )
                persistence.append({
                    'id': identifier('PERSIST', relative, f'{callee}:{call.start_byte}'),
                    'mechanism': mechanism,
                    'operation': f'{mechanism}.{op}',
                    'storageKey': key_expr,
                    'ownerFunctionId': func_owner['id'] if func_owner else None,
                    'manifestRefs': list(func_owner['manifestRefs']) if func_owner else [],
                    'flutterRecommendation': flutter_target,
                    **location(relative, call),
                })
            elif callee.endswith('addEventListener') and args and args[0].strip("'\"") in {'online', 'offline', 'storage'}:
                event_name = args[0].strip("'\"")
                persistence.append({
                    'id': identifier('PERSIST', relative, f'listener:{event_name}:{call.start_byte}'),
                    'mechanism': 'network-connectivity' if event_name in {'online', 'offline'} else 'cross-tab-storage',
                    'operation': f'addEventListener({event_name})',
                    'storageKey': event_name,
                    'ownerFunctionId': func_owner['id'] if func_owner else None,
                    'manifestRefs': list(func_owner['manifestRefs']) if func_owner else [],
                    'flutterRecommendation': 'connectivity_plus' if event_name in {'online', 'offline'} else 'riverpod_state_notifier',
                    **location(relative, call),
                })

    constraint_keys = {'required', 'pattern', 'minLength', 'maxLength', 'min', 'max', 'type', 'disabled', 'readOnly', 'error', 'helperText', 'rules', 'validate'}
    for elem in behavior.get('uiElements', []):
        props = elem.get('props', {})
        matched = {k: v for k, v in props.items() if k in constraint_keys}
        comp = elem.get('component', '')
        is_form_control = comp in {'input', 'textarea', 'select', 'TextField', 'Select', 'Autocomplete', 'Checkbox', 'Switch', 'FormControl'}
        if matched and (is_form_control or any(k in matched for k in ('required', 'pattern', 'error', 'validate', 'rules', 'minLength', 'maxLength'))):
            field_name = (props.get('name') or props.get('id') or props.get('label') or props.get('aria-label') or comp).strip("'\"{} ")
            validation_rules.append({
                'id': identifier('VALID', elem['sourceFile'], f"field:{comp}:{field_name}:{elem['sourceLine']}"),
                'kind': 'ui-field-constraint',
                'component': comp,
                'fieldName': field_name,
                'constraints': matched,
                'ownerFunctionId': elem.get('ownerFunctionId'),
                'guards': elem.get('guards', []),
                'sourceFile': elem['sourceFile'],
                'sourceLine': elem['sourceLine'],
                'sourceEndLine': elem['sourceEndLine'],
            })

    return validation_rules, persistence


def build_screen_inventory(manifest, behavior):
    """Build Screen Inventory & Mobile Routing Stack specification."""
    routes_by_id = {r['id']: r for r in manifest.get('routes', [])}
    actions = behavior.get('actions', [])
    screens_out = []
    shell_routes = []
    stack_screens = []
    modal_routes = []
    auth_routes = []

    for screen in manifest.get('screens', []):
        s_routes = [routes_by_id[rid] for rid in screen.get('routeIds', []) if rid in routes_by_id]
        paths = [r['path'] for r in s_routes]
        params = sorted({p for r in s_routes for p in r.get('params', [])})
        parent_routes = sorted({r['parentRouteId'] for r in s_routes if r.get('parentRouteId')})
        mui = set(screen.get('twakeMuiComponents', []))
        name_lower = screen['name'].lower()
        path_joined = ' '.join(paths).lower()

        if any(tok in name_lower or tok in path_joined for tok in ('login', 'callback', 'auth', 'sso', 'logout')):
            pattern = 'auth-callback-or-login'
            auth_routes.append(screen['id'])
        elif 'error' in name_lower or '/error' in path_joined:
            pattern = 'error-boundary-screen'
            stack_screens.append(screen['id'])
        elif any(p.endswith('/new') or p.endswith('/edit') for p in paths) or ('Dialog' in mui and not s_routes):
            pattern = 'modal-or-fullscreen-form'
            modal_routes.append(screen['id'])
        elif params or parent_routes:
            pattern = 'detail-or-parameterized-stack'
            stack_screens.append(screen['id'])
        elif bool(mui & {'Drawer', 'MobileTopBar', 'Tabs', 'BottomNavigation'}) or '/' in paths or len(s_routes) > 0:
            pattern = 'shell-drawer-or-tab-root'
            shell_routes.append(screen['id'])
        else:
            pattern = 'standard-stack-screen'
            stack_screens.append(screen['id'])

        screen_actions = [a for a in actions if screen['id'] in a.get('manifestRefs', []) or a['sourceFile'] == screen['sourceFile']]
        api_ids = sorted({
            flow_api
            for flow in manifest.get('flows', [])
            if flow.get('screenId') == screen['id']
            for flow_api in flow.get('apiCallIds', [])
        })
        screens_out.append({
            'screenId': screen['id'],
            'name': screen['name'],
            'sourceFile': screen['sourceFile'],
            'routeIds': screen.get('routeIds', []),
            'paths': paths,
            'routeParams': params,
            'parentRouteIds': parent_routes,
            'mobileRoutingPattern': pattern,
            'states': screen.get('states', ['default']),
            'childComponents': screen.get('childComponents', []),
            'childComponentIds': screen.get('childComponentIds', []),
            'actionIds': [a['id'] for a in screen_actions],
            'apiCallIds': api_ids,
            'hasWebMobileAdaptation': screen.get('hasWebMobileAdaptation', False),
            'mobileAdaptationNotes': screen.get('mobileAdaptationNotes', []),
        })

    return {
        'schemaVersion': '1.0.0',
        'app': manifest['app']['name'],
        'routerType': manifest['app']['routerType'],
        'targetFlutterRouter': manifest['app']['targetFlutterArchitecture']['router'],
        'mobileRoutingStack': {
            'shellRoutes': shell_routes,
            'stackScreens': stack_screens,
            'modalFlowScreens': modal_routes,
            'authAndCallbackScreens': auth_routes,
        },
        'routes': manifest.get('routes', []),
        'screens': screens_out,
    }


def build_ui_component_breakdown(manifest, gaps, behavior, widget_map=None, desktop_comparisons=None):
    """Flag web tables, complex sidebars, modals, nested dropdowns, and hover patterns for native mobile conversion."""
    mappings = (widget_map or {}).get('mappings', {})
    gaps_by_ref = defaultdict(list)
    for g in gaps:
        gaps_by_ref[g['manifestRef']].append(g)

    ui_elements_by_file = defaultdict(list)
    for el in behavior.get('uiElements', []):
        ui_elements_by_file[el['sourceFile']].append(el['component'])

    conversions = []
    for item in [*manifest.get('screens', []), *manifest.get('components', [])]:
        item_id = item['id']
        source_file = item['sourceFile']
        mui = set(item.get('twakeMuiComponents', []))
        tags = set(ui_elements_by_file.get(source_file, [])) | mui
        item_gaps = gaps_by_ref.get(item_id, [])
        has_mobile = item.get('hasWebMobileAdaptation', item.get('usesMobileBreakpoint', False))

        detected_patterns = []
        if tags & {'VirtualizedTable', 'Table', 'TableContainer', 'DataGrid', 'table'}:
            detected_patterns.append({
                'webPattern': 'web-table',
                'matchedComponents': sorted(tags & {'VirtualizedTable', 'Table', 'TableContainer', 'DataGrid', 'table'}),
                'recommendedNativePattern': 'card-list-or-filtered-mobile-columns',
                'rationale': 'Convert multi-column desktop tables to single-column list cards or filtered mobile columns with row overflow menu.',
            })
        if tags & {'Drawer', 'Sidebar', 'NavigationDrawer', 'NavDropdown', 'AddressBookNavItem'} or 'sidebar' in item['name'].lower():
            detected_patterns.append({
                'webPattern': 'complex-sidebar-or-drawer',
                'matchedComponents': sorted(tags & {'Drawer', 'Sidebar', 'NavigationDrawer', 'NavDropdown', 'AddressBookNavItem'}) or [item['name']],
                'recommendedNativePattern': 'modal-navigation-drawer-or-bottom-tabs',
                'rationale': 'Convert persistent desktop sidebars and nested navigation trees into a temporary modal Drawer or bottom navigation shell.',
            })
        if tags & {'Dialog', 'Modal', 'ConfirmModal', 'DialogContent', 'DialogActions'} or 'modal' in item['name'].lower() or 'dialog' in item['name'].lower():
            detected_patterns.append({
                'webPattern': 'modal-dialog',
                'matchedComponents': sorted(tags & {'Dialog', 'Modal', 'ConfirmModal', 'DialogContent', 'DialogActions'}) or [item['name']],
                'recommendedNativePattern': 'bottom-sheet-or-fullscreen-dialog',
                'rationale': 'Convert compact confirmation/action modals to modal bottom sheets and complex creation forms to full-screen mobile dialogs.',
            })
        if tags & {'Menu', 'MenuItem', 'Popover', 'Select', 'Autocomplete', 'Dropdown', 'DropdownMenu'}:
            detected_patterns.append({
                'webPattern': 'nested-dropdown-or-popover',
                'matchedComponents': sorted(tags & {'Menu', 'MenuItem', 'Popover', 'Select', 'Autocomplete', 'Dropdown', 'DropdownMenu'}),
                'recommendedNativePattern': 'modal-bottom-sheet-picker',
                'rationale': 'Convert anchored desktop popovers and nested dropdown menus into touch-friendly bottom sheet action lists.',
            })
        if any(g['category'] in {'hover-only-interaction', 'desktop-popover', 'context-menu'} for g in item_gaps):
            detected_patterns.append({
                'webPattern': 'hover-or-pointer-trigger',
                'matchedComponents': [g['category'] for g in item_gaps if g['category'] in {'hover-only-interaction', 'desktop-popover', 'context-menu'}],
                'recommendedNativePattern': 'explicit-overflow-menu-or-tap-target',
                'rationale': 'Replace hover-revealed actions or tooltips with always-visible mobile overflow buttons or tap-to-detail navigation.',
            })

        widget_mappings = [
            {
                'reactComponent': comp,
                'flutterWidget': mappings.get(comp, {}).get('flutterWidget'),
                'status': mappings.get(comp, {}).get('status', 'unimplemented'),
            }
            for comp in sorted(mui)
        ]

        conversions.append({
            'manifestId': item_id,
            'name': item['name'],
            'kind': 'screen' if item_id.startswith('SCREEN_') else 'component',
            'sourceFile': source_file,
            'hasWebMobileBranch': has_mobile,
            'twakeMuiMappings': widget_mappings,
            'patternConversions': detected_patterns,
            'gapIds': [g['id'] for g in item_gaps],
            'unresolvedGapIds': [g['id'] for g in item_gaps if g['status'] == 'unresolved-ask-user'],
        })

    return {
        'schemaVersion': '1.0.0',
        'app': manifest['app']['name'],
        'summary': {
            'totalItems': len(conversions),
            'itemsRequiringPatternConversion': sum(bool(c['patternConversions']) for c in conversions),
            'tablesCount': sum(any(p['webPattern'] == 'web-table' for p in c['patternConversions']) for c in conversions),
            'modalsCount': sum(any(p['webPattern'] == 'modal-dialog' for p in c['patternConversions']) for c in conversions),
            'sidebarsCount': sum(any(p['webPattern'] == 'complex-sidebar-or-drawer' for p in c['patternConversions']) for c in conversions),
            'dropdownsCount': sum(any(p['webPattern'] == 'nested-dropdown-or-popover' for p in c['patternConversions']) for c in conversions),
        },
        'desktopVsMobileComparisons': desktop_comparisons or [],
        'components': conversions,
    }
