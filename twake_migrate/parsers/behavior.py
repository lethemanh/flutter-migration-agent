"""Source-linked function, action and call inventory; unresolved edges stay explicit."""
from collections import defaultdict
import hashlib
import re
from pathlib import Path
from .javascript import descendants, text, string
from ..core.common import snake
from .source_resolution import alias_definitions, module_target, source_config_hashes

FUNCTIONS = {'function_declaration', 'generator_function_declaration', 'function_expression', 'generator_function', 'arrow_function', 'method_definition'}


def identifier(prefix, file, symbol):
    suffix = hashlib.sha256(f'{file}:{symbol}'.encode()).hexdigest()[:10].upper()
    return f'{prefix}_{snake(Path(file).stem)}_{snake(symbol)[:70]}_{suffix}'


def location(file, node):
    return dict(sourceFile=file, sourceLine=node.start_point.row + 1, sourceEndLine=node.end_point.row + 1)


def ancestors(node):
    while node.parent:
        node = node.parent
        yield node


def owner(node, records):
    return next((records[p.start_byte] for p in ancestors(node) if p.start_byte in records and p.type in FUNCTIONS), None)


def function_name(node):
    name = node.child_by_field_name('name')
    if name:
        return text(name)
    for parent in ancestors(node):
        if parent.type == 'variable_declarator':
            return text(parent.child_by_field_name('name'))
        if parent.type == 'pair':
            return text(parent.child_by_field_name('key')).strip("'\"")
        if parent.type in FUNCTIONS:
            break
    return 'anonymous'


def bindings(root):
    result = []
    for node in descendants(root, 'import_statement'):
        source = node.child_by_field_name('source')
        if source is None: continue
        specifier = string(source)
        for item in descendants(node, 'import_specifier'):
            if text(item).startswith('type '): continue
            name = text(item.child_by_field_name('name'))
            result.append((text(item.child_by_field_name('alias')) or name, name, specifier))
        for item in descendants(node, 'namespace_import'):
            result.append((text(item.named_children[-1]), '*', specifier))
        clause = next((n for n in node.named_children if n.type == 'import_clause'), None)
        if clause:
            result.extend((text(n), 'default', specifier) for n in clause.named_children if n.type == 'identifier')
    return result


def guards(node):
    result = []
    for parent in ancestors(node):
        if parent.type in {'if_statement', 'ternary_expression', 'conditional_expression', 'while_statement'}:
            condition = parent.child_by_field_name('condition')
            if condition: result.append(text(condition))
        elif parent.type == 'binary_expression' and any(c.type in ('&&','||','??') for c in parent.children):
            result.append(text(parent.child_by_field_name('left')))
    return list(dict.fromkeys(result))


def effect_kind(callee):
    if re.search(r'(^|\.)(fetch|request|get|post|put|patch|delete|del)\b', callee, re.I):
        return 'request-candidate'
    if re.search(r'(^|\.)(dispatch|emit|send|subscribe|unsubscribe)\b', callee): return 'state-or-message'
    if re.search(r'(^|\.)(navigate|redirect|open|push|replace)\b', callee): return 'navigation-candidate'
    if re.match(r'set[A-Z]', callee): return 'state-update'
    return None


def discover_behavior(web, parsed, manifest, source_aliases=None):
    files = set(parsed)
    definitions,alias_review=alias_definitions(web,parsed,source_aliases)
    resolve_import=lambda file,specifier:module_target(file,specifier,files,definitions,source_aliases)
    functions, actions, calls, unresolved, imports, ui_elements = [], [], [], [], [], []
    unresolved.extend(alias_review)
    by_node, by_name, exports, reexports = {}, defaultdict(list), {}, {}
    items = manifest['screens'] + manifest['components']
    refs = defaultdict(list)
    for item in items: refs[item['sourceFile']].append(item['id'])
    # Inventory every function, including callbacks and service implementations, before resolving calls.
    for file, root in parsed.items():
        relative = file.relative_to(web).as_posix()
        records, occurrences = {}, defaultdict(int)
        for node in descendants(root):
            if node.type not in FUNCTIONS: continue
            name = function_name(node)
            parent = owner(node, records)
            qualified = (parent['qualifiedName']+'.' if parent else '')+name
            occurrences[qualified] += 1
            symbol = qualified + (f'.{occurrences[qualified]}' if occurrences[qualified] > 1 else '')
            exported = any(p.type == 'export_statement' for p in ancestors(node)) and parent is None
            jsx_tags=sorted({text(n.child_by_field_name('name')) for n in descendants(node) if n.type in {'jsx_opening_element','jsx_self_closing_element'}})
            record = dict(jsxTags=jsx_tags,id=identifier('FUNC', relative, symbol), name=name, qualifiedName=symbol,
                          sourceRole='test-reference' if any(part in {'test','tests','e2e','__tests__'} for part in file.relative_to(web).parts) else 'application-or-tooling',
                          parentFunctionId=parent['id'] if parent else None, exported=exported,
                          manifestRefs=list(refs[relative]), callIds=[],
                          branches=[dict(kind=n.type,condition=text(n.child_by_field_name('condition')),**location(relative,n)) for n in descendants(node) if n.type in {'if_statement','ternary_expression','switch_statement','catch_clause','throw_statement'}],
                          **location(relative, node))
            records[node.start_byte] = record
            functions.append(record)
            by_name[(file, name)].append(record)
            if exported:
                exports[(file, name)] = record
                if any(p.type == 'export_statement' and re.search(r'\bdefault\b', text(p)[:30]) for p in ancestors(node)):
                    exports[(file, 'default')] = record
            # Inline named components are not equivalent to their containing TSX filename.
            if name[:1].isupper() and any(n.type in {'jsx_element','jsx_self_closing_element','jsx_fragment'} for n in descendants(node)):
                existing = next((i for i in items if i['sourceFile']==relative and i['name']==name), None)
                if not existing:
                    routes = [r for r in manifest['routes'] if r['component']==name]
                    is_screen = bool(routes)
                    new = dict(id=identifier('SCREEN' if is_screen else 'COMP', relative, name), name=name, sourceFile=relative,
                               sourceLine=record['sourceLine'], twakeMuiComponents=[], twakeIcons=[], twakeCssClasses=[], i18nKeys=[], childComponents=[])
                    if is_screen: new.update(routeIds=[r['id'] for r in routes], states=['default'],hasWebMobileAdaptation=False,mobileAdaptationNotes=[])
                    else: new.update(usesMobileBreakpoint=False,webOnlyRisks=[])
                    manifest['screens' if is_screen else 'components'].append(new)
                    items.append(new); refs[relative].append(new['id'])
                    record['manifestRefs'].append(new['id'])
        by_node[file] = records
        for local, imported, specifier in bindings(root):
            target = resolve_import(file, specifier)
            imports.append(dict(sourceFile=relative, localName=local, importedName=imported, specifier=specifier,
                                targetFile=target.relative_to(web).as_posix() if target else None))
        for node in descendants(root, 'export_statement'):
            source = node.child_by_field_name('source')
            target = resolve_import(file, string(source)) if source else file
            for item in descendants(node, 'export_specifier'):
                name = text(item.child_by_field_name('name'))
                alias = text(item.child_by_field_name('alias')) or name
                reexports[(file, alias)] = (target, name)
            if source and not list(descendants(node, 'export_specifier')):
                unresolved.append(dict(kind='wildcard-reexport', **location(relative,node), reason='Expand wildcard exports and reconcile consumers'))
    function_map={f['id']:f for f in functions}
    for item in items:
        implementation=next((f for f in functions if f['sourceFile']==item['sourceFile'] and f['name']==item['name']),None)
        if not implementation:continue
        tags=set(implementation['jsxTags']);root=parsed[web/item['sourceFile']]
        imports_for_component=bindings(root)
        item['twakeMuiComponents']=sorted({name if name!='default' else specifier.split('/')[-1] for local,name,specifier in imports_for_component if local in tags and specifier.startswith('@linagora/twake-mui')})
        item['twakeIcons']=sorted({name for local,name,specifier in imports_for_component if local in tags and specifier.startswith('@linagora/twake-icons') and name!='Icon'})
        children={i['id'] for i in items if i['sourceFile']==item['sourceFile'] and i['name'] in tags and i['id']!=item['id']}
        for local,name,specifier in imports_for_component:
            if local not in tags:continue
            target=resolve_import(web/item['sourceFile'],specifier)
            if target:
                candidates=[i for i in items if i['sourceFile']==target.relative_to(web).as_posix()]
                exact=[i for i in candidates if i['name']==name]
                children.update(i['id'] for i in exact or candidates)
        item['childComponentIds']=sorted(children)
    for f in functions:
        matching=[i['id'] for i in items if i['sourceFile']==f['sourceFile'] and i['name']==f['name']]
        if matching: f['manifestRefs']=matching
        elif f['parentFunctionId']: f['manifestRefs']=list(function_map[f['parentFunctionId']]['manifestRefs'])
    import_map = {(web/i['sourceFile'], i['localName']): i for i in imports}

    def exported(file, name, seen=None):
        seen = set() if seen is None else seen
        if (file, name) in seen: return None
        seen.add((file, name))
        if (file,name) in exports: return exports[(file,name)]
        if (file,name) in reexports:
            target, symbol = reexports[(file,name)]
            return exported(target,symbol,seen) if target else None
        candidates = by_name.get((file,name), [])
        return candidates[0] if len(candidates)==1 else None

    def resolve(file, name, caller):
        candidates = by_name.get((file,name), [])
        scopes = [caller['id']] if caller else []
        cursor = caller
        function_map = {f['id']:f for f in functions}
        while cursor and cursor['parentFunctionId']:
            scopes.append(cursor['parentFunctionId']);cursor=function_map[cursor['parentFunctionId']]
        for scope in [*scopes, None]:
            found = [f for f in candidates if f['parentFunctionId']==scope]
            if len(found)==1:return found[0]
        pieces=name.split('.')
        binding=import_map.get((file,pieces[0]))
        if binding and binding['targetFile']:
            symbol=pieces[1] if binding['importedName']=='*' and len(pieces)==2 else binding['importedName']
            return exported(web/binding['targetFile'],symbol)
        return None

    for file, root in parsed.items():
        relative=file.relative_to(web).as_posix();records=by_node[file]
        # Every call remains visible, even if runtime dispatch or an alias prevents resolution.
        for node in descendants(root, 'call_expression'):
            caller=owner(node,records);callee=text(node.child_by_field_name('function'))
            target=resolve(file,callee,caller)
            binding=import_map.get((file,callee.split('.')[0]))
            platform=callee in {'fetch','setTimeout','clearTimeout','setInterval','clearInterval'} or callee.startswith(('window.','document.','localStorage.','sessionStorage.','navigator.'))
            state='resolved' if target else 'platform-api' if platform else 'external-library' if binding and not binding['targetFile'] and not binding['specifier'].startswith('.') else 'unresolved'
            record=dict(id=identifier('CALL',relative,f'{callee}:{node.start_byte}'),callee=callee,
                        callerFunctionId=caller['id'] if caller else None,targetFunctionId=target['id'] if target else None,
                        argumentExpressions=[text(n) for n in node.child_by_field_name('arguments').named_children],
                        resolution=state,effect=effect_kind(callee),guards=guards(node),**location(relative,node))
            if record['effect']=='request-candidate' and (re.search(r'^(?:fetch|request)$|(?:api|http|client|dao|axios|ky)\b',callee,re.I) or binding and binding['specifier'] in {'axios','ky','node-fetch'}):
                api_id=record['id'].replace('CALL_', 'API_', 1)
                manifest['apiCalls'].append(dict(id=api_id,name=callee,kind='http-call',operation=callee,**location(relative,node)))
                record['apiCallId']=api_id
                if caller and api_id not in caller['manifestRefs']:caller['manifestRefs'].append(api_id)
            calls.append(record)
            if caller: caller['callIds'].append(record['id'])
            if state=='unresolved' and not re.match(r'^(?:set[A-Z]|use[A-Z]|(?:Object|Array|Math|JSON|Promise|console)\.)',callee):
                unresolved.append(dict(kind='unresolved-call',callId=record['id'],callee=callee,**location(relative,node),reason='Resolve wrapper, object method, alias or dynamic dispatch during source review'))
        for node in descendants(root):
            if node.type in {'jsx_opening_element','jsx_self_closing_element'}:
                component_owner=owner(node,records)
                props={}
                for attribute in node.named_children:
                    if attribute.type=='jsx_attribute' and attribute.named_children:
                        props[text(attribute.named_children[0])]=text(attribute.named_children[1]) if len(attribute.named_children)>1 else 'true'
                ui_elements.append(dict(component=text(node.child_by_field_name('name')),ownerFunctionId=component_owner['id'] if component_owner else None,props=props,guards=guards(node),**location(relative,node)))
            event=None;expression=None;component=None
            if node.type=='jsx_attribute' and node.named_children:
                event=text(node.named_children[0])
                if not re.match(r'^on[A-Z]',event):continue
                expression=node.named_children[1] if len(node.named_children)>1 else None
                component=text(node.parent.child_by_field_name('name')) if node.parent else None
            elif node.type=='pair':
                event=text(node.child_by_field_name('key')).strip("'\"")
                if not re.match(r'^on[A-Z]',event):continue
                expression=node.child_by_field_name('value');component='configuration callback'
            else:continue
            caller=owner(node,records)
            direct=[]
            if expression:
                for child in descendants(expression):
                    if child.type in FUNCTIONS and child.start_byte in records: direct.append(records[child.start_byte]['id'])
                    elif child.type=='identifier':
                        target=resolve(file,text(child),caller)
                        if target:direct.append(target['id'])
            if caller: action_refs=list(caller['manifestRefs'])
            else: action_refs=list(refs[relative])
            line=node.start_point.row+1
            label=None
            if node.type=='jsx_attribute':
                for attribute in node.parent.named_children:
                    if attribute.type=='jsx_attribute' and text(attribute.named_children[0]) in {'aria-label','title','label'} and len(attribute.named_children)>1:
                        label=text(attribute.named_children[1]);break
                if not label and node.parent.parent and node.parent.parent.type=='jsx_element':
                    labels=[text(n).strip() for n in node.parent.parent.named_children if n.type in {'jsx_text','jsx_expression'} and text(n).strip()]
                    label=' '.join(labels)[:160] or None
            elif node.parent and node.parent.type=='object':
                label_pair=next((p for p in node.parent.named_children if p.type=='pair' and text(p.child_by_field_name('key')).strip("'\"") in {'label','title','name'}),None)
                if label_pair:label=text(label_pair.child_by_field_name('value'))[:160]
            name=f'{component}.{event}'+(' — '+label if label else '')
            handlers=sorted(set(direct))
            ui_conditions={}
            if node.type=='jsx_attribute':
                for attribute in node.parent.named_children:
                    if attribute.type=='jsx_attribute' and text(attribute.named_children[0]) in {'disabled','hidden','readOnly','required','loading'}:
                        ui_conditions[text(attribute.named_children[0])]=text(attribute.named_children[1]) if len(attribute.named_children)>1 else 'true'
            actions.append(dict(labelExpression=label,uiConditions=ui_conditions,id=identifier('ACTION',relative,f'{name}:{node.start_byte}'),name=name,event=event,component=component,
                                ownerFunctionId=caller['id'] if caller else None,handlerFunctionIds=handlers,
                                handlerExpression=text(expression) if expression else None,guards=guards(node),
                                manifestRefs=action_refs,runtimeStatus='not-observed',**location(relative,node)))
            if not handlers:
                unresolved.append(dict(kind='unresolved-handler',actionId=actions[-1]['id'],**location(relative,node),reason='Resolve callback props or dynamic handler before migration'))
        for node in descendants(root):
            if not (node.type=='jsx_spread_attribute' or node.type=='spread_element' and node.parent.type=='jsx_expression' and node.parent.parent.type in {'jsx_opening_element','jsx_self_closing_element'}):continue
            unresolved.append(dict(kind='spread-props',**location(relative,node),reason='Inspect spread props for event handlers and conditional UI'))

    function_map={f['id']:f for f in functions};call_map={c['id']:c for c in calls}
    module_edges=defaultdict(set)
    for imported in imports:
        if imported['targetFile']:module_edges[imported['sourceFile']].add(imported['targetFile'])
    def reaches(start,target):
        pending=[start];seen=set()
        while pending:
            current=pending.pop()
            if current==target:return True
            if current not in seen:seen.add(current);pending.extend(module_edges[current])
        return False
    for action in actions:
        pending=list(action['handlerFunctionIds']);reachable=set();edges=set()
        while pending:
            function_id=pending.pop()
            if function_id in reachable:continue
            reachable.add(function_id)
            for call_id in function_map[function_id]['callIds']:
                edges.add(call_id)
                target=call_map[call_id]['targetFunctionId']
                if target:pending.append(target)
            # Higher-order wrappers and async callbacks are part of their parent's behavior.
            pending.extend(f['id'] for f in functions if f['parentFunctionId']==function_id)
        action['reachableFunctionIds']=sorted(reachable)
        action['callIds']=sorted(edges)
        action['effects']=[call_map[c] for c in sorted(edges) if call_map[c]['effect']]
        action['unresolvedCallIds']=[c for c in sorted(edges) if call_map[c]['resolution']=='unresolved']
        screens=[s for s in manifest['screens'] if reaches(s['sourceFile'],action['sourceFile'])]
        for screen in screens:
            flow_id=identifier('FLOW',action['sourceFile'],action['id']+screen['id'])
            manifest['flows'].append(dict(id=flow_id,name=action['name'],screenId=screen['id'],sourceFile=action['sourceFile'],
                                         sourceLine=action['sourceLine'],trigger=action['event'],
                                         steps=[f"Invoke {action['name']}",*[f"Preserve {function_map[f]['qualifiedName']}" for f in sorted(reachable)]],
                                         apiCallIds=sorted({call_map[c]['apiCallId'] for c in edges if call_map[c].get('apiCallId')}),sourceActionId=action['id']))
            action['manifestRefs'].append(flow_id)
    reached={f for action in actions for f in action['reachableFunctionIds']}
    return dict(schemaVersion='1.0.0',sourceAliases=source_aliases or {},sourceConfigHashes=source_config_hashes(web),functions=functions,actions=actions,calls=calls,imports=imports,uiElements=ui_elements,
                unassignedFunctionIds=sorted(f['id'] for f in functions if f['id'] not in reached and not f['manifestRefs']),
                reviewRequired=unresolved,complete=False,
                limitations=['Dynamic dispatch, callback props, aliases and library internals require source review; unresolved edges are never proof of absence.',
                             'Every function needs a reviewed disposition: feature behavior, shared utility, framework glue or excluded with reason.'])
