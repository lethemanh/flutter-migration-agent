import argparse
import json
from pathlib import Path
import sys
from .agent import harness_check, start_agent
from .browser import discover_runtime
from .config import checkpoint, init_workspace, read_config, record_feature
from .core import changes_since_checkpoint, check_feature_gate, complete_migration, validate_manifest, verify_parity, write_json
from .exporters import generate, plan_migration
from .parsers import discover_static, lint_flutter_tokens, validate_tokens


def parser():
    root=argparse.ArgumentParser(prog='twake-migrate',description='Python Twake React-to-Flutter migration toolkit')
    commands=root.add_subparsers(dest='command',required=True)
    p=commands.add_parser('start',help='Start the migration agent for separate web/mobile projects')
    p.add_argument('web',nargs='?');p.add_argument('mobile',nargs='?');p.add_argument('--config')
    p.add_argument('--batch', action='store_true', help='Run one non-interactive phase with a one-hour limit')
    p=commands.add_parser('discover-changes',help='List changes since the completed source migration')
    p.add_argument('--config',required=True)
    p=commands.add_parser('complete-migration',help='Verify migration and record completed source commit')
    p.add_argument('--config',required=True);p.add_argument('--artifacts')
    p=commands.add_parser('init-app',help='Create an app migration workspace outside Flutter')
    p.add_argument('--web',required=True);p.add_argument('--mobile',required=True);p.add_argument('--out',required=True)
    p=commands.add_parser('checkpoint',help='Persist stop reason and next action for resuming')
    p.add_argument('--config',required=True);p.add_argument('--state',required=True,choices=['ready','running','needs-user','blocked','stopped']);p.add_argument('--reason',required=True);p.add_argument('--next-action',required=True);p.add_argument('--feature')
    p=commands.add_parser('record-feature',help='Record hashed implementation and verification evidence')
    p.add_argument('--manifest',required=True);p.add_argument('--flutter',required=True);p.add_argument('--feature',required=True);p.add_argument('--implementation',action='append',required=True);p.add_argument('--verification',action='append',required=True);p.add_argument('--out',required=True)
    p=commands.add_parser('check-app',help='Write current app harness report from migration config')
    p.add_argument('--config',required=True);p.add_argument('--development',action='store_true');p.add_argument('--artifacts')
    p=commands.add_parser('discover-static',help='AST inventory of a React/TypeScript app')
    p.add_argument('--web');p.add_argument('--config');p.add_argument('--out');p.add_argument('--approve',action='store_true')
    p=commands.add_parser('discover-runtime',help='Capture 390×844 light/dark browser baselines')
    p.add_argument('--url',required=True);p.add_argument('--manifest',required=True);p.add_argument('--gaps');p.add_argument('--out');p.add_argument('--storage-state');p.add_argument('--browser-executable');p.add_argument('--capture-plan');p.add_argument('--headed',action='store_true');p.add_argument('--interactive-login',action='store_true');p.add_argument('--login-timeout',type=int,default=300);p.add_argument('--allow-mutations',action='store_true',help='Run explicitly authorized data-changing discovery journeys');p.add_argument('--crawl-depth',type=int,default=0,help='Legacy option accepted for compatibility. Discovered links are report-only.')
    p.add_argument('--reuse-evidence',action='store_true',help='Reuse passing captures and unchanged journeys with current fingerprints')
    p=commands.add_parser('plan-migration',help='Generate the mandatory pre-migration report and waves')
    p.add_argument('--manifest',required=True);p.add_argument('--gaps',required=True);p.add_argument('--widget-map');p.add_argument('--out');p.add_argument('--approve',action='store_true');p.add_argument('--runtime-report')
    p=commands.add_parser('generate-design-system',help='Generate Flutter UI from lock-matched web dependencies')
    p.add_argument('--web');p.add_argument('--config');p.add_argument('--dependency-root');p.add_argument('--out');p.add_argument('--twake-ui',help=argparse.SUPPRESS)
    p=commands.add_parser('validate-design-tokens',help='Check extracted source-to-Dart values and fingerprints')
    p.add_argument('--ui',required=True)
    p=commands.add_parser('lint-flutter-tokens',help='Scan Flutter Dart files for hardcoded design token violations')
    p.add_argument('--flutter',required=True)
    p=commands.add_parser('validate-manifest',help='Validate manifest schema and unique IDs')
    p.add_argument('--manifest',required=True)
    p=commands.add_parser('check-feature-gate',help='Check approval, widget mapping and mobile gap gates')
    p.add_argument('--manifest',required=True);p.add_argument('--gaps',required=True);p.add_argument('--widget-map',required=True);p.add_argument('--plan');p.add_argument('--feature',required=True)
    p=commands.add_parser('harness-check',help='Run migration guardrails including token and visual parity gates')
    p.add_argument('--manifest',required=True);p.add_argument('--gaps',required=True);p.add_argument('--widget-map',required=True);p.add_argument('--plan');p.add_argument('--flutter',required=True);p.add_argument('--allow-draft',action='store_true');p.add_argument('--strict-coverage',action='store_true');p.add_argument('--skip-parity',action='store_true');p.add_argument('--require-parity',action='store_true',help=argparse.SUPPRESS);p.add_argument('--parity-report');p.add_argument('--evidence')
    p=commands.add_parser('verify-parity',help='Compare decoded light/dark pixels and flow results')
    p.add_argument('--manifest',required=True);p.add_argument('--baselines',required=True);p.add_argument('--captures',required=True);p.add_argument('--flows');p.add_argument('--out',default='./parity-report.json');p.add_argument('--threshold',type=float,default=.08);p.add_argument('--flutter')
    return root


def run(args):
    c=args.command
    if c in ('discover-static', 'generate-design-system'):
        config = None
        if args.config:
            config = read_config(args.config)
            args.web = args.web or config['webRoot']
        if not args.web: raise ValueError('Provide --web or --config')
        if c == 'discover-static':
            args.out = args.out or (str(Path(config['workspaceRoot'])/'artifacts') if config else './discovery-out')
        else:
            args.out = args.out or (str(Path(config['mobileRoot'])/'packages/twake_flutter_ui') if config else './twake_flutter_ui')
            args.dependency_root = args.dependency_root or (config.get('dependencyRoot') if config else None)
    if c=='discover-changes':
        result=changes_since_checkpoint(args.config)
    elif c=='complete-migration':
        result=complete_migration(args.config,args.artifacts)
    elif c=='check-app':
        config=read_config(args.config);artifacts=Path(args.artifacts).resolve() if args.artifacts else Path(config['workspaceRoot'])/'artifacts';mobile=Path(config['mobileRoot'])
        result=harness_check(artifacts/'feature-manifest.json',artifacts/'gap-report.json',mobile/'packages/twake_flutter_ui/widget-map.json',mobile,artifacts/'migration-plan.json',require_parity=not args.development,parity_report_path=artifacts/'parity-report.json',evidence_path=artifacts/'feature-evidence.json')
        write_json(artifacts/('harness-development.json' if args.development else 'harness-final.json'),result)
    elif c=='init-app':
        result={'status':'ok','configPath':str(init_workspace(args.web,args.mobile,args.out))}
    elif c=='checkpoint':
        result=checkpoint(args.config,args.state,args.reason,args.next_action,args.feature)
    elif c=='record-feature':
        result=record_feature(args.manifest,args.flutter,args.feature,args.implementation,args.verification,args.out)
    elif c=='discover-static':
        result=discover_static(args.web,args.out,args.approve,config.get('sourceAliases') if config else None)
        manifest=result.pop('manifest');gaps=result.pop('gapReport');spec_counts=result.pop('specCounts',{})
        result.update(status='ok',stats={**{g:len(manifest[g]) for g in ('routes','screens','components','flows','apiCalls','twakeLibraries')},'locales':manifest['i18n']['locales'],'i18nKeys':manifest['i18n']['totalKeys'],'gaps':len(gaps['gaps']),'unresolvedGaps':sum(g['status']=='unresolved-ask-user' for g in gaps['gaps']),'functions':len(manifest.get('behavior',{}).get('functions',[])),'actions':len(manifest.get('behavior',{}).get('actions',[])),'unresolvedSourceReferences':len(manifest.get('behavior',{}).get('reviewRequired',[])),'unassignedFunctions':len(manifest.get('behavior',{}).get('unassignedFunctionIds',[])),**spec_counts})
    elif c=='discover-runtime': result={'status':'ok',**discover_runtime(args.url,args.manifest,args.out or Path(args.manifest).parent,args.gaps,args.storage_state,args.browser_executable,args.capture_plan,args.headed,args.interactive_login,args.login_timeout,args.allow_mutations,crawl_depth=args.crawl_depth,reuse_evidence=args.reuse_evidence)}
    elif c=='plan-migration':
        result=plan_migration(args.manifest,args.gaps,args.out or Path(args.manifest).parent,args.widget_map,args.approve,args.runtime_report)
        plan=result.pop('plan');result.update(status='ok',approvalStatus=plan['approval']['status'],discoveredFeaturesSummary=plan['discoveredFeaturesSummary']['counts'],twakeLibrariesCount=len(plan['twakeLibrariesReport']),wavesCount=len(plan['waves']),featureCount=len(plan['featureBreakdown']),taskCount=len(plan['tasks']),discoveryReadyForApproval=plan['discoveryReview']['readyForApproval'],discoveryComplete=plan['discoveryReview']['complete'])
    elif c=='generate-design-system': result={'status':'ok',**generate(args.web,args.out,args.dependency_root)}
    elif c=='validate-design-tokens': result=validate_tokens(args.ui)
    elif c=='lint-flutter-tokens': result=lint_flutter_tokens(args.flutter)
    elif c=='validate-manifest': result=validate_manifest(args.manifest)
    elif c=='check-feature-gate': result=check_feature_gate(args.manifest,args.gaps,args.widget_map,args.feature,args.plan)
    elif c=='harness-check':
        if args.skip_parity and args.require_parity: raise ValueError('--skip-parity conflicts with --require-parity')
        result=harness_check(args.manifest,args.gaps,args.widget_map,args.flutter,args.plan,args.allow_draft,True if args.strict_coverage else None,not args.skip_parity,args.parity_report,args.evidence)
    elif c=='verify-parity': result=verify_parity(args.manifest,args.baselines,args.captures,args.flows,args.threshold,args.out,args.flutter)
    else: raise ValueError('Unknown command')
    code=0
    for key in ('valid','passed','allPassed'):
        if key in result and not result[key]: code=1
    if result.get('allowed') is False: code=2
    return result,code


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command == 'start':
            if args.config:
                config=read_config(args.config)
                if args.web or args.mobile: raise ValueError('Use either --config or positional web/mobile paths')
                args.web,args.mobile=config['webRoot'],config['mobileRoot']
            if not args.web or not args.mobile: raise ValueError('Provide web and mobile paths or --config')
            return start_agent(args.web,args.mobile,args.config,batch=args.batch) or 0
        result,code=run(args)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return code
    except Exception as error:
        print(json.dumps({'status':'error','message':str(error)},indent=2),file=sys.stderr)
        return 1

if __name__=='__main__': sys.exit(main())
