import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image
from twake_migrate.core.common import digest, discovery_fingerprint

STAGE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result
    spec.loader.exec_module(result);return result
if (STAGE/'source_guards.py').is_file():
    guards=module('twake_migrate.core.source_guards',STAGE/'source_guards.py')
    review=module('twake_migrate.core.discovery_review_preview',STAGE/'discovery_review.py')
else:
    from twake_migrate.core import source_guards as guards
    from twake_migrate.core import discovery_review as review

@pytest.fixture
def evidence(tmp_path):
    web=tmp_path/'web';web.mkdir()
    source=web/'A.tsx';source.write_text('if (!isMobile) hidden(); else visible(); action={customOk}')
    library=web/'node_modules'/'mui'/'Alert.js';library.parent.mkdir(parents=True)
    library.write_text('action == null && onClose ? defaultClose() : customAction')
    out=tmp_path/'evidence';out.mkdir()
    captures=[];observations=[];guard_observations=[]
    for theme,color in [('light','white'),('dark','black')]:
        path=out/(theme+'.png');Image.new('RGB',(390,844),color).save(path)
        cap=dict(screenshotPath=path.name,screenshotSha256=digest(path))
        captures.append(dict(cap,routeId='ROUTE_A',screenIds=['SCREEN_A'],themeMode=theme))
        observations.append(dict(sourceActionId='VISIBLE',themeMode=theme,passed=True,assertions=[dict(selector='#visible',state='visible')],before=cap,after=cap))
        guard_observations.append(dict(kind='observed-source-guard',sourceActionId='HIDDEN',themeMode=theme,passed=True,callbackInvoked=False,assertions=[dict(selector='#hidden',state='hidden')],before=cap,after=cap))
    def action(id):return dict(id=id,name=id,event='onClick',sourceFile='A.tsx',sourceLine=1,manifestRefs=['SCREEN_A'],handlerFunctionIds=['HANDLER'],reachableFunctionIds=[],unresolvedCallIds=[])
    manifest=dict(app=dict(name='example',sourceRoot=str(web)),behavior=dict(actions=[action('HIDDEN'),action('VISIBLE')],functions=[],unassignedFunctionIds=[],sourceConfigHashes={}),screens=[dict(id='SCREEN_A',name='A',sourceFile='A.tsx')],components=[],routes=[],apiCalls=[],flows=[])
    disposition=dict(status='reviewed',reviewedBy='agent',reason='Existing source mobile alternative shares handler',kind='mobile-alternative',sourceEvidence=dict(path='A.tsx',sha256=digest(source)),sourceGuardExpression='!isMobile',alternativeSourceActionIds=['VISIBLE'])
    audit=dict(sourceHashes={'A.tsx':digest(source)},sourceReconciliation=dict(status='reconciled',reviewedBy='agent',notes='reviewed source'),actionGuardDispositions={'HIDDEN':disposition})
    runtime=dict(schemaVersion='2.0.0',manifestContentSha256=discovery_fingerprint(manifest),status='ok-with-observed-guards',viewport=dict(width=390,height=844),captures=captures,observations=observations,guardObservations=guard_observations)
    invoked={('VISIBLE',theme) for theme in ('light','dark')}
    return manifest,audit,runtime,out/'runtime.json',invoked

def run(data):return guards.review_source_guards(*data)

def test_mobile_guard_keeps_explicit_non_invocation(evidence):
    result=run(evidence)
    assert not result['blockers'] and result['actionIds']==['HIDDEN']
    assert all(o['callbackInvoked'] is False for o in result['observations'])

def test_library_suppression_requires_current_library_and_tested_handler(evidence):
    manifest,audit,runtime,path,invoked=evidence
    item=audit['actionGuardDispositions']['HIDDEN'];item.update(kind='library-suppressed-trigger',sourceGuardExpression='action={customOk}')
    library=Path(manifest['app']['sourceRoot'])/'node_modules/mui/Alert.js'
    item['libraryEvidence']=dict(path='mui/Alert.js',sha256=digest(library),guardExpression='action == null && onClose')
    assert not run(evidence)['blockers']
    library.write_text('new default-close behavior')
    assert 'library fingerprint' in run(evidence)['blockers'][0]

@pytest.mark.parametrize('problem',['missing-theme','failed-assertion','empty-assertion','visible-assertion','invocation-claim','unknown-action','changed-source','source-escape','missing-alternative','different-handler','untested-alternative','guard-cycle','invalid-png','wrong-size','image-drift','library-escape','wrong-viewport'])
def test_guard_evidence_fails_closed(evidence,problem):
    m,a,r,p,i=evidence;d=a['actionGuardDispositions']['HIDDEN'];o=r['guardObservations'][0]
    if problem=='missing-theme':r['guardObservations'].pop()
    elif problem=='failed-assertion':o['passed']=False
    elif problem=='empty-assertion':o['assertions']=[]
    elif problem=='visible-assertion':o['assertions'][0]['state']='visible'
    elif problem=='invocation-claim':o['callbackInvoked']=True
    elif problem=='unknown-action':o['sourceActionId']='UNKNOWN'
    elif problem=='changed-source':(Path(m['app']['sourceRoot'])/'A.tsx').write_text('changed')
    elif problem=='source-escape':d['sourceEvidence']['path']='../outside.tsx'
    elif problem=='missing-alternative':d['alternativeSourceActionIds']=[]
    elif problem=='different-handler':m['behavior']['actions'][1]['handlerFunctionIds']=['OTHER']
    elif problem=='untested-alternative':i.remove(('VISIBLE','dark'))
    elif problem=='guard-cycle':d['alternativeSourceActionIds']=['HIDDEN']
    elif problem in ('invalid-png','wrong-size','image-drift'):
        image=p.parent/o['before']['screenshotPath']
        if problem=='invalid-png':image.write_bytes(b'not a png')
        else:Image.new('RGB',(12,12),'red').save(image)
        if problem!='image-drift':o['before']['screenshotSha256']=digest(image)
    elif problem=='library-escape':
        d.update(kind='library-suppressed-trigger',libraryEvidence=dict(path='../../A.tsx',sha256=d['sourceEvidence']['sha256']))
    elif problem=='wrong-viewport':r['viewport']['width']=400
    assert run(evidence)['blockers']
    assert not run(evidence)['actionIds']

def test_plan_reports_invoked_and_guarded_coverage_separately(evidence,monkeypatch):
    m,a,r,p,i=evidence
    import twake_migrate.parsers.discovery as discovery
    import twake_migrate.parsers.source_resolution as resolution
    monkeypatch.setattr(discovery,'source_files',lambda root:[root/'A.tsx'])
    monkeypatch.setattr(resolution,'source_config_hashes',lambda root:{})
    result=review.build_discovery_review(m,p.parent/'manifest.json',a,r,p)
    assert result['readyForApproval']
    assert result['sourceActionCoverage']['invokedActionIds']==['VISIBLE']
    assert result['sourceActionCoverage']['guardedActionIds']==['HIDDEN']
    hidden=next(x for f in result['features'] for x in f['actions'] if x['id']=='HIDDEN')
    assert not hidden['missingUiThemes']
    assert all(x['callbackInvoked'] is False for x in hidden['uiReferences'])
    # A missing executable action remains blocked even with a valid guard.
    r['observations']=[]
    assert not review.build_discovery_review(m,p.parent/'manifest.json',a,r,p)['readyForApproval']

def test_no_guard_metadata_preserves_existing_gate(evidence,monkeypatch):
    m,a,r,p,i=evidence
    a.pop('actionGuardDispositions');r.pop('guardObservations')
    assert run(evidence)==dict(observations=[],actionIds=[],blockers=[])


def test_partial_discovery_unblocks_only_ready_features(evidence, monkeypatch):
    manifest, audit, runtime, path, _ = evidence
    import twake_migrate.parsers.discovery as discovery
    import twake_migrate.parsers.source_resolution as resolution
    monkeypatch.setattr(discovery, 'source_files', lambda root: [root / 'A.tsx'])
    monkeypatch.setattr(resolution, 'source_config_hashes', lambda root: {})
    manifest['screens'].append(dict(id='SCREEN_B', name='B', sourceFile='B.tsx'))
    runtime.update(status='partial', manifestContentSha256=discovery_fingerprint(manifest))

    result = review.build_discovery_review(manifest, path.parent / 'manifest.json', audit, runtime, path)
    assert result['readyForApproval']
    assert not result['complete']
    assert result['featureReadiness']['SCREEN_A']['ready']
    assert not result['featureReadiness']['SCREEN_B']['ready']

    (path.parent / 'light.png').unlink()
    result = review.build_discovery_review(manifest, path.parent / 'manifest.json', audit, runtime, path)
    assert not result['featureReadiness']['SCREEN_A']['ready']


def test_runtime_reuses_only_unchanged_complete_journey_themes(evidence):
    from twake_migrate.browser.evidence import fingerprint, reuse_runtime

    _, _, runtime, path, _ = evidence
    journey = dict(id='open', steps=[dict(action='click', selector='#open')])
    runtime.update(status='partial', evidenceKey='current', journeyKeys={'open': fingerprint(journey)})
    for observation in runtime['observations']:
        observation.update(journeyId='open', step=0)
    path.write_text(json.dumps(runtime))

    _, observations, _, reused = reuse_runtime(path, 'current', [journey])
    assert len(observations) == 2
    assert reused == {('open', 'light'), ('open', 'dark')}
    (path.parent / 'light.png').unlink()
    _, observations, _, reused = reuse_runtime(path, 'current', [journey])
    assert len(observations) == 1
    assert reused == {('open', 'dark')}
    assert not reuse_runtime(path, 'changed', [journey])[1]
    assert not reuse_runtime(path, 'current', [dict(journey, steps=[{'action': 'fill'}])])[1]
