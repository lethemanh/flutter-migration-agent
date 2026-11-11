"""App-owned migration context, separate from the Flutter source tree."""
from pathlib import Path
import re
from ..core.common import load, write_json, now, digest, GROUPS


def read_config(path):
    path = Path(path).expanduser().resolve()
    config = load(path)
    if config.get('schemaVersion') != '1.0.0':
        raise ValueError('Unsupported migration config schemaVersion')
    def resolve(value):
        return (path.parent / Path(value).expanduser()).resolve()
    for key in ('webRoot', 'mobileRoot'):
        if not isinstance(config.get(key), str):
            raise ValueError(f'Migration config requires {key}')
        config[key] = str(resolve(config[key]))
    if config.get('dependencyRoot'):
        config['dependencyRoot'] = str(resolve(config['dependencyRoot']))
    libraries = config.get('librarySources', {})
    if not isinstance(libraries, dict):
        raise ValueError('librarySources must map package names to source directories')
    config['librarySources'] = {name: str(resolve(value)) for name, value in libraries.items()}
    for name, directory in config['librarySources'].items():
        if not Path(directory).is_dir():
            raise ValueError(f'Library source does not exist: {name}: {directory}')
    aliases=config.get('sourceAliases',{})
    if not isinstance(aliases,dict):raise ValueError('sourceAliases must map import prefixes to implementation directories')
    config['sourceAliases']={name:str(resolve(value)) for name,value in aliases.items()}
    for name,directory in config['sourceAliases'].items():
        if not Path(directory).is_dir():raise ValueError(f'Source alias directory does not exist: {name}: {directory}')
    config['workspaceRoot'] = str(path.parent)
    config['configPath'] = str(path)
    mobile = Path(config['mobileRoot'])
    if path.parent == mobile or path.parent.is_relative_to(mobile):
        raise ValueError('Migration workspace must be outside the mobile project')
    return config


def init_workspace(web, mobile, root):
    root = Path(root).expanduser().resolve()
    path = root / 'migration.json'
    if path.exists():
        config = read_config(path)
        if config['webRoot'] != str(Path(web).resolve()) or config['mobileRoot'] != str(Path(mobile).resolve()):
            raise ValueError('Existing migration config belongs to different web/mobile projects')
        return path
    mobile = Path(mobile).expanduser().resolve()
    if root == mobile or root.is_relative_to(mobile):
        raise ValueError('Migration workspace must be outside the mobile project')
    write_json(path, dict(schemaVersion='1.0.0', webRoot=str(Path(web).resolve()), mobileRoot=str(mobile), dependencyRoot=None, librarySources={}, lastMigratedCommit=None))
    if not (root / 'SKILL.md').exists():
        (root / 'SKILL.md').write_text('''---
name: app-migration
description: App-specific migration decisions and implementation references.
---

# App migration context

Read migration.json and artifacts/ before working. Record approved decisions here.
Library source directories are references; design generation must still use lock-matched dependencies.
Keep reports, plans, screenshots, evidence and checkpoints in this workspace.
Keep Flutter code and its packaged dependencies in the mobile project.
Do not infer completion from traceability headers or a passing development check.

## Authentication and session flow

Discover this app's authentication mechanism from source before implementing it. Record login entry points, protocol/session or cookie handling, applicable client/issuer/redirect configuration, native implementation choice, required backend bootstrap, logout, lifecycle, cancellation and failure recovery. Reference source files and app-local evidence; do not copy another app's flow or environment registration. Record secrets only through appropriate runtime configuration, never in this skill. If the app has no authentication, record the source evidence for that finding. Keep this section marked unresolved until source tracing is complete.

''')
    checkpoint(path, 'ready', 'Workspace initialized', 'Inspect existing artifacts and discover the web app')
    return path


def default_workspace(web):
    name = re.sub(r'[^a-zA-Z0-9_-]+', '-', Path(web).name)
    return Path(__file__).resolve().parent.parent.parent / 'apps' / name


def checkpoint(config_path, state, reason, next_action, feature=None):
    if state not in {'ready', 'running', 'needs-user', 'blocked', 'stopped'}:
        raise ValueError('Invalid checkpoint state')
    config = read_config(config_path)
    path = Path(config['workspaceRoot']) / 'progress.json'
    previous = load(path) if path.exists() else {}
    event = dict(at=now(), state=state, reason=reason, nextAction=next_action, featureId=feature)
    write_json(path, dict(**event, history=[*previous.get('history', []), event]))
    return event


def record_feature(manifest_path, flutter_root, feature_id, implementations, verifications, out):
    manifest = load(manifest_path)
    if feature_id not in {i['id'] for g in GROUPS for i in manifest[g]}:
        raise ValueError(f'Unknown feature: {feature_id}')
    root = Path(flutter_root).resolve()
    files = []
    for value in implementations:
        file = (root / value).resolve()
        if not file.is_relative_to(root / 'lib') or file.suffix != '.dart' or not file.is_file():
            raise ValueError(f'Implementation must be an existing Dart file under lib/: {value}')
        header = re.match(r'//[ \t]*@manifest-id:[ \t]*([^\r\n]+)', file.read_text())
        if not header or feature_id not in {x.strip() for x in header[1].split(',')}:
            raise ValueError(f'Implementation has no traceability for {feature_id}: {value}')
        files.append(dict(path=str(file), sha256=digest(file)))
    checks = []
    for value in verifications:
        file = Path(value).resolve()
        if not file.is_file() or not file.stat().st_size:
            raise ValueError(f'Verification evidence missing or empty: {value}')
        checks.append(dict(path=str(file), sha256=digest(file)))
    if not files or not checks:
        raise ValueError('Implementation and verification evidence are required')
    report = load(out) if Path(out).exists() else {'schemaVersion': '1.0.0', 'features': {}}
    report['features'][feature_id] = dict(recordedAt=now(), manifestSha256=digest(manifest_path), implementation=files, verification=checks)
    write_json(out, report)
    return dict(status='recorded', featureId=feature_id, evidencePath=str(out))
