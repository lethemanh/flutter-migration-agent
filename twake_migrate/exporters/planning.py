from pathlib import Path
import copy
import re
from ..core.common import load, write_json, now, GROUPS, HELPERS, snake, digest, discovery_fingerprint
from ..core.validation import feature_refs
from ..core.discovery_review import build_discovery_review, render_discovery_plan


def plan_migration(manifest_path, gap_report_path, out_dir, widget_map_path=None, approve=False, runtime_report_path=None):
    existing = Path(out_dir) / 'migration-plan.json'
    manifest, gaps = load(manifest_path), load(gap_report_path)['gaps']
    previous = load(existing) if existing.is_file() else {}
    prior_approval = previous.get('approval', {})
    scope = dict(manifest=discovery_fingerprint(manifest), gaps=digest(gap_report_path))
    preserve_approval = prior_approval.get('status') == 'approved'
    if preserve_approval and previous.get('approvedScope') != scope:
        raise ValueError('Refusing to overwrite approval for a changed or legacy scope; use a separate plan directory')
    mappings = load(widget_map_path)['mappings'] if widget_map_path and Path(widget_map_path).is_file() else {}
    audit_path=Path(manifest_path).with_name('discovery-audit.json')
    runtime_path=Path(runtime_report_path) if runtime_report_path else Path(manifest_path).with_name('runtime-discovery.json')
    discovery=build_discovery_review(manifest,manifest_path,load(audit_path) if audit_path.is_file() else {},load(runtime_path) if runtime_path.is_file() else {},runtime_path)
    if preserve_approval and any(previous['discoveryReview'].get(key) != discovery[key]
                                 for key in ('sourceHashes', 'sourceConfigHashes')):
        raise ValueError('Refusing to refresh approval after source changes; use a separate plan directory')
    if approve and not discovery['readyForApproval']:
        raise ValueError('Discovery is not ready for approval: '+'; '.join(discovery['blockers']))
    approve = approve or preserve_approval
    unresolved = [g for g in gaps if g['status']=='unresolved-ask-user']
    libraries = []
    for library in manifest['twakeLibraries']:
        symbols = library.get('usedSymbols',[])
        missing = [s for s in symbols if s not in HELPERS and not s.endswith('Props') and mappings.get(s,{}).get('status','unimplemented')=='unimplemented'] if library['package']=='@linagora/twake-mui' else []
        libraries.append({**library,'usedSymbolsCount':len(symbols),'unmappedSymbols':missing,'status':'requires-widget-or-decision' if missing else 'requires-port' if library['status']=='requires-port' else 'ready'})
    all_items = {i['id']:i for group in GROUPS for i in manifest[group]}
    waves = copy.deepcopy(load(Path(__file__).resolve().parent.parent/'templates/waves.json'))
    used = set()
    categories={i['id']:g for g in GROUPS for i in manifest[g]}
    def classify(item_id):
        item=all_items[item_id];category=categories[item_id]
        if category=='routes':return 1
        if category=='apiCalls':return 0
        if category=='flows':return 6
        if re.search(r'login|auth|callback|error',item.get('name',''),re.I):return 1
        if category=='screens':return 3
        return 2
    for wave in waves:
        for step in wave['steps']:
            step['manifestIds']=[i for i in step['manifestIds'] if i in all_items]
            used.update(step['manifestIds'])
            if step['manifestIds']: step['sourceFiles']=sorted({all_items[i]['sourceFile'] for i in step['manifestIds']})
    for item_id,item in all_items.items():
        if item_id in used: continue
        number = classify(item_id)
        source=Path(item['sourceFile']);parts=source.parts
        module=snake(parts[parts.index('features')+1]).lower() if 'features' in parts and parts.index('features')+1<len(parts) else 'shared'
        stem=snake(item.get('name',source.parent.name) if source.stem=='index' else source.stem).lower()
        category=categories[item_id]
        if category=='routes':target='lib/core/routing/app_router.dart'
        elif category=='flows':target=f'test/features/{module}/{stem}_flow_test.dart'
        elif category=='apiCalls':target=f'lib/core/services/{stem}.dart'
        else:target=f'lib/features/{module}/'+('screens' if category=='screens' else 'widgets')+f'/{stem}.dart'
        waves[number]['steps'].append(dict(stepId='STEP_'+item_id,title=('Verify ' if category=='flows' else 'Port ')+item.get('name',item_id),manifestIds=[item_id],sourceFiles=[item['sourceFile']],targetFlutterFile=target,twakeDependencies=['@linagora/twake-mui'] if item.get('twakeMuiComponents') else [],mobileStrategy='Copy the manifest feature and the existing web mobile branch.',blockingGaps=[],status='ready'))
    for feature in discovery['features']:
        if not feature.get('actions'):continue
        refs=sorted({r for a in feature['actions'] for r in a['manifestRefs'] if r in all_items})
        waves[4]['steps'].append(dict(stepId='STEP_ACTIONS_'+feature['featureId'],title='Implement reviewed actions for '+feature['name'],manifestIds=refs,sourceFiles=sorted({a['sourceFile'] for a in feature['actions']}),targetFlutterFile='lib/features/'+re.sub(r'[^a-z0-9_]+','_',feature['name'].lower())+'/providers/actions.dart',twakeDependencies=[],mobileStrategy='Trace handlers, guards, service outcomes and observed original UI states; see migration-tasks.json action subtasks.',blockingGaps=[],status='ready'))
    for library in libraries:
        if library['status']!='requires-port':continue
        name=library['package']
        sources=sorted({i['sourceFile'] for i in manifest.get('behavior',{}).get('imports',[]) if i['specifier']==name or i['specifier'].startswith(name+'/')})
        waves[5]['steps'].append(dict(stepId='STEP_LIBRARY_'+re.sub(r'[^a-zA-Z0-9]+','_',name).upper(),title='Preserve used '+name+' implementation behavior',manifestIds=[],sourceFiles=sources or ['package.json'],targetFlutterFile='lib/core/integrations/'+re.sub(r'[^a-z0-9]+','_',name.lower())+'.dart',twakeDependencies=[name],mobileStrategy='Inspect the configured library implementation for the exact imported symbols and observed behavior.',blockingGaps=[],status='ready'))
    for wave in waves:
        for step in wave['steps']:
            refs = set().union(*(feature_refs(manifest, item_id) for item_id in step['manifestIds']))
            step['blockingGaps']=[g['id'] for g in unresolved if g['manifestRef'] in refs]
            missing=[name for item_id in refs for name in all_items[item_id].get('twakeMuiComponents',[]) if mappings.get(name,{}).get('status','unimplemented')=='unimplemented']
            step['blockingComponents']=sorted(set(missing))
            step['blockingDiscovery'] = [item_id for item_id in step['manifestIds']
                                         if not discovery['featureReadiness'][item_id]['ready']]
            step['status']='blocked' if step['blockingGaps'] or missing or step['blockingDiscovery'] else 'ready'
        wave['status']='blocked-by-gaps' if any(s['blockingGaps'] for s in wave['steps']) else 'blocked-by-components' if any(s.get('blockingComponents') for s in wave['steps']) else 'blocked-by-discovery' if any(s['blockingDiscovery'] for s in wave['steps']) else 'ready'
    counts={g:len(manifest[g]) for g in GROUPS}
    counts.update(locales=len(manifest['i18n']['locales']),i18nKeys=manifest['i18n']['totalKeys'],resolvedMobileGaps=sum(g['status']!='unresolved-ask-user' for g in gaps),unresolvedMobileGaps=len(unresolved))
    plan=dict(schemaVersion='1.0.0',app={**{k:manifest['app'][k] for k in ('name','version','sourceRoot')},'targetFlutterPackage':'twake_'+Path(manifest['app']['sourceRoot']).name.replace('twake-','').replace('-frontend','').replace('-','_')+'_mobile'},approval=dict(status='approved' if approve else 'pending-review',reviewedBy='human-reviewer' if approve else None,reviewedAt=now() if approve else None),discoveredFeaturesSummary=dict(counts=counts,**{g:manifest[g] for g in GROUPS},i18n=manifest['i18n']),twakeLibrariesReport=libraries,waves=waves)
    if approve:
        plan['approvedScope'] = scope
    if preserve_approval:
        plan['approval'] = prior_approval
    plan['runtimeReportPath'] = str(runtime_path.resolve())
    plan['discoveryReview']={k:v for k,v in discovery.items() if k not in {'tasks','features','functionReview'}}
    plan['featureBreakdown']=discovery['features']
    plan['tasks']=discovery['tasks']
    plan['humanFeatures']=manifest.get('humanFeatures',[])
    if approve:
        for feature in discovery['features']:feature['reviewStatus']='approved'
        for task in discovery['tasks']:
            if task['taskId']=='TASK_HUMAN_PLAN_APPROVAL':task['status']='done'
            elif task['status']=='pending-review':task['status']='pending'
            for subtask in task.get('subtasks',[]):subtask['status']='pending'
    out=Path(out_dir).resolve()
    write_json(out/'migration-tasks.json',dict(schemaVersion='1.0.0',approval=plan['approval'],tasks=discovery['tasks']))
    write_json(out/'feature-review.json',dict(schemaVersion='1.0.0',**discovery))
    write_json(out/'migration-plan.json',plan)
    (out/'migration-plan.md').write_text(render_discovery_plan(plan,discovery,gaps))
    return dict(taskListPath=str(out/'migration-tasks.json'),featureReviewPath=str(out/'feature-review.json'),planJsonPath=str(out/'migration-plan.json'),planMdPath=str(out/'migration-plan.md'),plan=plan)
