"""Reconcile code behavior and original UI, then group features into migration tasks."""
from pathlib import Path
from .common import GROUPS, digest, discovery_fingerprint
from .source_guards import review_source_guards
from .validation import feature_refs


def build_discovery_review(manifest, manifest_path, audit, runtime, runtime_path):
    from ..parsers.behavior import identifier
    from ..parsers.discovery import source_files
    from ..parsers.source_resolution import source_config_hashes
    behavior=manifest.get('behavior',{})
    functions={f['id']:f for f in behavior.get('functions',[])}
    actions=behavior.get('actions',[])
    source_root=Path(manifest['app']['sourceRoot']).resolve()
    current_sources={p.relative_to(source_root).as_posix():digest(p) for p in source_files(source_root)}
    review=audit.get('review',{})
    reconciliation=audit.get('sourceReconciliation',{})
    agent_review=reconciliation.get('status')=='reconciled' and bool(reconciliation.get('reviewedBy')) and bool(reconciliation.get('notes'))
    legacy_review=review.get('status')=='reviewed' and bool(review.get('reviewedBy')) and bool(review.get('notes'))
    source_current = audit.get('sourceHashes') == current_sources
    source_reviewed=(agent_review or legacy_review) and source_current
    runtime_matches=runtime.get('schemaVersion')=='2.0.0' and runtime.get('viewport') == {'width': 390, 'height': 844} and runtime.get('manifestContentSha256')==discovery_fingerprint(manifest)
    observations=runtime.get('observations',[]) if runtime_matches else []
    captures=runtime.get('captures',[]) if runtime_matches else []
    blockers=[]
    if runtime_matches:
        from ..browser.evidence import verified_capture
        from functools import lru_cache
        root = Path(runtime_path).parent.resolve()

        @lru_cache(maxsize=None)
        def valid_image(path, sha):
            return verified_capture(root, dict(screenshotPath=path, screenshotSha256=sha))

        def valid(item):
            return valid_image(item.get('screenshotPath', ''), item.get('screenshotSha256'))

        valid_captures = [c for c in captures if valid(c)]
        valid_observations = [o for o in observations if valid(o['before']) and valid(o['after'])]
        if len(valid_captures) != len(captures) or len(valid_observations) != len(observations):
            blockers.append('Original UI screenshot evidence is missing or changed; repeat affected browser observations')
        captures, observations = valid_captures, valid_observations
    observed_actions={(o.get('sourceActionId'),o.get('themeMode')) for o in observations if o.get('passed') and o.get('assertions')}
    invoked_actions={(o.get('sourceActionId'), o.get('themeMode')) for o in observations
                     if o.get('passed') and o.get('assertions') and o.get('callbackInvoked', True)}
    guard_review=review_source_guards(manifest, audit, runtime, runtime_path, invoked_actions) if runtime_matches else dict(observations=[], actionIds=[], blockers=[])
    blockers.extend(guard_review['blockers'])
    observations.extend(guard_review['observations'])
    observed_actions.update((o['sourceActionId'], o['themeMode']) for o in guard_review['observations'])
    observed_screens={(s,c.get('themeMode')) for c in captures if not c.get('redirected') for s in c.get('screenIds',[])}
    expected_actions={(a['id'],theme) for a in actions for theme in ('light','dark')}
    expected_screens={(s['id'],theme) for s in manifest['screens'] for theme in ('light','dark')}
    complete_status=runtime.get('status')=='ok' or (runtime.get('status')=='ok-with-observed-guards' and bool(guard_review['actionIds']))
    runtime_complete=runtime_matches and complete_status and not guard_review['blockers'] and expected_actions<=observed_actions and expected_screens<=observed_screens
    if not behavior:blockers.append('Run source behavior discovery; route/screen names alone are insufficient')
    configs=source_config_hashes(source_root)
    if behavior and behavior.get('sourceConfigHashes')!=configs:
        source_current = source_reviewed = False
        blockers.append('Source configuration changed; refresh import/alias discovery')
    if not source_reviewed:blockers.append('Agent source reconciliation of functions, unresolved calls and feature mappings is pending')
    dispositions=audit.get('functionDispositions',{})
    unassigned=[f for f in behavior.get('unassignedFunctionIds',[]) if not dispositions.get(f,{}).get('reason') or dispositions.get(f,{}).get('disposition') not in {'feature','shared-utility','framework-glue','excluded'}]
    if unassigned:blockers.append(f'{len(unassigned)} unassigned functions need a reviewed disposition with a reason')
    if not runtime_complete:blockers.append('Capture original app routes AND action states in light/dark; a current complete runtime report is required')
    # User-facing features group controls and their service dependencies. Raw calls and generated
    # screen/action flow associations are traceability records, not hundreds of extra features.
    features=[]
    for group in ('screens','components'):
        for item in manifest[group]:
            features.append(dict(featureId=item['id'],name=item['name'],kind=group,sourceFile=item['sourceFile'],manifestRefs=[item['id']],actions=[]))
    for group,kind in (('routes','routing'),('apiCalls','service')):
        by_file={}
        for item in manifest[group]:by_file.setdefault(item['sourceFile'],[]).append(item['id'])
        for file,refs in by_file.items():
            features.append(dict(featureId=identifier('FEATURE',file,kind),name=f'{kind}: {Path(file).stem}',kind=kind,sourceFile=file,manifestRefs=refs,actions=[]))
    for action in actions:
        parent=next((f for f in features if set(f['manifestRefs'])&set(action['manifestRefs']) and f['sourceFile']==action['sourceFile']),None)
        if parent is None:parent=next((f for f in features if f['sourceFile']==action['sourceFile']),None)
        if parent is None:
            parent=dict(featureId=identifier('FEATURE',action['sourceFile'],'source-actions'),name='Source actions: '+Path(action['sourceFile']).stem,kind='source-actions',sourceFile=action['sourceFile'],manifestRefs=action['manifestRefs'],actions=[])
            features.append(parent)
        evidence=[o for o in observations if o.get('sourceActionId')==action['id'] and o.get('passed') and o.get('assertions')]
        parent['actions'].append(dict(**action,uiReferences=[dict(theme=o['themeMode'],before=o['before']['screenshotPath'],after=o['after']['screenshotPath'],coverageKind=o.get('coverageKind','invoked-action'),callbackInvoked=o.get('callbackInvoked',True)) for o in evidence],missingUiThemes=sorted({'light','dark'}-{o['themeMode'] for o in evidence})))
    unmapped=[a['id'] for a in actions if not a['manifestRefs']]
    if unmapped:blockers.append(f'{len(unmapped)} source actions still need a manifest feature association')
    readiness = {}
    groups_by_id = {item['id']: group for group in GROUPS for item in manifest[group]}
    items = {item['id']: item for group in GROUPS for item in manifest[group]}
    for item_id, item in items.items():
        refs = feature_refs(manifest, item_id)
        route_screens = {s['id'] for s in manifest['screens'] if refs.intersection(s.get('routeIds', []))}
        for screen_id in route_screens:
            refs.update(feature_refs(manifest, screen_id))
        scoped_actions = [action for action in actions if refs.intersection(action['manifestRefs'])
                          or action['id'] == item.get('sourceActionId')]
        related = {f['id'] for f in functions.values() if refs.intersection(f['manifestRefs'])}
        related.update(f for action in scoped_actions for f in action['reachableFunctionIds'])
        missing_actions = sorted([action['id'], theme] for action in scoped_actions
                                 for theme in ('light', 'dark') if (action['id'], theme) not in observed_actions)
        required_screens = refs.intersection(s['id'] for s in manifest['screens'])
        if groups_by_id[item_id] == 'components' and not scoped_actions:
            required_screens.update(s['id'] for s in manifest['screens']
                                    if item_id in feature_refs(manifest, s['id']))
        missing_screens = sorted([screen, theme] for screen in required_screens for theme in ('light', 'dark')
                                 if (screen, theme) not in observed_screens)
        scoped_review = audit.get('featureReconciliation', {}).get(item_id, {})
        reviewed = source_reviewed or (scoped_review.get('status') == 'reconciled'
                                       and all(scoped_review.get(key) for key in ('reviewedBy', 'notes')))
        same_file_pending = any(functions[f]['sourceFile'] == item['sourceFile']
                                for f in unassigned if f in functions)
        source_ready = bool(behavior and source_current and reviewed
                            and not related.intersection(unassigned) and not same_file_pending
                            and not any(a['sourceFile'] == item['sourceFile'] and not a['manifestRefs'] for a in actions))
        visual = groups_by_id[item_id] in {'routes', 'screens', 'components', 'flows'}
        ui_ready = (runtime_matches and runtime.get('themeVerificationEnabled', True) and runtime.get('status') in {'ok', 'partial', 'ok-with-observed-guards'}
                    and not missing_actions and not missing_screens
                    and (not visual or bool(required_screens or scoped_actions)
                         or all(any(c['routeId'] == item_id and c['themeMode'] == theme
                                    and not c.get('redirected') for c in captures)
                                for theme in ('light', 'dark'))))
        readiness[item_id] = dict(ready=bool(source_ready and ui_ready), sourceReady=source_ready,
                                  missingActions=missing_actions, missingScreens=missing_screens,
                                  actionIds=sorted(a['id'] for a in scoped_actions))
    scope_ready = not blockers or any(item['ready'] for item in readiness.values())
    tasks=[
        dict(taskId='TASK_SOURCE_RECONCILIATION',title='Reconcile every function, action and unresolved call with features',kind='discovery',dependsOn=[],status='done' if source_reviewed and not unassigned and not unmapped else 'blocked',acceptanceCriteria=['Group handlers into user-facing features; a raw function or callback is not automatically a feature','Review service/library boundaries, guards, validation, side effects, errors and retry/cancel paths','Give every unassigned function a feature/shared-utility/framework-glue/excluded disposition with a reason']),
        dict(taskId='TASK_ORIGINAL_UI_OBSERVATION',title='Observe original app routes and action states',kind='discovery',dependsOn=['TASK_SOURCE_RECONCILIATION'],status='done' if runtime_complete else 'blocked',acceptanceCriteria=['Capture real 390x844 light/dark UI through the original app theme mechanism','Open menus/dialogs, exercise forms and relevant permission/disabled states, assert outcomes']),
        dict(taskId='TASK_HUMAN_PLAN_APPROVAL',title='Human reviews feature list, UI evidence, mobile gaps and tasks',kind='review',dependsOn=[],status='pending-review',acceptanceCriteria=['Explicit approval of reconciled feature scope, architecture and mobile decisions before Flutter code'])]
    for feature in features:
        refs=set(feature['manifestRefs']);file=feature['sourceFile'];feature_id=feature['featureId']
        related={f['id'] for f in functions.values() if refs&set(f['manifestRefs'])}
        if feature['kind'] in {'service','source-actions'}:related.update(f['id'] for f in functions.values() if f['sourceFile']==file)
        related.update(f for a in feature['actions'] for f in a['reachableFunctionIds'])
        feature['functionIds']=sorted(related)
        feature['uiReferences']=[dict(theme=c['themeMode'],screenshotPath=c['screenshotPath']) for c in captures if refs&set(c.get('screenIds',[])) or c['routeId'] in refs]
        feature['uiReferences'].extend(dict(theme=o['themeMode'],screenshotPath=o['after']['screenshotPath']) for o in observations if o.get('sourceActionId') in {a['id'] for a in feature['actions']})
        feature['reviewStatus']='pending-human-review'
        prefix='TASK_'+feature_id
        visual=feature['kind'] in {'screens','components','source-actions'}
        logic=dict(taskId=prefix+'_LOGIC',featureId=feature_id,title='Implement '+feature['name']+' logic',kind='logic',manifestRefs=feature['manifestRefs'],functionIds=feature['functionIds'],sourceFiles=sorted({file,*[functions[f]['sourceFile'] for f in related]}),dependsOn=['TASK_HUMAN_PLAN_APPROVAL'],status='pending-review',subtasks=[],acceptanceCriteria=['Preserve source inputs, outputs, guards, validation, permissions and side effects','Keep every listed action and failure/cancel/retry outcome functional'])
        verify=dict(taskId=prefix+'_VERIFY',featureId=feature_id,title='Verify '+feature['name'],kind='verification',dependsOn=[prefix+'_LOGIC']+([prefix+'_UI'] if visual else []),status='pending-review',subtasks=[],acceptanceCriteria=['Exercise source behavior, not only widget visibility','Attach meaningful tests and original/native flow or UI parity evidence'])
        tasks.append(logic)
        if visual:tasks.append(dict(taskId=prefix+'_UI',featureId=feature_id,title='Reproduce original '+feature['name']+' UI states',kind='ui',dependsOn=[prefix+'_LOGIC'],status='pending-review',uiReferences=feature['uiReferences'],acceptanceCriteria=['Match observed original layout, states and computed styles in light/dark','Use lock-matched shared components and tokens']))
        tasks.append(verify)
        for action in feature['actions']:
            action_id=action['id'];implement='TASK_'+action_id+'_IMPLEMENT';check='TASK_'+action_id+'_VERIFY'
            logic['subtasks'].append(dict(taskId=implement,featureId=action_id,title='Implement '+action['name'],kind='action',manifestRefs=action['manifestRefs'],sourceFile=file,sourceLine=action['sourceLine'],functionIds=action['reachableFunctionIds'],unresolvedCallIds=action['unresolvedCallIds'],dependsOn=['TASK_HUMAN_PLAN_APPROVAL'],status='pending-review',acceptanceCriteria=['Preserve handler, source guards, disabled states and reached service/API calls','Keep success, validation, failure, retry and cancellation behavior']))
            logic['dependsOn'].append(implement)
            verify['subtasks'].append(dict(taskId=check,featureId=action_id,title='Verify '+action['name']+' outcome',kind='verification',dependsOn=[implement]+([prefix+'_UI'] if visual else []),status='pending-review',missingUiThemes=action['missingUiThemes'],acceptanceCriteria=[('Preserve the verified source guard and tested same-handler alternative; do not add an unavailable control' if action_id in guard_review['actionIds'] else 'Invoke the action and assert its expected outcome; button presence alone fails'),'Compare trigger/result states and record relevant response status or state change']))
            verify['dependsOn'].append(check)
    return dict(sourceActionCoverage=dict(invokedActionIds=sorted({a for a,t in invoked_actions}),guardedActionIds=guard_review['actionIds'],guardBlockers=guard_review['blockers']),manifestContentSha256=discovery_fingerprint(manifest),sourceConfigHashes=configs,sourceHashes=current_sources,sourceOfLogic='source-code',sourceOfUi='running-original-app',readyForApproval=scope_ready,complete=not blockers,featureReadiness=readiness,blockers=blockers,unassignedFunctionIds=unassigned,unmappedActionIds=unmapped,
                functionReview=[dict(functionId=f['id'],sourceRole=f.get('sourceRole'),name=f['qualifiedName'],sourceFile=f['sourceFile'],sourceLine=f['sourceLine'],manifestRefs=f['manifestRefs'],disposition=dispositions.get(f['id'])) for f in functions.values()],features=features,tasks=tasks)


def render_discovery_plan(plan, discovery, gaps):
    """Human scope checklist; implementation evidence stays in agent JSON files."""
    import re
    def readable(name):
        return re.sub(r'(?<=[a-z0-9])(?=[A-Z])',' ',name).replace('_',' ').strip()
    groups=plan.get('humanFeatures')
    if not groups:
        groups=[dict(title=readable(f['name']),functions=list(dict.fromkeys(readable(a.get('labelExpression') or a['event']) for a in f['actions']))) for f in discovery['features'] if f['kind'] in {'screens','components'}]
    lines=['# Migration plan — '+plan['app']['name'],'',
           '**Draft scope checklist — source/UI reconciliation is still pending.**' if not discovery['readyForApproval'] else '**Ready for human scope review. Individual features still require their own discovery evidence.**',
           'Human review: check the features/functions below and flag anything missing.','']
    for group in groups:
        lines.append('- [ ] **'+group['title']+'**'+(': '+ '; '.join(group.get('functions',[])) if group.get('functions') else ''))
    lines+=['','Implementation details for the agent: [plan](migration-plan.json), [tasks](migration-tasks.json), [source evidence](feature-review.json).',
            'Approval covers this scope only; unresolved discovery and mobile decisions remain in the agent plan.']
    return '\n'.join(lines)+'\n'
