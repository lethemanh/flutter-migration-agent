"""Start an interactive migration session with the packaged rules."""
from pathlib import Path
import os
import shlex
import shutil
import signal
import sys
import subprocess
from tempfile import NamedTemporaryFile
from .prompts import DESIGN_TOKEN_CONTRACT, build_system_prompt
from ..config.workspace import read_config, init_workspace, default_workspace


def bundled_codex_candidates():
    homes = (Path('/Applications'), Path.home() / 'Applications')
    relative = (
        'ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
        'Codex.app/Contents/Resources/codex',
    )
    return [base / name for base in homes for name in relative]


def resolve_codex():
    override = os.environ.get('TWAKE_CODEX_BIN')
    if override:
        candidate = shutil.which(override) or str(Path(override).expanduser())
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise ValueError('TWAKE_CODEX_BIN must point to an executable Codex CLI')
    on_path = shutil.which('codex')
    if on_path:
        return on_path
    for candidate in bundled_codex_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise ValueError('Codex CLI is required to start the agent. Install it or set TWAKE_CODEX_BIN to its executable path, then retry')


def prepare_launch(web_root, mobile_root, config_path=None):
    web = Path(web_root).expanduser().resolve()
    mobile = Path(mobile_root).expanduser().resolve()
    toolkit = Path(__file__).resolve().parent.parent.parent
    if not (web / 'package.json').is_file():
        raise ValueError(f'Web project package.json not found: {web}')
    if mobile == web or mobile.is_relative_to(web) or web.is_relative_to(mobile):
        raise ValueError('Web and mobile projects must be separate directories')
    if (toolkit / 'pyproject.toml').is_file() and mobile.is_relative_to(toolkit):
        raise ValueError('The mobile project must be outside the migration toolkit')
    codex = resolve_codex()
    config_path = config_path or init_workspace(web, mobile, default_workspace(web))
    config = read_config(config_path)
    if config['webRoot'] != str(web) or config['mobileRoot'] != str(mobile):
        raise ValueError('Launch paths do not match migration config')
    prompt = build_system_prompt(web, mobile, config_path)
    return mobile, [codex, '--cd', str(mobile), '--sandbox', 'workspace-write', '--add-dir', config['workspaceRoot'], prompt]


def run_batch(argv, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    instructions = """
Run routine work without mid-run prompts. Complete independent work using the
existing evidence and approvals. Retry a failed check only after changing an
input or correcting its cause.

When the plan is ready and lacks explicit approval for the current scope,
save a needs-user checkpoint with the plan path. Present the plan and ask
the user directly in the final result: "Do you approve this migration plan?"
Tell the user to reply in an interactive migration session and exit the batch.
Never treat a batch invocation, silence, or a request to continue as approval.

If an external prerequisite blocks the plan, present the draft, name the
missing prerequisite, and checkpoint the exact next action. Resume approved
scope only after the evidence gates pass.
"""
    command = [argv[0], '--ask-for-approval', 'never', 'exec', '--skip-git-repo-check', *argv[1:-1], argv[-1] + instructions]
    with NamedTemporaryFile(mode='w', prefix='batch-', suffix='.log', dir=artifacts, delete=False) as log:
        print(f'Migration batch log: {log.name}', flush=True)
        with subprocess.Popen(command, stdin=subprocess.DEVNULL, stderr=log, start_new_session=True) as process:
            try:
                code = process.wait(timeout=3600)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if isinstance(error, KeyboardInterrupt):
                    raise
                print('Migration batch reached its one-hour limit. Resume from the last checkpoint.')
                code = 124
    if code not in (0, 124):
        print(f'Migration batch exited with status {code}. See {log.name} for diagnostics.', file=sys.stderr)
    return code


def start_agent(web_root, mobile_root, config_path=None, *, batch=False):
    mobile, argv = prepare_launch(web_root, mobile_root, config_path)
    mobile.mkdir(parents=True, exist_ok=True)
    # Inherit the terminal; keep an argument vector, never a shell command.
    from ..config.workspace import checkpoint
    from ..core.common import load
    config_path = config_path or default_workspace(web_root) / 'migration.json'
    previous_path = Path(config_path).resolve().parent / 'progress.json'
    previous = load(previous_path) if previous_path.exists() else {}
    if previous.get('state') not in {'needs-user', 'blocked'}:
        checkpoint(config_path, 'running', 'Migration session launched', previous.get('nextAction', 'Read app workspace and continue approved work'), previous.get('featureId'))
    try:
        if batch:
            code = run_batch(argv, previous_path.parent / 'artifacts')
        else:
            command = [argv[0], '--ask-for-approval', 'on-request', *argv[1:]]
            code = subprocess.call(command)
    except (OSError, KeyboardInterrupt) as error:
        current = load(previous_path)
        if current['state'] not in {'needs-user', 'blocked'}:
            checkpoint(config_path, 'stopped', f'CLI interrupted or failed: {type(error).__name__}', current['nextAction'], current.get('featureId'))
        raise
    current = load(previous_path)
    if current['state'] in {'needs-user', 'blocked'}:
        print(f"Migration {current['state']}: {current['reason']}\nNext action: {current['nextAction']}")
    else:
        checkpoint(config_path, 'stopped', f'Migration CLI exited with status {code}; exit is not migration completion', current['nextAction'], current.get('featureId'))
    return code
