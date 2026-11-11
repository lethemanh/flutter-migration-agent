"""Fingerprint reusable browser observations without storing session credentials."""
import hashlib
import json
from pathlib import Path

from PIL import Image

from ..core.common import digest, discovery_fingerprint, load
from ..parsers.discovery import source_files
from ..parsers.source_resolution import source_config_hashes


def evidence_key(manifest, plan, base_url, storage_state, executable_path, allow_mutations, capture_plan=None):
    root = Path(manifest['app']['sourceRoot']).resolve()
    plan_root = Path(capture_plan).resolve().parent if capture_plan else Path.cwd()
    inputs = {name: digest(plan_root / name) for name in plan.get('evidenceInputs', [])}
    return fingerprint(dict(
        manifest=discovery_fingerprint(manifest),
        sources={path.relative_to(root).as_posix(): digest(path) for path in source_files(root)},
        config=source_config_hashes(root),
        plan={key: value for key, value in plan.items() if key not in {'journeys', 'routes'}},
        url=base_url, session=digest(storage_state) if storage_state else None,
        browser=executable_path, mutations=allow_mutations, inputs=inputs,
    ))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def verified_capture(root, item):
    path = (root / item['screenshotPath']).resolve()
    if not path.is_relative_to(root) or not path.is_file() or digest(path) != item.get('screenshotSha256'):
        return False
    try:
        with Image.open(path) as image:
            image.load()
            return image.format == 'PNG' and image.size == (390, 844)
    except (OSError, ValueError):
        return False


def reuse_runtime(report_path, key, journeys, route_keys=None):
    if not report_path.is_file():
        return [], [], [], set()
    report = load(report_path)
    if report.get('evidenceKey') != key or report.get('status') not in {'ok', 'partial'}:
        return [], [], [], set()
    root = report_path.parent.resolve()
    prior_route_keys = report.get('routeKeys', {})
    if route_keys is None:
        route_keys = prior_route_keys
    captures = [c for c in report['captures']
                if prior_route_keys.get(c['routeId']) == route_keys.get(c['routeId'])
                and (not route_keys or c['routeId'] in route_keys) and verified_capture(root, c)]
    cached = {}
    for observation in report['observations']:
        cached.setdefault((observation['journeyId'], observation['themeMode']), []).append(observation)
    observations, reusable = [], set()
    for journey in journeys:
        name = journey['id']
        route_id = journey.get('routeId')
        if (report.get('journeyKeys', {}).get(name) != fingerprint(journey)
                or prior_route_keys.get(route_id) != route_keys.get(route_id)):
            continue
        for theme in ('light', 'dark'):
            pair = (name, theme)
            steps = cached.get(pair, [])
            if ({step['step'] for step in steps} == set(range(len(journey['steps'])))
                    and all(step['passed'] and verified_capture(root, step['before'])
                            and verified_capture(root, step['after']) for step in steps)):
                reusable.add(pair)
                observations.extend(steps)
    capture_keys = {(capture['routeId'], capture['themeMode']) for capture in captures}
    records = [r for r in report.get('networkRecords', [])
               if ((r.get('journeyId'), r.get('themeMode')) in reusable
                   if r.get('journeyId') else (r.get('routeId'), r.get('themeMode')) in capture_keys)]
    return captures, observations, records, reusable
