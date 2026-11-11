from pathlib import Path
from .common import load, GROUPS, digest, discovery_fingerprint


def validate_manifest(manifest_path):
    from jsonschema import Draft202012Validator
    errors=[]
    try:
        manifest=load(manifest_path)
        schema=load(Path(__file__).resolve().parent.parent/'schemas/feature-manifest.schema.json')
        errors.extend(f"{'.'.join(map(str,e.absolute_path))}: {e.message}" for e in Draft202012Validator(schema).iter_errors(manifest))
        seen=set()
        for group,prefix in zip(GROUPS,('ROUTE_','SCREEN_','COMP_','FLOW_','API_')):
            for item in manifest.get(group,[]):
                item_id=item.get('id','')
                if not item_id.startswith(prefix): errors.append(f'Invalid ID: {item_id}; expected {prefix}')
                elif item_id in seen: errors.append(f'Duplicate manifest ID detected: {item_id}')
                seen.add(item_id)
        behavior=manifest.get('behavior')
        if behavior is not None:
            tables={key:{item.get('id') for item in behavior.get(key,[])} for key in ('functions','actions','calls')}
            for key,ids in tables.items():
                if len(ids)!=len(behavior.get(key,[])):errors.append(f'Duplicate source behavior ID: {key}')
            def references(values,known,label):
                for value in values:
                    if value is not None and value not in known:errors.append(f'Broken source behavior reference: {label}: {value}')
            for function in behavior.get('functions',[]):
                references([function.get('parentFunctionId')],tables['functions'],'parent function')
                references(function.get('callIds',[]),tables['calls'],'function calls')
                references(function.get('manifestRefs',[]),seen,'function feature')
            for call in behavior.get('calls',[]):
                references([call.get('callerFunctionId'),call.get('targetFunctionId')],tables['functions'],'call edge')
            for action in behavior.get('actions',[]):
                references([action.get('ownerFunctionId'),*action.get('handlerFunctionIds',[]),*action.get('reachableFunctionIds',[])],tables['functions'],'action function')
                references(action.get('callIds',[]),tables['calls'],'action calls')
                references(action.get('manifestRefs',[]),seen,'action feature')
        stats={g:len(manifest.get(g,[])) for g in GROUPS}
        stats.update(totalIds=len(seen),i18nKeys=manifest.get('i18n',{}).get('totalKeys',0),approvalStatus=manifest.get('approval',{}).get('status'))
        return dict(valid=not errors,errors=errors,stats=stats)
    except (OSError,ValueError,TypeError) as error: return dict(valid=False,errors=[str(error)])


def feature_refs(manifest, feature_id):
    items = {i['id']: i for group in GROUPS for i in manifest[group]}
    names = {i.get('name'): i['id'] for i in items.values()}
    refs, pending = set(), [feature_id]
    while pending:
        item_id = pending.pop()
        if item_id in refs or item_id not in items: continue
        refs.add(item_id)
        pending.extend(items[item_id].get('childComponentIds',[]))
        pending.extend(items[item_id].get('apiCallIds', []))
        pending.extend(names[name] for name in items[item_id].get('childComponents', []) if name in names)
    return refs


def check_feature_gate(manifest_path,gap_report_path,widget_map_path,feature_id,plan_path=None):
    manifest,gaps,mappings=load(manifest_path),load(gap_report_path)['gaps'],load(widget_map_path)['mappings']
    items={item['id']:item for group in GROUPS for item in manifest[group]}
    if feature_id not in items: return dict(allowed=False,reason='UNKNOWN_MANIFEST_ID',message=f'Unknown manifest feature: {feature_id}')
    target=items[feature_id]
    blockers=[]
    if manifest['approval']['status']!='approved': blockers.append(dict(type='BLOCKED_UNAPPROVED_MANIFEST',message='Manifest requires user approval'))
    plan_path = plan_path or Path(manifest_path).with_name('migration-plan.json')
    if not Path(plan_path).is_file():
        blockers.append(dict(type='BLOCKED_MISSING_MIGRATION_PLAN', message='Generate and approve the migration plan'))
    else:
        plan = load(plan_path)
        review = plan.get('discoveryReview', {})
        if plan['approval']['status'] != 'approved':
            blockers.append(dict(type='BLOCKED_UNAPPROVED_MIGRATION_PLAN', message='Migration plan requires user approval'))
        elif plan.get('approvedScope'):
            current = current_plan_discovery(manifest, manifest_path, gap_report_path, plan)
            readiness = current.get('featureReadiness', {}).get(feature_id, {})
            if not readiness.get('ready'):
                blockers.append(dict(type='BLOCKED_INCOMPLETE_DISCOVERY',
                                     message='This feature needs current source review and original UI evidence',
                                     readiness=readiness, discoveryBlockers=current.get('blockers', [])))
        elif review.get('readyForApproval') is False:
            blockers.append(dict(type='BLOCKED_INCOMPLETE_DISCOVERY', message='Source behavior and original UI observation must be reconciled before feature migration'))
        elif review:
            from ..parsers.discovery import source_files
            from ..parsers.source_resolution import source_config_hashes
            root = Path(manifest['app']['sourceRoot']).resolve()
            actual = {p.relative_to(root).as_posix(): digest(p) for p in source_files(root)}
            if review.get('sourceConfigHashes') != source_config_hashes(root) or review.get('manifestContentSha256') != discovery_fingerprint(manifest) or review.get('sourceHashes') != actual:
                blockers.append(dict(type='BLOCKED_STALE_DISCOVERY', message='Source or feature scope changed after discovery review; reconcile the plan'))
    refs = feature_refs(manifest, feature_id)
    for item_id in refs:
        for name in items[item_id].get('twakeMuiComponents', []):
            if mappings.get(name,{}).get('status','unimplemented')=='unimplemented': blockers.append(dict(type='BLOCKED_MISSING_COMPONENT',component=name,manifestRef=item_id,message=f'No implemented Twake widget: {name}'))
    for gap in gaps:
        if gap['manifestRef'] in refs and gap['status']=='unresolved-ask-user': blockers.append(dict(type='BLOCKED_UNRESOLVED_MOBILE_GAP',gapId=gap['id'],manifestRef=gap['manifestRef'],category=gap['category'],description=gap['description'],message='Ask the user to resolve this mobile gap'))
    return dict(allowed=not blockers,featureId=feature_id,sourceFile=target['sourceFile'],hasWebMobileAdaptation=target.get('hasWebMobileAdaptation',target.get('usesMobileBreakpoint',False)),mobileAdaptationNotes=target.get('mobileAdaptationNotes',[]),blockers=blockers)


def current_plan_discovery(manifest, manifest_path, gap_report_path, plan):
    """Revalidate incremental discovery against the approved scope and on-disk evidence."""
    from .discovery_review import build_discovery_review

    approved = plan['approvedScope']
    if approved != dict(manifest=discovery_fingerprint(manifest), gaps=digest(gap_report_path)):
        return {'blockers': ['Approved manifest scope or mobile gap decisions changed']}
    runtime_path = Path(plan['runtimeReportPath'])
    audit_path = Path(manifest_path).with_name('discovery-audit.json')
    review = build_discovery_review(
        manifest, manifest_path, load(audit_path) if audit_path.is_file() else {},
        load(runtime_path) if runtime_path.is_file() else {}, runtime_path,
    )
    if any(review[key] != plan['discoveryReview'][key] for key in ('sourceHashes', 'sourceConfigHashes')):
        return {'blockers': ['Source changed after scope approval']}
    return review
