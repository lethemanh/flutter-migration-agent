"""Validate observed inactive controls without claiming callback invocation.

A disposition covers a source callback only when its inaccessible trigger and
an invoked control sharing its exact handler are both evidenced. It is not an
exemption for unavailable runtime data or an unimplemented feature.
"""
from pathlib import Path
from PIL import Image
from .common import digest


# Supported installed implementation reviewed end-to-end: package export,
# forwarding component, mobile wrapper, and rendered bottom sheet. Unknown or
# edited versions fail closed; an artifact cannot declare its own trusted hash.
UNFORWARDED_ACTIONS_MENU = {
    '@linagora/twake-mui/dist/index.js': '94f082cefa36e07ae8495ba932ac94c3d9a3dd3e2677ccdaf5aed14b86b9132c',
    '@linagora/twake-mui/dist/components/ActionsMenu/index.js': 'b0fcf026f096b98fe14a69f26290549777c4a9aada877e30900ebe4bf767ebb1',
    '@linagora/twake-mui/dist/components/ActionsMenu/ActionsMenuWrapper.js': 'f85cf3fa3ab7ca76b75a1ecf85ed1d73ce4e5cbbe979b5b166c41a528f0eff2a',
    '@linagora/twake-mui/dist/components/BottomSheet/index.js': '8fffd16a9f38cc0d3f90cca95b328a233bdf61830585506c028175af7582d68f',
}


# MUI 19.5 adds exports to the package entrypoint. Its ActionsMenu export and
# all three implementation files above are unchanged from the reviewed chain.
# Only these two reviewed entrypoints qualify; artifacts cannot supply trust.
UNFORWARDED_ACTIONS_MENU_ENTRYPOINTS = frozenset({
    UNFORWARDED_ACTIONS_MENU['@linagora/twake-mui/dist/index.js'],
    '4fc0bbaeac53720759c797c9c8b80ccb703c5a51c8e2d97b45d4380d892f2dd1',
})


def _trusted_menu_hash(path, sha):
    if path == '@linagora/twake-mui/dist/index.js':
        return sha in UNFORWARDED_ACTIONS_MENU_ENTRYPOINTS
    return sha == UNFORWARDED_ACTIONS_MENU[path]


def _unforwarded_menu(action, alternatives, actions, disposition, root, fingerprint):
    """Only a discarded, side-effect-free propagation callback qualifies.

    The exact supported mobile implementation drops wrapper props. Its child
    item handler is independently invoked; it is not claimed to share this
    discarded callback. No API or state-changing callback can use this rule.
    """
    from ..parsers.javascript import parse, descendants, text
    evidence = disposition.get('libraryChainEvidence', [])
    if (not isinstance(evidence, list) or len(evidence) != len(UNFORWARDED_ACTIONS_MENU)
        or {e.get('path') for e in evidence} != set(UNFORWARDED_ACTIONS_MENU)
        or not all(_trusted_menu_hash(e['path'], e.get('sha256'))
                   and fingerprint(e, root / 'node_modules') for e in evidence)):
        return 'unsupported or changed mobile library implementation'
    try:
        tree = parse((root / action['sourceFile']).read_text(), 'tsx')
        def attribute(candidate):
            found = [n for n in descendants(tree, 'jsx_attribute')
                     if n.start_point.row + 1 == candidate['sourceLine']
                     and text(n.named_children[0]) == candidate['event']]
            if len(found) != 1:
                raise ValueError('ambiguous source attribute')
            return found[0]
        attr = attribute(action)
        opening = attr.parent
        if action['event'] != 'onClick' or text(opening.child_by_field_name('name')) != 'ActionsMenu':
            return 'guard must belong to ActionsMenu.onClick'
        # Require the actual named package import, without aliases or re-exports.
        imports = [n for n in descendants(tree, 'import_statement')
                   if text(n.child_by_field_name('source')).strip('\"\'') == '@linagora/twake-mui']
        if not any(text(n.child_by_field_name('name')) == 'ActionsMenu'
                   and n.child_by_field_name('alias') is None
                   for imp in imports for n in descendants(imp, 'import_specifier')):
            return 'direct ActionsMenu library import is required'
        arrows = list(descendants(attr, 'arrow_function'))
        if len(arrows) != 1:
            return 'only a direct propagation callback is supported'
        arrow = arrows[0]
        param = arrow.child_by_field_name('parameter')
        body = arrow.child_by_field_name('body')
        if param is None or param.type != 'identifier' or body.type != 'call_expression':
            return 'only a direct propagation callback is supported'
        function = body.child_by_field_name('function')
        arguments = body.child_by_field_name('arguments')
        if (function.type != 'member_expression'
            or text(function.child_by_field_name('object')) != text(param)
            or text(function.child_by_field_name('property')) != 'stopPropagation'
            or arguments.named_children
            or text(attr.named_children[1]).strip() != '{' + text(arrow) + '}'):
            return 'callback contains behavior beyond stopping propagation'
        owner = opening.parent
        if owner.type != 'jsx_element':
            return 'ActionsMenu must own explicit child actions'
        for alternative in alternatives:
            other = attribute(actions[alternative])
            parent = other.parent
            if actions[alternative]['event'] != 'onClick' or text(parent.child_by_field_name('name')) != 'ActionsMenuItem':
                return 'invoked alternative must be an ActionsMenuItem'
            ancestor = parent.parent
            while ancestor is not None and ancestor != owner:
                ancestor = ancestor.parent
            if ancestor is None:
                return 'invoked alternative must belong to the same menu'
    except (ValueError, KeyError, AttributeError, IndexError):
        return 'unsupported source syntax for unforwarded propagation callback'
    return None


def review_source_guards(manifest, audit, runtime, runtime_path, invoked_actions):
    actions = {a['id']: a for a in manifest.get('behavior', {}).get('actions', [])}
    dispositions = audit.get('actionGuardDispositions', {})
    observations = runtime.get('guardObservations', [])
    if not dispositions and not observations:
        return dict(observations=[], actionIds=[], blockers=[])
    source_root = Path(manifest['app']['sourceRoot']).resolve()
    evidence_root = Path(runtime_path).parent.resolve()
    blockers, accepted = [], []
    if runtime.get('viewport') != dict(width=390, height=844):
        return dict(observations=[], actionIds=[], blockers=['Guard observations require the 390x844 mobile viewport'])

    def fingerprint(item, allowed_root):
        relative = item.get('path')
        if not isinstance(relative, str) or Path(relative).is_absolute():
            return False
        path = (allowed_root / relative).resolve()
        return (path.is_relative_to(allowed_root) and path.is_file()
                and digest(path) == item.get('sha256'))

    for action_id, disposition in dispositions.items():
        action = actions.get(action_id)
        error = None
        alternatives = disposition.get('alternativeSourceActionIds', [])
        if action is None:
            error = 'unknown source action'
        elif (disposition.get('status') != 'reviewed' or not disposition.get('reviewedBy')
              or not disposition.get('reason') or disposition.get('kind') not in
              {'mobile-alternative', 'library-suppressed-trigger', 'library-unforwarded-propagation'}):
            error = 'missing explicit source review'
        elif not fingerprint(disposition.get('sourceEvidence', {}), source_root):
            error = 'source fingerprint changed or missing'
        elif disposition['sourceEvidence']['path'] != action['sourceFile']:
            error = 'source evidence does not own this action'
        elif not alternatives or not all(
            alternative in actions
            and alternative not in dispositions
            and actions[alternative]['sourceFile'] == action['sourceFile']
            and (disposition.get('kind') == 'library-unforwarded-propagation'
                 or set(action.get('handlerFunctionIds', [])) & set(actions[alternative].get('handlerFunctionIds', [])))
            and all((alternative, theme) in invoked_actions for theme in ('light', 'dark'))
            for alternative in alternatives
        ):
            error = 'invoked alternative sharing the same source handler is required in both themes'
        else:
            source = (source_root / action['sourceFile']).read_text()
            expression = disposition.get('sourceGuardExpression')
            if not isinstance(expression, str) or not expression or expression not in source:
                error = 'source guard expression changed or missing'
            elif disposition['kind'] == 'mobile-alternative' and 'isMobile' not in expression:
                error = 'mobile guard must reference the source mobile branch'
            elif disposition['kind'] == 'library-unforwarded-propagation':
                error = _unforwarded_menu(action, alternatives, actions, disposition, source_root, fingerprint)
            elif disposition['kind'] == 'library-suppressed-trigger':
                library = disposition.get('libraryEvidence', {})
                if not fingerprint(library, source_root / 'node_modules'):
                    error = 'library fingerprint changed or missing'
                else:
                    expression = library.get('guardExpression')
                    library_source = (source_root / 'node_modules' / library['path']).read_text()
                    if not isinstance(expression, str) or not expression or expression not in library_source:
                        error = 'library guard expression changed or missing'
        candidates = [o for o in observations if o.get('sourceActionId') == action_id]
        valid = []
        if not error:
            for observation in candidates:
                assertions = observation.get('assertions', [])
                if (observation.get('callbackInvoked') is not False
                    or observation.get('kind') != 'observed-source-guard'
                    or observation.get('passed') is not True
                    or observation.get('themeMode') not in ('light', 'dark')
                    or not assertions
                    or (disposition['kind'] != 'library-unforwarded-propagation'
                        and not all(a.get('state') == 'hidden' and a.get('selector') for a in assertions))
                    or (disposition['kind'] == 'library-unforwarded-propagation'
                        and (not all(a.get('state') == 'visible' and a.get('selector') and a.get('phase') in ('before', 'after') for a in assertions)
                             or {a['phase'] for a in assertions} != {'before', 'after'}
                             or not any(a['phase'] == 'before' and a['selector'] == '[data-testid=\"bottomSheet-header\"]' for a in assertions)))):
                    error = 'explicit passed hidden-state assertions and callbackInvoked=false are required'
                    break
                for side in ('before', 'after'):
                    image = observation.get(side, {})
                    path = (evidence_root / image.get('screenshotPath', '')).resolve()
                    if (not path.is_relative_to(evidence_root) or not path.is_file()
                        or digest(path) != image.get('screenshotSha256')):
                        error = 'guard screenshot is missing or changed'
                        break
                    try:
                        with Image.open(path) as decoded:
                            decoded.load()
                            if decoded.format != 'PNG' or decoded.size != (390, 844):
                                error = 'guard screenshot must be a valid 390x844 PNG'
                    except (OSError, ValueError):
                        error = 'guard screenshot cannot be decoded'
                if error:
                    break
                valid.append(observation)
            if not error and {o['themeMode'] for o in valid} != {'light', 'dark'}:
                error = 'guard observations are required in both themes'
        if error:
            blockers.append(f'Invalid source guard {action_id}: {error}')
        else:
            accepted.extend(dict(o, coverageKind='source-guard') for o in valid)
    for observation in observations:
        if observation.get('sourceActionId') not in dispositions:
            blockers.append('Guard observation lacks an explicit source disposition')
    return dict(observations=accepted,
                actionIds=sorted({o['sourceActionId'] for o in accepted}), blockers=blockers)
