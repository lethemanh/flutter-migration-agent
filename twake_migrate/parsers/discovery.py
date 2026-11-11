from pathlib import Path
import re
from ..core.common import load, write_json, now, walk, snake, flatten, HELPERS, digest
from .javascript import parse, descendants, text, string
from .behavior import discover_behavior
from .route_discovery import routes_from_objects


def imports(root):
    result = []
    for node in descendants(root,'import_statement'):
        package = string(node.child_by_field_name('source'))
        names = []
        for specifier in descendants(node,'import_specifier'):
            if text(specifier).startswith('type '): continue
            names.append(text(specifier.child_by_field_name('name')))
        clause = next((n for n in node.named_children if n.type == 'import_clause'),None)
        if clause:
            names.extend(text(n) for n in clause.named_children if n.type == 'identifier')
        result.append((package,names))
    return result


def routes_from_ast(root, source_file):
    routes = []
    def visit(node, parent=None):
        opening = node.child_by_field_name('open_tag') if node.type == 'jsx_element' else node if node.type == 'jsx_self_closing_element' else None
        if opening and text(opening.child_by_field_name('name')) == 'Route':
            attributes = {}
            for attribute in (n for n in opening.named_children if n.type == 'jsx_attribute'):
                key = text(attribute.named_children[0])
                attributes[key] = attribute.named_children[1] if len(attribute.named_children)>1 else None
            elements = list(descendants(attributes['element'])) if attributes.get('element') else []
            component_node = next((n for n in elements if n.type in ('jsx_self_closing_element','jsx_opening_element')),None)
            if component_node:
                component = text(component_node.child_by_field_name('name'))
                index = 'index' in attributes
                raw = 'index' if index else string(attributes['path']) if attributes.get('path') else '/'
                route_path = parent['path'] if parent and index else parent['path'].rstrip('/')+'/'+raw if parent and not raw.startswith('/') else raw
                suffix = 'ROOT' if route_path == '/' else snake(route_path.replace(':','BY_'))+('_INDEX' if index else '')
                route = dict(id='ROUTE_'+suffix,path=route_path,component=component,sourceFile=source_file,params=re.findall(r':(\w+)',route_path),parentRouteId=parent['id'] if parent and not raw.startswith('/') else None)
                routes.append(route)
                parent = route
            if node.type == 'jsx_element':
                for child in node.named_children:
                    if child.type not in ('jsx_opening_element','jsx_closing_element'): visit(child,parent)
            return
        for child in node.named_children: visit(child,parent)
    visit(root)
    return routes


def source_files(web):
    return [p for p in walk(web,{'.ts','.tsx','.js','.jsx'}) if not p.name.endswith(('.test.ts','.test.tsx','.spec.ts','.spec.tsx','.test.js','.test.jsx','.spec.js','.spec.jsx','.d.ts'))]


def discover_static(web_root, out_dir, approve=False, source_aliases=None):
    existing = Path(out_dir) / 'feature-manifest.json'
    if existing.is_file() and load(existing).get('approval', {}).get('status') == 'approved':
        raise ValueError('Refusing to overwrite approved feature-manifest.json; refresh into a separate directory and reconcile changes')
    web = Path(web_root).resolve()
    package = load(web/'package.json')
    files = source_files(web)
    parsed, sources, file_imports = {},{},{}
    for file in files:
        src = file.read_text()
        try: root = parse(src,'tsx' if file.suffix in ('.tsx','.jsx') else 'ts' if file.suffix == '.ts' else 'js')
        except ValueError as error: raise ValueError(f'{file.relative_to(web)}: {error}') from error
        parsed[file],sources[file],file_imports[file] = root,src,imports(root)
    dependencies = {**package.get('dependencies',{}),**package.get('devDependencies',{})}
    for file in walk(web, {'.json'}):
        if file.name == 'package.json' and file != web/'package.json':
            child = load(file)
            for name, version in {**child.get('dependencies',{}), **child.get('devDependencies',{})}.items():
                dependencies.setdefault(name, version)
    def package_name(value):
        return '/'.join(value.split('/')[:2]) if value.startswith('@') else value.split('/')[0]
    imported_packages = {package_name(pkg) for pairs in file_imports.values() for pkg, _ in pairs if not pkg.startswith(('.', '/'))}
    for name in imported_packages:
        if name.startswith(('@linagora/', 'twake-', 'cozy-')):
            dependencies.setdefault(name, 'imported; version requires resolution')
    css_classes = sorted({c for src in sources.values() for c in re.findall(r'\bu-[a-z0-9-]+',src)})
    catalog = load(Path(__file__).resolve().parent.parent/'templates/libraries.json')
    known = {entry['package'] for entry in catalog}
    for name in sorted(dependencies):
        if name.startswith(('@linagora/', 'twake-', 'cozy-')) and name not in known:
            catalog.append(dict(package=name,category='utils',strategy='port-dart',flutterTarget='Inspect configured library implementation and map its used behavior before porting',status='requires-port'))
    libraries = []
    for entry in catalog:
        name = entry['package']
        version = dependencies.get(name) or ('peer-of-twake-mui' if name == '@linagora/twake-css' and '@linagora/twake-mui' in dependencies else None)
        if not version: continue
        symbols = css_classes if name == '@linagora/twake-css' else sorted({sym for pairs in file_imports.values() for pkg,names in pairs if pkg == name or pkg.startswith(name+'/') for sym in names})
        libraries.append({**entry,'versionSpec':version,'usedSymbols':symbols})
    routes = []
    route_review = []
    for file in files:
        relative=str(file.relative_to(web))
        routes.extend(routes_from_ast(parsed[file],relative))
        object_routes, unresolved_routes=routes_from_objects(parsed[file],relative)
        routes.extend(object_routes);route_review.extend(unresolved_routes)
    screens,components,flows,apis,gaps = [],[],[],[],[]
    for file in files:
        relative = file.relative_to(web).as_posix()
        for node in descendants(parsed[file],'variable_declarator'):
            name = text(node.child_by_field_name('name'))
            if name.endswith('Thunk') and node.parent and node.parent.parent and node.parent.parent.type == 'export_statement':
                action = name.removesuffix('Thunk')
                if 'API_'+snake(action) not in {a['id'] for a in apis}: apis.append(dict(id='API_'+snake(action),name=action,kind='redux-thunk',sourceFile=relative,operation=name))
        if 'websocket/operations/' in relative and file.name != 'index.ts':
            apis.append(dict(id='API_WS_'+snake(file.stem),name=file.stem,kind='websocket-op',sourceFile=relative,operation='websocket:'+file.stem))
    for file in files:
        if file.suffix not in ('.tsx','.jsx') or file.stem in ('index','App','AppRoutes'): continue
        name,src,root = file.stem,sources[file],parsed[file]
        relative = file.relative_to(web).as_posix()
        imported = {}
        for pkg,names in file_imports[file]: imported.setdefault(pkg,set()).update(names)
        mui = sorted(n for n in imported.get('@linagora/twake-mui',set()) if n not in HELPERS and not n.endswith('Props'))
        icons = sorted(imported.get('@linagora/twake-icons',set())-{'Icon'})
        css = sorted(set(re.findall(r'\bu-[a-z0-9-]+',src)))
        keys = sorted({string(n.child_by_field_name('arguments').named_children[0]) for n in descendants(root,'call_expression') if text(n.child_by_field_name('function')) == 't' and n.child_by_field_name('arguments').named_children and n.child_by_field_name('arguments').named_children[0].type == 'string'})
        mobile = 'useBreakpoints' in imported.get('@linagora/twake-mui',set()) or bool(re.search(r'\bisMobile\b',src))
        children = [n for pkg,names in file_imports[file] if pkg.startswith('.') for n in names if n and n[0].isupper()]
        states = ['default']
        for state,pattern in [('loading',r'\bloading\b|\bisLoading\b|<Skeleton|<CircularProgress'),('error',r'\berror\b|<Alert|<Error'),('empty',r'EmptyState|entries\.length === 0'),('modal',r'Dialog|Modal|Open')]:
            if re.search(pattern,src): states.append(state)
        matches = [r for r in routes if r['component']==name or name=='Error' and r['component']=='ErrorPage']
        screen = bool(matches) or name.endswith('Page')
        item_id = ('SCREEN_' if screen else 'COMP_')+snake(name)
        notes = []
        if mobile:
            for token,note in [('MobileTopBar','Renders MobileTopBar with drawer burger button and search toggle on small viewports.'),('<Fab','Renders floating action button (Fab) on mobile address book screen.'),('allColumns.filter','Filters VirtualizedTable columns on mobile to only contact.displayName and actions.'),('Drawer','Switches sidebar to temporary Drawer on mobile.')]:
                if token in src: notes.append(note)
        def gap(suffix,category,description,resolved=False,alternative=None):
            gaps.append(dict(id='GAP_'+snake(name)+'_'+suffix,manifestRef=item_id,sourceFile=relative,category=category,description=description,webHasMobileView=resolved,webMobileAlternative=alternative,status='resolved-by-web-mobile-view' if resolved else 'unresolved-ask-user',resolution='Copy the web mobile branch.' if resolved else None))
        if any(t in src for t in (':hover','mousemove','onMouseEnter')):
            adapted = mobile and '!isMobile' in src
            gap('HOVER' if adapted else 'HOVER_POPOVER','hover-only-interaction' if adapted else 'desktop-popover',f'{name} uses hover or pointer interactions'+(' with a !isMobile fallback.' if adapted else ' without a mobile fallback.'),adapted,'Use the existing mobile dropdown action.' if adapted else None)
        if 'VirtualizedTable' in mui:
            table_mobile = mobile and bool(re.search(r'(?:allColumns|columns)\.filter', src)) and 'isMobile' in src
            gap('TABLE' if table_mobile else 'WIDE_TABLE','wide-table',f'{name} renders a virtualized table'+(' with a candidate mobile column filter; confirm it at runtime.' if table_mobile else ' without a verified mobile column adaptation.'),table_mobile,'Copy the mobile column filter after confirming runtime behavior.' if table_mobile else None)
        if re.search(r'window\.(MAIL_SPA_URL|CALENDAR_SPA_URL|CHAT_SPA_URL)',src): gap('CROSS_APP_URLS','browser-specific-api',f'{name} opens sibling web apps using window SPA URLs. A mobile launch policy needs user review.')
        item = dict(id=item_id,name=name,sourceFile=relative,twakeMuiComponents=mui,twakeIcons=icons,twakeCssClasses=css,i18nKeys=keys)
        if screen:
            item.update(routeIds=[r['id'] for r in matches],childComponents=children,states=states,hasWebMobileAdaptation=mobile,mobileAdaptationNotes=notes)
            screens.append(item)
        else:
            item.update(childComponents=children,usesMobileBreakpoint=mobile,webOnlyRisks=[g['id'] for g in gaps if g['manifestRef']==item_id])
            components.append(item)
    locale_files = [p for p in walk(web,{'.json'}) if 'locales' in p.parts]
    en = next((p for p in locale_files if p.name=='en.json'),locale_files[0] if locale_files else None)
    keys = sorted(flatten(load(en))) if en else []
    router_version=dependencies.get('react-router') or dependencies.get('react-router-dom')
    router_major=re.search(r'\d+',router_version) if router_version else None
    router_type='react-router-v'+router_major[0] if router_major else 'react-router-detected' if routes else 'source-review-required'
    source_state='redux-toolkit' if '@reduxjs/toolkit' in dependencies else 'source-review-required'
    manifest = dict(schemaVersion='1.0.0',app=dict(name=package.get('name',web.name),version=package.get('version','0.1.0'),sourceRoot=str(web),routerType=router_type,stateManagement=source_state,targetFlutterArchitecture=dict(stateManagement='flutter_riverpod',router='go_router',folderStructure='feature-first',designPackage='twake_flutter_ui')),approval=dict(status='approved' if approve else 'draft',reviewedBy='human-reviewer' if approve else None,reviewedAt=now() if approve else None,notes='Manifest approved.' if approve else 'Requires human review before porting.'),twakeLibraries=libraries,routes=routes,screens=screens,components=components,flows=flows,apiCalls=apis,i18n=dict(locales=sorted(p.stem for p in locale_files),totalKeys=len(keys),keys=keys))
    behavior = discover_behavior(web, parsed, manifest, source_aliases)
    manifest['behavior'] = behavior
    try:
        from ..core.source_checkpoint import git
        manifest['sourceCommit']=git(web,'rev-parse','HEAD')
    except ValueError: manifest['sourceCommit']=None
    limitations = list(route_review)
    for file, src in sources.items():
        relative = file.relative_to(web).as_posix()
        for pattern, reason in [
            (r'\b(createBrowserRouter|createHashRouter|useRoutes)\s*\(', 'Object-based router: reconcile extracted routes and unresolved dynamic entries'),
            (r'\b(fetch|axios\.(?:get|post|put|patch|delete)|createAsyncThunk)\s*\(', 'Confirm request/action coverage and indirect service calls'),
            (r'\b(?:onClick|onSubmit|onChange|onDrop)\s*=', 'Review event handlers and record each user journey, including secondary actions'),
        ]:
            if re.search(pattern, src): limitations.append(dict(sourceFile=relative, reason=reason))
    audit = dict(schemaVersion='1.0.0', sourceReconciliation=dict(status='pending',reviewedBy=None,notes=None), review=dict(status='pending-review',reviewedBy=None,notes=None), sourceHashes={str(f.relative_to(web)):digest(f) for f in files}, scannedFiles=sorted(str(f.relative_to(web)) for f in files), automaticInventoryIsExhaustive=False, reviewRequired=limitations, notes=['Review dynamic routes, aliases, re-exports, inline components, API wrappers and every handler against the manifest before approval. Generated primary flows are candidates, not exhaustive behavior specifications.'])
    report = dict(schemaVersion='1.0.0',app=manifest['app']['name'],gaps=gaps)
    out = Path(out_dir).resolve()
    from ..exporters.markdown_spec import generate_discovery_specs
    spec_outputs = generate_discovery_specs(web, parsed, manifest, gaps, behavior, out)
    audit['behaviorCounts']={key:len(behavior[key]) for key in ('functions','actions','calls','reviewRequired','unassignedFunctionIds')}
    audit['specCounts']=spec_outputs['specCounts']
    write_json(out/'source-behavior.json',behavior)
    write_json(out/'runtime-capture-plan.template.json',dict(requireThemeColorChange=True,crawl=dict(maxPages=25,maxSteps=30,timeoutSeconds=60),routes={r['id']:dict(skipReason='Supply a real route fixture') if ':' in r['path'] else dict(path=r['path']) for r in routes},journeys=[],actionChecklist=[dict(sourceActionId=a['id'],name=a['name'],sourceFile=a['sourceFile'],sourceLine=a['sourceLine'],guards=a['guards'],uiConditions=a['uiConditions'],status='needs-browser-observation') for a in behavior['actions']]))
    write_json(out/'discovery-audit.json',audit)
    write_json(out/'feature-manifest.json',manifest)
    write_json(out/'gap-report.json',report)
    summary = [f"# Discovery Summary: {manifest['app']['name']}",f"Source: `{web}`",f"Approval: {manifest['approval']['status']}"]
    for group in ('routes','screens','components','flows','apiCalls','twakeLibraries'):
        summary.append('\n## '+group)
        summary.extend('- '+str(item) for item in manifest[group])
    summary.append('\n## Locales and keys\n'+str(manifest['i18n']))
    summary.append('\n## Source behavior inventory\n'+str(audit['behaviorCounts'])+'\nSee source-behavior.json for every function, handler, call edge, branch and unresolved reference. Unassigned functions require review; they are not silently excluded.')
    summary.append('\n## Structured Mobile Output Specs\n'+str(spec_outputs['specCounts'])+'\nSee screen-inventory.json, ui-component-breakdown.json, api-data-contracts.json, and state-validation-matrix.json.')
    summary.append('\n## Discovery limits\nAutomatic inventory requires source review. See discovery-audit.json for file coverage and candidate missing behavior.')
    summary.append('\n## Mobile gaps\n'+'\n'.join('- '+str(g) for g in gaps))
    (out/'discovery-summary.md').write_text('\n'.join(summary)+'\n')
    return dict(manifestPath=str(out/'feature-manifest.json'),gapReportPath=str(out/'gap-report.json'),summaryPath=str(out/'discovery-summary.md'),**spec_outputs,manifest=manifest,gapReport=report)
