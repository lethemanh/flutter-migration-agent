"""Flutter Design Token Linter & Validator for the migration harness."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable, Sequence

from ..core.common import walk

REPLACEMENT_RULES: dict[str, str] = {
    'TOKEN_LINT_COLOR': (
        'Use design system color tokens (AppColors.<token>, TwakePalette.<token>, '
        'or Theme.of(context).colorScheme.<token>) instead of hardcoded Color(0x...), '
        'Colors.*, or raw hex strings.'
    ),
    'TOKEN_LINT_SPACING': (
        'Use design system spacing tokens (AppSpacing.<token> or TwakeSpacing.<token>, '
        'e.g., EdgeInsets.all(AppSpacing.md), SizedBox(height: AppSpacing.sm)) '
        'instead of hardcoded numeric spacing in EdgeInsets or SizedBox.'
    ),
    'TOKEN_LINT_TYPOGRAPHY': (
        'Use predefined typography tokens (AppTypography.<token>, TwakeTypography.<token>, '
        'or Theme.of(context).textTheme.<token>) instead of raw TextStyle, fontSize, or fontWeight.'
    ),
    'TOKEN_LINT_RADIUS': (
        'Use design system radius tokens (AppRadii.<token> or TwakeRadius.<token>, '
        'e.g., BorderRadius.circular(AppRadii.sm)) instead of hardcoded numeric radii.'
    ),
    'TOKEN_LINT_ICON': (
        'Use TwakeIcon(icon: TwakeIcons.<Name>) instead of hardcoded Material Icons.*.'
    ),
}

CATEGORIES: dict[str, str] = {
    'TOKEN_LINT_COLOR': 'color',
    'TOKEN_LINT_SPACING': 'spacing',
    'TOKEN_LINT_TYPOGRAPHY': 'typography',
    'TOKEN_LINT_RADIUS': 'radius',
    'TOKEN_LINT_ICON': 'icon',
}

_TOKEN_FILE_PATTERN = re.compile(
    r'^(?:app|twake|design)_(?:colors|palette|spacing|typography|radii|radius|theme|tokens)\.dart$'
    r'|_(?:tokens|theme|colors|palette|spacing|typography|radii|radius)\.dart$',
    re.IGNORECASE,
)

_COLOR_PATTERN = re.compile(
    r'\bColor\s*\(\s*0x[0-9A-Fa-f]+\s*\)'
    r'|\bColors\s*\.\s*[A-Za-z_]\w*'
    r'|(?<![/\w])[\'"]#(?:[0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})[\'"]'
)

_TYPOGRAPHY_PATTERN = re.compile(
    r'\bTextStyle\s*\('
    r'|\bfontSize\s*:\s*\d+(?:\.\d+)?'
    r'|\bfontWeight\s*:\s*FontWeight\s*\.\s*\w+'
)

_ICON_PATTERN = re.compile(r'\bIcons\s*\.\s*[A-Za-z_]\w*')

_CALL_START_PATTERN = re.compile(
    r'\b(?P<kind>'
    r'EdgeInsets\s*\.\s*(?:all|symmetric|only|fromLTRB)'
    r'|SizedBox(?:\s*\.\s*\w+)?'
    r'|(?:BorderRadius|Radius)\s*\.\s*circular'
    r')\s*\('
)

_NUMERIC_ARG_PATTERN = re.compile(r'(?:^|[(,\s:])\d+(?:\.\d+)?\b')
_SIZEDBOX_DIM_PATTERN = re.compile(r'\b(?:height|width)\s*:\s*\d+(?:\.\d+)?\b')


class TokenViolation(dict):
    """Structured design token violation supporting both dict keys and attribute access."""

    _ALIASES = {
        'file_path': 'file',
        'filePath': 'file',
        'line_number': 'line',
        'lineNumber': 'line',
        'violating_code': 'snippet',
        'violatingCode': 'snippet',
        'replacement_rule': 'replacementRule',
        'recommendation': 'replacementRule',
        'rule': 'code',
    }

    def __init__(
        self,
        *,
        file: str,
        line: int,
        code: str,
        snippet: str,
        replacement_rule: str | None = None,
        category: str | None = None,
    ) -> None:
        resolved_rule = replacement_rule or REPLACEMENT_RULES.get(code, '')
        resolved_category = category or CATEGORIES.get(code, 'token')
        super().__init__(
            file=str(file),
            line=int(line),
            code=code,
            category=resolved_category,
            snippet=snippet,
            replacementRule=resolved_rule,
        )

    def _resolve_key(self, key: str) -> str:
        return self._ALIASES.get(key, key)

    def __getitem__(self, key: str):
        return super().__getitem__(self._resolve_key(key))

    def get(self, key: str, default=None):
        return super().get(self._resolve_key(key), default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            key = self._resolve_key(key)
        return super().__contains__(key)

    def __getattr__(self, name: str):
        resolved = self._resolve_key(name)
        if super().__contains__(resolved):
            return super().__getitem__(resolved)
        raise AttributeError(f'{type(self).__name__!r} object has no attribute {name!r}')

    def format_error(self) -> str:
        return f"[{self['code']}] {self['file']}:{self['line']}: {self['snippet']}"


def is_token_definition_file(file_path: str | Path) -> bool:
    """Return True if file_path is a theme or design-token definition file."""
    path = Path(file_path)
    lower_parts = {part.lower() for part in path.parts[:-1]}
    if {'tokens', 'theme', 'themes'} & lower_parts:
        return True
    return bool(_TOKEN_FILE_PATTERN.search(path.name))


def _strip_comments(source: str) -> list[str]:
    """Strip // and /* */ comments while preserving line count and string literals."""
    lines = source.splitlines()
    clean_lines: list[str] = []
    in_block_comment = False

    for raw_line in lines:
        out: list[str] = []
        i = 0
        n = len(raw_line)
        in_Quote: str | None = None
        while i < n:
            ch = raw_line[i]
            nxt = raw_line[i + 1] if i + 1 < n else ''
            if in_block_comment:
                if ch == '*' and nxt == '/':
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if in_Quote:
                out.append(ch)
                if ch == '\\' and i + 1 < n:
                    out.append(raw_line[i + 1])
                    i += 2
                    continue
                if ch == in_Quote:
                    in_Quote = None
                i += 1
                continue
            if ch == '/' and nxt == '/':
                break
            if ch == '/' and nxt == '*':
                in_block_comment = True
                i += 2
                continue
            if ch in ("'", '"'):
                in_Quote = ch
            out.append(ch)
            i += 1
        clean_lines.append(''.join(out))
    return clean_lines


def _extract_top_level_segments(
    line: str,
    active_stack: list[tuple[str, int]],
    base_depth: int,
) -> tuple[dict[str, list[str]], list[tuple[str, int]], int]:
    """Track call contexts (EdgeInsets, SizedBox, BorderRadius.circular) across lines."""
    segments: dict[str, list[str]] = {'EdgeInsets': [], 'SizedBox': [], 'Radius': []}
    buffers: dict[int, tuple[str, list[str]]] = {
        depth: (kind, []) for kind, depth in active_stack
    }

    starts: dict[int, str] = {}
    for match in _CALL_START_PATTERN.finditer(line):
        raw_kind = re.sub(r'\s+', '', match.group('kind'))
        kind = (
            'EdgeInsets'
            if raw_kind.startswith('EdgeInsets.')
            else 'SizedBox'
            if raw_kind.startswith('SizedBox')
            else 'Radius'
        )
        open_idx = match.end() - 1
        starts[open_idx] = kind

    depth = base_depth
    in_quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_quote:
            for target_depth, (_, buf) in buffers.items():
                if depth == target_depth:
                    buf.append(ch)
            if ch == '\\' and i + 1 < n:
                i += 1
                for target_depth, (_, buf) in buffers.items():
                    if depth == target_depth:
                        buf.append(line[i])
            elif ch == in_quote:
                in_quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            in_quote = ch
            for target_depth, (_, buf) in buffers.items():
                if depth == target_depth:
                    buf.append(ch)
            i += 1
            continue

        if ch == '(':
            depth += 1
            if i in starts:
                kind = starts[i]
                active_stack.append((kind, depth))
                buffers[depth] = (kind, ['('])
            else:
                for target_depth, (_, buf) in buffers.items():
                    if depth - 1 == target_depth:
                        buf.append('(')
            i += 1
            continue

        if ch == ')':
            if depth in buffers:
                kind, buf = buffers.pop(depth)
                buf.append(')')
                segments[kind].append(''.join(buf))
                active_stack[:] = [(k, d) for k, d in active_stack if d != depth]
            depth = max(0, depth - 1)
            for target_depth, (_, buf) in buffers.items():
                if depth == target_depth:
                    buf.append(')')
            i += 1
            continue

        for target_depth, (_, buf) in buffers.items():
            if depth == target_depth:
                buf.append(ch)
        i += 1

    for target_depth, (kind, buf) in buffers.items():
        if buf:
            segments[kind].append(''.join(buf))

    return segments, active_stack, depth


def lint_dart_code(
    source: str,
    file_path: str | Path = '<memory>',
    *,
    check_icons: bool = True,
) -> list[TokenViolation]:
    """Scan Dart source code and return all detected design token violations."""
    raw_lines = source.splitlines()
    clean_lines = _strip_comments(source)
    violations: list[TokenViolation] = []
    active_stack: list[tuple[str, int]] = []
    depth = 0
    file_str = str(file_path)

    for line_number, (raw_line, clean_line) in enumerate(zip(raw_lines, clean_lines), start=1):
        stripped_clean = clean_line.strip()
        if not stripped_clean:
            continue
        snippet = raw_line.strip()
        line_codes: list[str] = []

        if _COLOR_PATTERN.search(clean_line):
            line_codes.append('TOKEN_LINT_COLOR')

        if _TYPOGRAPHY_PATTERN.search(clean_line):
            line_codes.append('TOKEN_LINT_TYPOGRAPHY')

        segments, active_stack, depth = _extract_top_level_segments(clean_line, active_stack, depth)

        spacing_violation = any(
            _NUMERIC_ARG_PATTERN.search(seg) for seg in segments['EdgeInsets']
        ) or any(
            _SIZEDBOX_DIM_PATTERN.search(seg) for seg in segments['SizedBox']
        )
        if spacing_violation:
            line_codes.append('TOKEN_LINT_SPACING')

        radius_violation = any(
            _NUMERIC_ARG_PATTERN.search(seg) for seg in segments['Radius']
        )
        if radius_violation:
            line_codes.append('TOKEN_LINT_RADIUS')

        if check_icons and _ICON_PATTERN.search(clean_line):
            line_codes.append('TOKEN_LINT_ICON')

        for code in line_codes:
            violations.append(
                TokenViolation(
                    file=file_str,
                    line=line_number,
                    code=code,
                    snippet=snippet,
                )
            )

    return violations


def lint_dart_file(
    file_path: str | Path,
    *,
    root: str | Path | None = None,
    skip_token_files: bool = False,
    check_icons: bool = True,
) -> list[TokenViolation]:
    """Lint a single Dart file and return structured TokenViolation entries."""
    path = Path(file_path).resolve()
    display_path = (
        path.relative_to(Path(root).resolve()).as_posix()
        if root and path.is_relative_to(Path(root).resolve())
        else str(file_path)
    )
    if skip_token_files and is_token_definition_file(display_path):
        return []
    return lint_dart_code(path.read_text(), display_path, check_icons=check_icons)


class DesignTokenValidator:
    """Validator that scans Flutter Dart files for prohibited hardcoded design values."""

    def __init__(
        self,
        flutter_root: str | Path | None = None,
        *,
        skip_token_files: bool = False,
        check_icons: bool = True,
    ) -> None:
        self.flutter_root = Path(flutter_root).resolve() if flutter_root else None
        self.skip_token_files = skip_token_files
        self.check_icons = check_icons

    def validate_code(self, source: str, file_path: str | Path = '<memory>') -> list[TokenViolation]:
        if self.skip_token_files and is_token_definition_file(file_path):
            return []
        return lint_dart_code(source, file_path, check_icons=self.check_icons)

    def validate_file(self, file_path: str | Path) -> list[TokenViolation]:
        return lint_dart_file(
            file_path,
            root=self.flutter_root,
            skip_token_files=self.skip_token_files,
            check_icons=self.check_icons,
        )

    def validate_files(self, files: Iterable[str | Path]) -> dict:
        violations: list[TokenViolation] = []
        scanned: list[str] = []
        for f in files:
            path = Path(f)
            if not path.is_absolute() and self.flutter_root:
                path = self.flutter_root / path
            if not path.is_file() or path.suffix != '.dart':
                continue
            rel = (
                path.resolve().relative_to(self.flutter_root).as_posix()
                if self.flutter_root and path.resolve().is_relative_to(self.flutter_root)
                else str(f)
            )
            if self.skip_token_files and is_token_definition_file(rel):
                continue
            scanned.append(rel)
            violations.extend(
                lint_dart_file(
                    path,
                    root=self.flutter_root,
                    skip_token_files=self.skip_token_files,
                    check_icons=self.check_icons,
                )
            )
        return {
            'passed': len(violations) == 0,
            'filesScanned': scanned,
            'violations': violations,
            'errors': [v.format_error() for v in violations],
        }

    def validate_project(self, flutter_root: str | Path | None = None) -> dict:
        target_root = Path(flutter_root).resolve() if flutter_root else self.flutter_root
        if target_root is None:
            raise ValueError('flutter_root is required for validate_project')
        search_root = target_root / 'lib' if (target_root / 'lib').is_dir() else target_root
        dart_files = list(walk(search_root, {'.dart'}))
        prev_root = self.flutter_root
        self.flutter_root = target_root
        try:
            return self.validate_files(dart_files)
        finally:
            self.flutter_root = prev_root


def lint_flutter_tokens(
    target: str | Path | Sequence[str | Path],
    *,
    root: str | Path | None = None,
    skip_token_files: bool = False,
    check_icons: bool = True,
) -> dict:
    """Convenience entry point to lint a directory, a single Dart file, or a sequence of files."""
    if isinstance(target, (str, Path)):
        path = Path(target)
        if path.is_dir():
            validator = DesignTokenValidator(
                path, skip_token_files=skip_token_files, check_icons=check_icons
            )
            return validator.validate_project(path)
        validator = DesignTokenValidator(
            root, skip_token_files=skip_token_files, check_icons=check_icons
        )
        return validator.validate_files([path])
    validator = DesignTokenValidator(
        root, skip_token_files=skip_token_files, check_icons=check_icons
    )
    return validator.validate_files(target)

