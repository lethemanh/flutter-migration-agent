from __future__ import annotations

import difflib
import inspect
import logging
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Sequence

from ..core.common import load, GROUPS, walk, digest
from .prompts import build_system_prompt, DESIGN_TOKEN_CONTRACT
from ..core.validation import feature_refs
from ..parsers.discovery import source_files
from ..parsers.token_linter import (
    DesignTokenValidator,
    TokenViolation,
    lint_dart_file,
)
def validate_manifest(manifest_path):
    from ..core.validation import validate_manifest as _validate_manifest

    return _validate_manifest(manifest_path)


def validate_tokens(ui_root):
    from ..parsers.tokens import validate_tokens as _validate_tokens

    return _validate_tokens(ui_root)

COMPLETION_TOOLS: frozenset[str] = frozenset({
    'finish_task',
    'complete',
    'complete_task',
    'submit',
})

MAX_TOKEN_RETRIES: int = 3


def format_token_violation_feedback(
    violations: Sequence[TokenViolation],
    attempt: int = 1,
    max_retries: int = MAX_TOKEN_RETRIES,
) -> str:
    """Format a structured, actionable observation message for rejected completion turns."""
    lines = [
        f'[DESIGN_TOKEN_GUARDRAIL_REJECTED] Task completion rejected '
        f'(attempt {attempt}/{max_retries}).',
        f'Detected {len(violations)} hardcoded design token violation(s):',
    ]
    for v in violations:
        lines.append(
            f"- {v['file']}:{v['line']} [{v['code']}] `{v['snippet']}` -> "
            f"Expected: {v['replacementRule']}"
        )
    lines.append(
        'Refactor all offending lines above to use the project Design Tokens '
        '(AppColors / TwakePalette, AppSpacing / TwakeSpacing, '
        'AppTypography / TwakeTypography, AppRadii / TwakeRadius) and '
        'invoke `finish_task` / `complete` again.'
    )
    return '\n'.join(lines)


class HarnessOrchestrator:
    """Agent harness state machine enforcing design token compliance before task completion."""

    def __init__(
        self,
        flutter_root: str | Path,
        *,
        web_root: str | Path | None = None,
        max_retries: int = MAX_TOKEN_RETRIES,
        system_prompt: str | None = None,
        validator: DesignTokenValidator | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.flutter_root = Path(flutter_root).resolve()
        self.web_root = Path(web_root).resolve() if web_root else None
        self.max_retries = max_retries
        self.validator = validator or DesignTokenValidator(self.flutter_root)
        self.logger = logger or logging.getLogger(__name__)
        self.system_prompt = system_prompt or build_system_prompt(self.web_root, self.flutter_root)
        self.history: list[dict[str, Any]] = [
            {'role': 'system', 'content': self.system_prompt},
        ]
        self.modified_files: list[Path] = []
        self._baseline_snapshots: dict[str, str] = {}
        self.retry_count: int = 0
        self.completed: bool = False
        self.halted: bool = False
        self.unresolvable_diff: str | None = None
        self.logs: list[str] = []
        self._completion_checks: int = 0
        self._last_result: dict[str, Any] | None = None

    @property
    def attempts(self) -> int:
        return self.retry_count

    def track_file(
        self,
        file_path: str | Path,
        *,
        content: str | None = None,
        original_content: str | None = None,
    ) -> Path:
        """Record a modified or created Flutter file and capture its pre-edit baseline."""
        path = Path(file_path)
        if not path.is_absolute():
            path = (self.flutter_root / path).resolve()
        else:
            path = path.resolve()
        key = str(path)
        if key not in self._baseline_snapshots:
            if original_content is not None:
                self._baseline_snapshots[key] = original_content
            elif path.is_file() and content is not None:
                self._baseline_snapshots[key] = path.read_text()
            else:
                self._baseline_snapshots[key] = ''
        if content is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        if path not in self.modified_files:
            self.modified_files.append(path)
        return path

    record_file_change = track_file

    def _target_files(self, files: Iterable[str | Path] | None = None) -> list[Path]:
        if files is not None:
            resolved: list[Path] = []
            for f in files:
                p = Path(f)
                if not p.is_absolute():
                    p = (self.flutter_root / p).resolve()
                if p.is_file() and p.suffix == '.dart':
                    resolved.append(p)
            return resolved
        search_root = self.flutter_root / 'lib' if (self.flutter_root / 'lib').is_dir() else self.flutter_root
        discovered = list(walk(search_root, {'.dart'})) if search_root.is_dir() else []
        combined: list[Path] = []
        seen: set[Path] = set()
        for p in [*self.modified_files, *discovered]:
            rp = p.resolve()
            if rp not in seen and rp.is_file() and rp.suffix == '.dart':
                seen.add(rp)
                combined.append(rp)
        return combined

    def _build_unresolvable_diff(self, violations: Sequence[TokenViolation]) -> str:
        sections: list[str] = [
            f'=== UNRESOLVABLE DESIGN TOKEN DIFF (halted after {self.retry_count} attempts) ==='
        ]
        by_file: dict[str, list[TokenViolation]] = {}
        for v in violations:
            by_file.setdefault(v['file'], []).append(v)

        for rel_file, file_violations in by_file.items():
            full_path = (self.flutter_root / rel_file).resolve()
            current_text = full_path.read_text() if full_path.is_file() else ''
            baseline_text = self._baseline_snapshots.get(str(full_path), '')
            diff_lines = list(
                difflib.unified_diff(
                    baseline_text.splitlines(keepends=True),
                    current_text.splitlines(keepends=True),
                    fromfile=f'a/{rel_file}',
                    tofile=f'b/{rel_file}',
                )
            )
            if diff_lines:
                sections.append(''.join(diff_lines).rstrip('\n'))
            for v in file_violations:
                sections.append(
                    f"@@ {v['file']}:{v['line']} [{v['code']}] @@\n"
                    f"- {v['snippet']}\n"
                    f"+ Expected: {v['replacementRule']}"
                )
        return '\n'.join(sections)

    def intercept_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        *,
        files: Iterable[str | Path] | None = None,
    ) -> dict[str, Any]:
        """Intercept agent tool calls and run the Design Token Validator on finish_task/complete."""
        args = tool_args or {}
        if tool_name not in COMPLETION_TOOLS:
            target = args.get('path') or args.get('file') or args.get('file_path')
            if target and str(target).endswith('.dart'):
                self.track_file(target, content=args.get('content'))
            self.history.append({'role': 'assistant', 'tool': tool_name, 'args': args})
            result = {
                'intercepted': False,
                'accepted': True,
                'completed': self.completed,
                'halted': self.halted,
                'retryCount': self.retry_count,
                'violations': [],
                'feedback': None,
                'unresolvableDiff': self.unresolvable_diff,
            }
            self._last_result = result
            return result

        self._completion_checks += 1
        self.history.append({'role': 'assistant', 'tool': tool_name, 'args': args})
        validation = self.validator.validate_files(self._target_files(files))
        violations: list[TokenViolation] = validation['violations']

        if not violations:
            self.completed = True
            self.halted = False
            result = {
                'intercepted': True,
                'accepted': True,
                'completed': True,
                'halted': False,
                'retryCount': self.retry_count,
                'violations': [],
                'feedback': None,
                'unresolvableDiff': None,
            }
            self.history.append(
                {
                    'role': 'tool',
                    'tool': tool_name,
                    'status': 'completed',
                    'content': 'Design token validation passed. Task marked as complete.',
                }
            )
            self._last_result = result
            return result

        self.completed = False
        self.retry_count += 1
        feedback = format_token_violation_feedback(
            violations, attempt=self.retry_count, max_retries=self.max_retries
        )
        self.history.append(
            {
                'role': 'user',
                'type': 'token_validation_feedback',
                'attempt': self.retry_count,
                'violations': violations,
                'content': feedback,
            }
        )

        if self.retry_count >= self.max_retries:
            self.halted = True
            self.unresolvable_diff = self._build_unresolvable_diff(violations)
            self.logs.append(self.unresolvable_diff)
            self.logger.error(
                'Token validation failed after %d attempts. Halting.\n%s',
                self.retry_count,
                self.unresolvable_diff,
            )

        result = {
            'intercepted': True,
            'accepted': False,
            'completed': False,
            'halted': self.halted,
            'shouldRetry': not self.halted,
            'retryCount': self.retry_count,
            'violations': violations,
            'feedback': feedback,
            'unresolvableDiff': self.unresolvable_diff,
        }
        self._last_result = result
        return result

    def _invoke_agent(self, agent_fn: Callable[..., Any]) -> Any:
        try:
            sig = inspect.signature(agent_fn)
            params = [
                p
                for p in sig.parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
            if has_varargs or len(params) >= 2:
                return agent_fn(self.history, self)
            if len(params) == 1:
                return agent_fn(self.history)
            return agent_fn()
        except TypeError:
            return agent_fn(self.history)

    def run(self, agent_fn: Callable[..., Any]) -> dict[str, Any]:
        """Execute the agent turn loop with pre-completion token validation and up to max_retries."""
        while not self.completed and not self.halted:
            checks_before = self._completion_checks
            response = self._invoke_agent(agent_fn)
            if self._completion_checks > checks_before and self._last_result is not None:
                continue

            tool_name = 'finish_task'
            tool_args: dict[str, Any] = {}
            if isinstance(response, str):
                tool_name = response
            elif isinstance(response, dict):
                tool_name = (
                    response.get('tool')
                    or response.get('tool_name')
                    or response.get('name')
                    or 'finish_task'
                )
                tool_args = response.get('args') or response.get('arguments') or {}

            self.intercept_tool_call(tool_name, tool_args)
            if tool_name not in COMPLETION_TOOLS:
                # Non-completion tool executed; continue to next turn unless agent stops
                continue

        return (
            self._last_result
            if self._last_result is not None
            else {
                'intercepted': False,
                'accepted': self.completed,
                'completed': self.completed,
                'halted': self.halted,
                'retryCount': self.retry_count,
                'violations': [],
                'feedback': None,
                'unresolvableDiff': self.unresolvable_diff,
            }
        )


AgentHarness = HarnessOrchestrator


def harness_check(
    manifest_path,
    gap_report_path,
    widget_map_path,
    flutter_root,
    plan_path=None,
    allow_draft=False,
    strict_coverage=None,
    require_parity=True,
    parity_report_path=None,
    evidence_path=None,
):
    strict_coverage = require_parity if strict_coverage is None else strict_coverage
    if require_parity:
        strict_coverage = True
    validation = validate_manifest(manifest_path)
    if not validation['valid']:
        return dict(
            passed=False,
            errors=['[MANIFEST_INVALID] ' + e for e in validation['errors']],
            warnings=[],
            coverage={},
        )
    manifest, gaps, mappings = (
        load(manifest_path),
        load(gap_report_path)['gaps'],
        load(widget_map_path)['mappings'],
    )
    tokens = validate_tokens(Path(widget_map_path).parent)
    errors = ['[DESIGN_TOKEN_MISMATCH] ' + e for e in tokens['errors']]

    def error(code, message):
        errors.append(f'[{code}] {message}')

    if require_parity and allow_draft:
        error('DRAFT_COMPLETION_FORBIDDEN', 'Final verification requires approved manifest and plan')
    if not allow_draft and manifest['approval']['status'] != 'approved':
        error('MANIFEST_NOT_APPROVED', 'Manifest requires user approval')
    plan_path = plan_path or Path(manifest_path).with_name('migration-plan.json')
    discovery = None
    if plan_path:
        if not Path(plan_path).is_file():
            error('MIGRATION_PLAN_MISSING', str(plan_path))
        else:
            plan = load(plan_path)
            if not allow_draft and plan['approval']['status'] != 'approved':
                error('MIGRATION_PLAN_NOT_APPROVED', 'Migration plan requires user approval')
            elif plan.get('approvedScope'):
                from ..core.validation import current_plan_discovery
                discovery = current_plan_discovery(manifest, manifest_path, gap_report_path, plan)
                if require_parity and not discovery.get('complete'):
                    error('INCOMPLETE_DISCOVERY', '; '.join(discovery['blockers']))
            elif plan.get('discoveryReview', {}).get('readyForApproval') is False:
                error('INCOMPLETE_DISCOVERY', 'Reconcile source functions and original app UI before migration')
    items = {i['id']: i for group in GROUPS for i in manifest[group]}
    routes = {r['path'] for r in manifest['routes']}
    keys = set(manifest['i18n']['keys'])
    referenced = set()
    flutter_path = Path(flutter_root)
    files = list(walk(flutter_path / 'lib', {'.dart'}))
    if not files:
        error('MISSING_FLUTTER_FILES', 'No Dart files found under lib/')
    token_violations: list[TokenViolation] = []
    for file in files:
        relative = file.relative_to(flutter_path)
        content = file.read_text()
        headers = re.findall(r'\A//[ \t]*@manifest-id:\s*([^\r\n]+)', content, re.M)
        if not headers:
            error('MISSING_MANIFEST_ID', str(relative))
        for header in headers:
            for item_id in map(str.strip, header.split(',')):
                if item_id not in items:
                    error('REVERSE_CHECK_INVENTED_ID', f'{relative}: {item_id}')
                else:
                    referenced.add(item_id)
        match = re.search(r'\A[^\r\n]*\r?\n//[ \t]*@source-react:\s*([^\r\n]+)', content, re.M)
        if not match:
            error('MISSING_SOURCE_TRACEABILITY', str(relative))
        else:
            for source in map(str.strip, match[1].split(',')):
                base = Path(manifest['app']['sourceRoot']).resolve()
                target = (base / source).resolve()
                if not target.is_relative_to(base) or not target.is_file():
                    error('BROKEN_SOURCE_TRACEABILITY', f'{relative}: {source}')
        for route in re.findall(r'GoRoute\(\s*path:\s*[\'"]([^\'"]+)[\'"]', content):
            if route not in routes:
                error('REVERSE_CHECK_INVENTED_ROUTE', f'{relative}: {route}')
        for key in re.findall(r'TwakeI18n\.t\(\s*[\'"]([^\'"]+)[\'"]', content):
            if key not in keys:
                error('REVERSE_CHECK_INVENTED_I18N_KEY', f'{relative}: {key}')
        file_violations = lint_dart_file(file, root=flutter_path, skip_token_files=False)
        for v in file_violations:
            token_violations.append(v)
            error(v['code'], f"{v['file']}:{v['line']}: {v['snippet']}")
    for item_id in sorted(referenced):
        if discovery is not None and not require_parity and not discovery.get('featureReadiness', {}).get(item_id, {}).get('ready'):
            error('INCOMPLETE_FEATURE_DISCOVERY', item_id)
        item = items[item_id]
        for name in item.get('twakeMuiComponents', []):
            if mappings.get(name, {}).get('status', 'unimplemented') == 'unimplemented':
                error('BLOCKED_MISSING_COMPONENT', f'{item_id}: {name}')
        refs = feature_refs(manifest, item_id)
        for gap in gaps:
            if gap['manifestRef'] in refs and gap['status'] == 'unresolved-ask-user':
                error('BLOCKED_UNRESOLVED_MOBILE_GAP', f"{item_id}: {gap['id']}")
    coverage = {
        group: dict(
            covered=sum(i['id'] in referenced for i in manifest[group]),
            total=len(manifest[group]),
        )
        for group in GROUPS
    }
    if strict_coverage:
        for category, stats in coverage.items():
            if stats['covered'] < stats['total']:
                error('INCOMPLETE_COVERAGE', f"{category}: {stats['covered']}/{stats['total']}")
    if require_parity:
        audit_path = Path(manifest_path).with_name('discovery-audit.json')
        audit = load(audit_path) if audit_path.is_file() else {}
        review = audit.get('review', {})
        if review.get('status') != 'reviewed' or not review.get('reviewedBy') or not review.get('notes'):
            error('DISCOVERY_REVIEW_REQUIRED', 'Reconcile source handlers/routes/services with the manifest and record human review in discovery-audit.json')
        if not audit.get('sourceHashes'):
            error('DISCOVERY_REVIEW_REQUIRED', 'Discovery source fingerprints are missing')
        actual_sources = {str(p.relative_to(Path(manifest['app']['sourceRoot']))) for p in source_files(Path(manifest['app']['sourceRoot']))}
        if actual_sources != set(audit.get('sourceHashes', {})):
            error('DISCOVERY_SOURCE_CHANGED', 'Source file inventory changed; refresh discovery review')
        for relative, expected in audit.get('sourceHashes', {}).items():
            source = (Path(manifest['app']['sourceRoot']) / relative).resolve()
            if not source.is_relative_to(Path(manifest['app']['sourceRoot']).resolve()) or not source.is_file() or digest(source) != expected:
                error('DISCOVERY_SOURCE_CHANGED', relative)
        evidence = load(evidence_path).get('features', {}) if evidence_path and Path(evidence_path).is_file() else {}
        for item_id in items:
            entry = evidence.get(item_id, {})
            if entry.get('manifestSha256') != digest(manifest_path):
                error('FEATURE_EVIDENCE_MISSING_OR_STALE', item_id)
                continue
            for category in ('implementation', 'verification'):
                records = entry.get(category, [])
                if not records:
                    error('FEATURE_EVIDENCE_MISSING_OR_STALE', f'{item_id}: {category}')
                for record in records:
                    file = Path(record.get('path', '')).resolve()
                    if not file.is_file() or not file.stat().st_size or digest(file) != record.get('sha256'):
                        error('FEATURE_EVIDENCE_MISSING_OR_STALE', f'{item_id}: {file}')
                    elif category == 'implementation' and (not file.is_relative_to(flutter_path.resolve() / 'lib') or item_id not in file.read_text()):
                        error('FEATURE_EVIDENCE_INVALID', f'{item_id}: {file}')
        if not parity_report_path or not Path(parity_report_path).is_file():
            error('PARITY_GATE_MISSING', 'A light/dark pixel and flow parity report is required')
        else:
            parity = load(parity_report_path)
            if (
                parity.get('schemaVersion') != '2.0.0'
                or parity.get('comparison') != 'decoded-rgba-pixels'
                or not parity.get('allPassed')
            ):
                error(
                    'PARITY_GATE_FAILED',
                    'A passing decoded-pixel light/dark parity report is required',
                )
            current_flutter_hashes = {str(p.relative_to(flutter_path)):digest(p) for p in files}
            if parity.get('flutterRoot') != str(flutter_path.resolve()) or parity.get('flutterSourceHashes') != current_flutter_hashes:
                error('PARITY_GATE_FAILED', 'Flutter source changed or parity report has no Flutter source fingerprints; rerun captures and verify-parity --flutter')
            if parity.get('manifestSha256') != digest(manifest_path):
                error('PARITY_GATE_FAILED', 'Parity report belongs to a different manifest')
            if not parity.get('inputs'):
                error('PARITY_GATE_FAILED', 'Parity report has no input fingerprints')
            for record in parity.get('inputs', []):
                path = Path(record['path'])
                if not path.is_file() or digest(path) != record.get('sha256'):
                    error('PARITY_GATE_FAILED', f'Stale parity input: {path}')
            for item_id in sorted(items):
                if not item_id.startswith('SCREEN_'):
                    continue
                screen = next(
                    (s for s in parity.get('screens', []) if s['screenId'] == item_id),
                    {},
                )
                checked_flows = {f.get('flowId') for f in screen.get('flowsChecked', []) if f.get('passed') is True}
                expected_flows = {f['id'] for f in manifest['flows'] if f['screenId'] == item_id}
                if not expected_flows <= checked_flows:
                    error('PARITY_GATE_FAILED', f'{item_id}: missing flow evidence')
                themes = screen.get('visualDiff', {}).get('themes', {})
                if not screen.get('passed') or not all(
                    themes.get(m, {}).get('passed') for m in ('light', 'dark')
                ):
                    error('PARITY_GATE_FAILED', item_id)
    return dict(
        passed=not errors,
        errors=errors,
        warnings=[] if require_parity else ['Development check only: full coverage, feature evidence and visual parity are required for completion.'],
        tokenViolations=token_violations,
        referencedIds=sorted(referenced),
        coverage=coverage,
        verification=dict(
            tokenValues=tokens['passed'],
            visualParityRequired=require_parity,
            completionVerified=require_parity and strict_coverage and not allow_draft and not errors,
        ),
    )
