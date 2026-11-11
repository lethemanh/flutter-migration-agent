from pathlib import Path
import math
import re
from ..core.common import load, digest
from .javascript import parse, descendants, variable, prop, evaluate, text


def pixels(value):
    match = re.fullmatch(r'(-?[\d.]+)(px|rem)?', str(value).strip())
    if not match: raise ValueError(f'Unsupported dimension: {value}')
    return float(match[1]) * (16 if match[2] == 'rem' else 1)


def read_sources(web_root, dependency_root=None):
    web_root = Path(web_root).resolve()
    dependency_root = Path(dependency_root or web_root).resolve()
    dirs = {n:dependency_root/'node_modules'/'@linagora'/f'twake-{n}' for n in ('mui','css','icons')}
    files = {}
    def read(name, file):
        file = Path(file).resolve()
        if not file.is_file(): raise ValueError(f'Missing resolved design source: {file}')
        files[name] = str(file)
        return file.read_text()
    import json
    packages = {n:json.loads(read(n+'Package', d/'package.json')) for n,d in dirs.items()}
    web_lock = json.loads(read('webLock',web_root/'package-lock.json'))
    dep_lock = json.loads(read('dependencyLock',dependency_root/'package-lock.json'))
    for name,pkg in packages.items():
        key = f'node_modules/@linagora/twake-{name}'
        expected, actual = web_lock.get('packages',{}).get(key,{}), dep_lock.get('packages',{}).get(key,{})
        if not expected.get('integrity') or pkg['version'] != expected.get('version') or actual.get('integrity') != expected['integrity']:
            raise ValueError(f"Resolved {pkg['name']}@{pkg['version']} does not match web lockfile {expected.get('version')}; install locked dependencies or use --dependency-root")
    palette = json.loads(read('palette',dirs['css']/'palette.json'))
    ast = parse(read('typography',dirs['mui']/'dist/lib/makeTypography.js'))
    typography = evaluate(next(descendants(ast,'return_statement')).named_children[0])
    ast = parse(read('semantics',dirs['mui']/'dist/lib/makePalette.js'))
    branches = list(descendants(ast,'if_statement'))
    condition = text(branches[0].child_by_field_name('condition')) if branches else ''
    if not re.fullmatch(r'\(mode\s*===\s*[\'"]dark[\'"]\)',condition):
        raise ValueError('Unsupported makePalette mode branching')
    returns = list(descendants(ast,'return_statement'))
    if len(returns) != 2: raise ValueError('Unsupported makePalette return branches')
    semantics = {mode:evaluate(node.named_children[0], {'palette':palette,'mode':mode}) for mode,node in zip(('dark','light'),returns)}
    radius_raw = evaluate(variable(parse(read('radius',dirs['mui']/'dist/lib/radius.js')), 'radius'))
    theme = evaluate(variable(parse(read('theme',dirs['mui']/'dist/lib/makeTheme.js')), 'themesCommonConfig'))
    css = read('utilities',dirs['css']/'dist/utils.css')
    def utility(selector, field):
        match = re.search(re.escape(selector) + r'\{' + field + r':([^;!}]+)',css)
        if not match: raise ValueError(f'Missing CSS token: {selector}')
        return pixels(match[1])
    spacing = {n:utility(f'.u-stack-{n}>*+*','margin-top') for n in ('xs','s','m','l','xl','xxl')}
    steps = {n:utility(f'.u-p-{n}','padding') for n in ('0','half','1','1-half','2','2-half','3')}
    breakpoints = list(dict.fromkeys(pixels(v) for v in re.findall(r'@media\(max-width:\s*([\d.]+rem)\)',css)))
    if len(breakpoints) != 3: raise ValueError('Unsupported CSS breakpoint scale')
    overrides = parse(read('overrides',dirs['mui']/'dist/lib/overrides.js'))
    def component_slot(component, slot, keys):
        config = next(n.child_by_field_name('value') for n in descendants(overrides,'pair') if text(n.child_by_field_name('key')) == component)
        value = prop(prop(config,'styleOverrides'),slot)
        if value.type == 'arrow_function': value = value.child_by_field_name('body')
        if value.type == 'parenthesized_expression': value = value.named_children[0]
        result = {k:evaluate(prop(value,k),{'radius':radius_raw}) for k in keys}
        result['borderRadius'] = pixels(result['borderRadius'])
        return result
    components = {
        'button':component_slot('MuiButton','root',('borderRadius','minHeight','padding')),
        'input':component_slot('MuiOutlinedInput','root',('borderRadius',)),
        'fabMedium':component_slot('MuiFab','sizeMedium',('borderRadius','width','height')),
    }
    avatar_helpers = read('avatarHelpers',dirs['mui']/'dist/components/Avatar/helpers.js')
    colors_block = re.search(r'export const supportedColors = \[(.*?)\];',avatar_helpers,re.S)
    gradients_block = re.search(r'export const colorMapping = \{(.*?)\n\};',avatar_helpers,re.S)
    if not colors_block or not gradients_block: raise ValueError('Unsupported twake-mui avatar helper source shape')
    avatar_colors = re.findall(r"'([A-Za-z]+)'",colors_block.group(1))
    gradient_rows = re.findall(r"([A-Za-z]+): 'linear-gradient\(([0-9.]+)deg, (#[A-Fa-f0-9]{6}) ([0-9.]+)%, (#[A-Fa-f0-9]{6}) ([0-9.]+)%\)'",gradients_block.group(1))
    avatar_gradients = {name:dict(angle=float(angle),colors=[first,second],stops=[float(a)/100,float(b)/100]) for name,angle,first,a,second,b in gradient_rows}
    if not avatar_colors or set(avatar_colors)!=set(avatar_gradients): raise ValueError('Unsupported or incomplete Twake avatar gradients')
    icon_ast = parse(read('icons',dirs['icons']/'dist/index.js'))
    sprite = evaluate(variable(icon_ast,'icons_sprite_default'))
    return dict(dirs={k:str(v) for k,v in dirs.items()},packages=packages, files=files,palette=palette,typography=typography,semantics=semantics,radius={k:pixels(v) for k,v in radius_raw.items()},shapeDefault=theme['shape']['borderRadius'],spacing=spacing,steps=steps,breakpoints=breakpoints,components=components,sprite=sprite,avatarColors=avatar_colors,avatarGradients=avatar_gradients)


def color(value, alpha=None):
    if isinstance(value,dict): return color(value['color'],value['alpha'])
    value = value.removeprefix('#')
    if len(value) == 3: value = ''.join(c*2 for c in value)
    if not re.fullmatch('[a-fA-F0-9]{6}',value): raise ValueError(f'Unsupported color: {value}')
    a = math.floor((1 if alpha is None else alpha)*255+.5)
    return f'Color(0x{a:02X}{value.upper()})'


def semantic_roles(source):
    def visit(obj,prefix):
        for key,value in obj.items():
            if key in ('mode','grey'): continue
            name = prefix + key[0].upper() + key[1:]
            if isinstance(value,dict) and 'alpha' not in value: yield from visit(value,name)
            else: yield name,value
    for mode in ('light','dark'):
        yield from visit(source['semantics'][mode],mode)


def validate_tokens(ui_root):
    root = Path(ui_root).resolve()
    errors = []
    try:
        lock = load(root/'version-lock.json')
        if lock.get('resolution') != 'web-lockfile-dependencies': raise ValueError('Regenerate from lock-matched web dependencies')
        source = read_sources(lock['webRoot'],lock.get('dependencyRoot'))
        for name,file in source['files'].items():
            if lock.get('sources',{}).get(name) != {'path':file,'sha256':digest(file)}: errors.append(f'Source changed: {name}')
        for name,record in lock.get('sources',{}).items():
            if not Path(record['path']).is_file() or digest(record['path']) != record['sha256']: errors.append(f'Source changed: {name}')
        if not lock.get('outputs'): errors.append('Missing generated output hashes')
        for relative,expected in lock.get('outputs',{}).items():
            file = (root/relative).resolve()
            if not file.is_relative_to(root) or not file.is_file() or digest(file) != expected: errors.append(f'Generated output changed: {relative}')
        def numeric(expr):
            if not expr or not re.fullmatch(r'\s*-?[\d.]+(?:\s*/\s*[\d.]+)?\s*',expr): return float('nan')
            parts = expr.split('/')
            return float(parts[0])/(float(parts[1]) if len(parts)>1 else 1)
        def equal(actual,expected,name):
            if not math.isfinite(actual) or abs(actual-expected)>1e-9: errors.append(f'Token mismatch: {name}: {actual} != {expected}')
        dart = (root/'lib/src/tokens/twake_typography.dart').read_text()
        for name,style in source['typography'].items():
            if name == 'fontFamily': continue
            match = re.search(r'TextStyle '+name+r' = TextStyle\(([\s\S]*?)\);',dart)
            body = match[1] if match else ''
            def field(key):
                m = re.search(key+r':\s*([^,]+)',body)
                return m[1] if m else None
            equal(numeric(field('fontSize')),style['fontSize'],name+'.fontSize')
            weight = re.search(r'w(\d+)',field('fontWeight') or '')
            equal(float(weight[1]) if weight else float('nan'),style['fontWeight'],name+'.fontWeight')
            line = style['lineHeight']
            equal(numeric(field('height')),pixels(line)/style['fontSize'] if isinstance(line,str) else line,name+'.lineHeight')
            equal(numeric(field('letterSpacing')),pixels(style.get('letterSpacing',0)),name+'.letterSpacing')
        radii = {**source['radius'],'shapeDefault':source['shapeDefault'],**{k:source['components'][c]['borderRadius'] for k,c in [('button','button'),('input','input'),('fab','fabMedium')]}}
        spacing = {**source['spacing'],**{k:source['steps'][v] for k,v in {'u0':'0','uHalf':'half','u1':'1','u1Half':'1-half','u2':'2','u2Half':'2-half','u3':'3'}.items()}}
        for file,expected in [('twake_radius.dart',radii),('twake_spacing.dart',spacing)]:
            dart = (root/'lib/src/tokens'/file).read_text()
            for name,value in expected.items():
                match = re.search(r'double '+name+r' = ([^;]+);',dart)
                equal(numeric(match[1] if match else None),value,name)
        dart = (root/'lib/src/tokens/twake_palette.dart').read_text()
        for name,value in semantic_roles(source):
            if isinstance(value,(str,dict)):
                if f'Color {name} = {color(value)};' not in dart: errors.append(f'Token mismatch: {name}')
        theme = (root/'lib/src/theme/twake_theme.dart').read_text()
        height = source['components']['button']['minHeight']
        if not re.search(r'minimumSize: const Size\(64, '+str(height)+r'(?:\.0)?\)',theme): errors.append('Button minimum height mismatch')
    except (ValueError, OSError, KeyError, StopIteration, TypeError) as error:
        errors.append(str(error))
    return {'passed':not errors,'errors':errors}
