"""Record a source revision only after the complete migration passes verification."""
import re
import subprocess
from pathlib import Path
from .common import load, write_json, digest, now


def git(web, *args):
    result=subprocess.run(['git','-C',str(web),*args],capture_output=True,text=True)
    if result.returncode:raise ValueError('Source Git revision is unavailable; restore repository history before checkpointing')
    return result.stdout.strip()


def changes_since_checkpoint(config_path):
    from ..config.workspace import read_config
    config=read_config(config_path);web=Path(config['webRoot']);base=config.get('lastMigratedCommit')
    if not base:return dict(mode='full',reason='No completed migration commit recorded',files=[])
    if not re.fullmatch(r'[0-9a-f]{40,64}',base):raise ValueError('Invalid lastMigratedCommit')
    git(web,'cat-file','-e',base+'^{commit}')
    files=git(web,'diff','--name-only',base,'--','.').splitlines()
    files+=git(web,'ls-files','--others','--exclude-standard').splitlines()
    return dict(mode='incremental',fromCommit=base,toCommit=git(web,'rev-parse','HEAD'),files=sorted(set(files)),reason='Inspect changed files and their importers, services and UI dependencies; retain unchanged approved inventory')


def complete_migration(config_path, artifacts=None):
    from ..agent.harness import harness_check
    from ..config.workspace import read_config
    config=read_config(config_path);web=Path(config['webRoot']);root=Path(config['workspaceRoot'])
    folder=Path(artifacts).resolve() if artifacts else root/'artifacts'
    manifest=folder/'feature-manifest.json';head=git(web,'rev-parse','HEAD')
    if git(web,'status','--porcelain','--untracked-files=all'):raise ValueError('Source has uncommitted changes; no migration commit was recorded')
    if load(manifest).get('sourceCommit')!=head:raise ValueError('Discovery must identify the current sourceCommit before completion')
    result=harness_check(manifest,folder/'gap-report.json',Path(config['mobileRoot'])/'packages/twake_flutter_ui/widget-map.json',config['mobileRoot'],folder/'migration-plan.json',strict_coverage=True,require_parity=True,parity_report_path=folder/'parity-report.json',evidence_path=folder/'feature-evidence.json')
    write_json(folder/'harness-final.json',result)
    if not result.get('verification',{}).get('completionVerified'):return dict(passed=False,completed=False,errors=result['errors'])
    if git(web,'rev-parse','HEAD')!=head or git(web,'status','--porcelain','--untracked-files=all'):raise ValueError('Source changed during verification; checkpoint unchanged')
    saved=load(config_path);saved['lastMigratedCommit']=head
    saved['migrationBaseline']=dict(manifest=str(manifest),manifestSha256=digest(manifest),completedAt=now())
    write_json(config_path,saved)
    return dict(passed=True,completed=True,lastMigratedCommit=head)
