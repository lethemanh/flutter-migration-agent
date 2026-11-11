from pathlib import Path
import json
import math
import re
import shutil
import xml.etree.ElementTree as ET
from ..core.common import flatten, pascal, write_json, digest, now, load
from ..parsers.tokens import read_sources, color, semantic_roles, pixels

HERE = Path(__file__).resolve().parent.parent
TEMPLATES = HERE/'templates'


def _env():
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    return Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined, keep_trailing_newline=True)

def number(value):
    return str(int(value)) if float(value).is_integer() else str(value)

def dart_string(value):
    return "'" + str(value).replace('\\','\\\\').replace("'","\\'").replace('$','\\$').replace('\n','\\n').replace('\r','\\r') + "'"

def collect_locales(web_root, source):
    """Mirror twake-i18n's app-first library extension; fingerprint every input."""
    web_root = Path(web_root)
    app = {}
    def phrases(file, key):
        source['files'][key] = str(file.resolve())
        result = flatten(load(file))
        if not all(isinstance(value, str) for value in result.values()):
            raise ValueError(f'Unsupported non-string translation in {file}')
        return result
    for file in sorted((web_root/'common/src/locales').glob('*.json')):
        app[file.stem] = phrases(file, 'appLocale:'+file.stem)
    roots = [('mui', Path(source['dirs']['mui'])/'dist/components')]
    bar = web_root/'node_modules/@linagora/twake-bar'
    if (bar/'package.json').is_file():
        package = load(bar/'package.json')
        expected = load(web_root/'package-lock.json').get('packages',{}).get('node_modules/@linagora/twake-bar',{})
        if package.get('version') != expected.get('version') or not expected.get('integrity'):
            raise ValueError('Resolved @linagora/twake-bar locale source does not match web lockfile')
        source['files']['barLocalePackage'] = str((bar/'package.json').resolve())
        roots.append(('bar',bar/'dist'))
    libraries = {lang:{} for lang in app}
    for name, root in roots:
        for file in sorted(root.rglob('locales/*.json')):
            lang = file.stem
            if lang not in app: continue
            values = phrases(file, 'libraryLocale:'+name+':'+file.relative_to(root).as_posix())
            effective_app = {**app.get('en',{}), **app[lang]}
            for key,value in values.items():
                if key in effective_app: continue
                if key in libraries[lang] and libraries[lang][key] != value:
                    raise ValueError(f'Conflicting library translation {lang}:{key}; inspect source mount/extension order')
                libraries[lang][key] = value
    # I18n initializes the English app phrases, overlays the selected app
    # language, then useExtendI18n fills missing keys from mounted libraries.
    return {lang:{**libraries[lang], **app.get('en',{}), **values} for lang,values in app.items()}

def generate(web_root, out_dir, dependency_root=None, **_):
    source = read_sources(web_root,dependency_root)
    out = Path(out_dir).resolve()
    if out == Path(web_root).resolve() or out in Path(web_root).resolve().parents:
        raise ValueError('Output must not overwrite the web source root')
    lib = out/'lib'
    def write(relative, content):
        file = out/relative
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(content)
    mui,css,icons = [source['packages'][n]['version'] for n in ('mui','css','icons')]
    header = f'// GENERATED FILE - DO NOT EDIT BY HAND.\n// Source: @linagora/twake-mui ({mui}) & @linagora/twake-css ({css})\n'
    palette = [header,"import 'package:flutter/material.dart';\n",'class TwakePalette {']
    for group,values in source['palette'].items():
        for key,value in values.items():
            name = group[0].lower()+group[1:]+key[0].upper()+key[1:]
            palette.append(f'  static const Color {name} = {color(value)};')
    for name,value in semantic_roles(source):
        if isinstance(value,(str,dict)):
            palette.append(f'  static const Color {name} = {color(value)};')
        elif isinstance(value,(float,int)):
            palette.append(f'  static const double {name} = {number(value)};')
        else: raise ValueError(f'Unsupported semantic value: {name}')
    palette.append('}\n')
    write('lib/src/tokens/twake_palette.dart','\n'.join(palette))
    typo = [header,"import 'package:flutter/material.dart';\n",'class TwakeTypography {',"  static const String fontFamily = 'packages/twake_flutter_ui/Inter';"]
    for name,style in source['typography'].items():
        if name == 'fontFamily': continue
        size,weight = style['fontSize'],style['fontWeight']
        if weight not in range(100,1000,100): raise ValueError(f'Unsupported weight: {weight}')
        height = style['lineHeight']
        if isinstance(height,str): height = pixels(height)/size
        typo.append(f'''  static const TextStyle {name} = TextStyle(
    fontFamily: fontFamily,
    fontSize: {number(size)},
    fontWeight: FontWeight.w{weight},
    height: {number(height)},
    letterSpacing: {number(pixels(style.get('letterSpacing',0)))},
  );''')
    slots = dict(displayLarge='h1',displayMedium='h2',displaySmall='h3',headlineLarge='h3',headlineMedium='h4',headlineSmall='h5',titleLarge='h6',titleMedium='subtitle1',titleSmall='subtitle2',bodyLarge='body1',bodyMedium='body2',bodySmall='caption',labelLarge='button',labelMedium='button',labelSmall='overline')
    typo.append('  static TextTheme toTextTheme(Color primaryTextColor, Color secondaryTextColor) {\n    return TextTheme(')
    for slot,name in slots.items():
        if name not in source['typography']: raise ValueError(f'Missing required typography variant {name}')
        role = 'secondaryTextColor' if slot in ('titleSmall','bodySmall','labelSmall') else 'primaryTextColor'
        typo.append(f'      {slot}: {name}.copyWith(color: {role}),')
    typo.append('    );\n  }\n}\n')
    write('lib/src/tokens/twake_typography.dart','\n'.join(typo))
    radii = {**source['radius'],'shapeDefault':source['shapeDefault'],**{k:source['components'][c]['borderRadius'] for k,c in [('button','button'),('input','input'),('fab','fabMedium')]}}
    radius = [header,"import 'package:flutter/material.dart';",'class TwakeRadius {']
    for key,value in radii.items():
        radius.extend([f'  static const double {key} = {number(value)};', f'  static const BorderRadius border{key[0].upper()+key[1:]} = BorderRadius.all(Radius.circular({key}));'])
    radius.append('}\n')
    write('lib/src/tokens/twake_radius.dart','\n'.join(radius))
    spacing = [header,"import 'package:flutter/material.dart';",'class TwakeSpacing {']
    values = {**source['spacing'],**{k:source['steps'][v] for k,v in {'u0':'0','uHalf':'half','u1':'1','u1Half':'1-half','u2':'2','u2Half':'2-half','u3':'3'}.items()},**dict(zip(('breakpointTiny','breakpointSmall','breakpointMedium'),source['breakpoints']))}
    for key,value in values.items(): spacing.append(f'  static const double {key} = {number(value)};')
    spacing.append('  static double stack(num units) => units * 8.0;')
    for name,expr in dict(p0='EdgeInsets.zero',pHalf='EdgeInsets.all(uHalf)',p1='EdgeInsets.all(u1)',p1Half='EdgeInsets.all(u1Half)',p2='EdgeInsets.all(u2)',ph1='EdgeInsets.symmetric(horizontal: u1)',pv1='EdgeInsets.symmetric(vertical: u1)',mb1='EdgeInsets.only(bottom: u1)',mr1='EdgeInsets.only(right: u1)',mt1='EdgeInsets.only(top: u1)').items():
        spacing.append(f'  static const EdgeInsets {name} = {expr};')
    spacing.append('}\n')
    write('lib/src/tokens/twake_spacing.dart','\n'.join(spacing))
    padding = re.fullmatch(r'(\d+)px (\d+)px',source['components']['button']['padding'])
    if not padding: raise ValueError('Unsupported button padding')
    avatar_gradients = {}
    for name, gradient in source['avatarGradients'].items():
        angle = math.radians(gradient['angle'])
        dx, dy = math.sin(angle), -math.cos(angle)
        avatar_gradients[name] = {**gradient, 'beginX': -dx, 'beginY': -dy, 'endX': dx, 'endY': dy}
    context = dict(mui_version=mui,css_version=css,button_height=source['components']['button']['minHeight'],button_horizontal=padding[2],button_vertical=padding[1],avatar_colors=source['avatarColors'],avatar_gradients=avatar_gradients)
    env = _env()
    for template,target in [('twake_theme.dart','lib/src/theme/twake_theme.dart'),('twake_components.dart','lib/src/components/twake_components.dart'),('twake_contact_popover.dart','lib/src/components/twake_contact_popover.dart'),('twake_mui_compat.dart','lib/src/components/twake_mui_compat.dart'),('twake_utils.dart','lib/src/utils/twake_utils.dart'),('twake_flutter_ui.dart','lib/twake_flutter_ui.dart'),('pubspec.yaml','pubspec.yaml')]:
        write(target,env.get_template(template).render(**context))
    for directory in ('assets/icons/ui','assets/icons/illus','lib/src/l10n'):
        if (out/directory).exists(): shutil.rmtree(out/directory)
        (out/directory).mkdir(parents=True)
    ET.register_namespace('xlink','http://www.w3.org/1999/xlink')
    svg = ET.fromstring(source['sprite'].replace('<svg>', '<svg xmlns:xlink="http://www.w3.org/1999/xlink">',1))
    defs = next((n for n in svg if n.tag == 'defs'),None)
    entries = []
    for symbol in svg.iter('symbol'):
        name = symbol.attrib['id']
        if not re.fullmatch(r'[\w-]+',name): raise ValueError('Unsupported icon ID')
        attrs = {'xmlns':'http://www.w3.org/2000/svg'}
        if 'viewBox' in symbol.attrib: attrs['viewBox'] = symbol.attrib['viewBox']
        element = ET.Element('svg',attrs)
        if defs is not None: element.append(defs)
        for child in symbol: element.append(child)
        category = 'illus' if name.startswith('illus-') else 'ui'
        asset = f'assets/icons/{category}/{name}.svg'
        write(asset,ET.tostring(element,encoding='unicode'))
        entries.append((pascal(name),asset))
    if not entries: raise ValueError('No installed SVG symbols')
    icon_lines = [header,'// ignore_for_file: constant_identifier_names',f'// Source: @linagora/twake-icons ({icons})',"import 'package:flutter/material.dart';","import 'package:flutter_svg/flutter_svg.dart';",'class TwakeIconData {\n  final String name;\n  final String assetPath;\n  const TwakeIconData(this.name, this.assetPath);\n}', 'class TwakeIcons {']
    seen = set()
    for name,asset in entries:
        if name in seen: raise ValueError(f'Duplicate icon symbol name: {name}')
        seen.add(name)
        icon_lines.append(f"  static const TwakeIconData {name} = TwakeIconData('{name}', 'packages/twake_flutter_ui/{asset}');")
    icon_lines.extend(['}', '''class TwakeIcon extends StatelessWidget {
  final TwakeIconData icon;
  final double size;
  final Color? color;
  const TwakeIcon({super.key, required this.icon, this.size = 24, this.color});
  @override
  Widget build(BuildContext context) => Semantics(label: icon.name,
    child: SizedBox(width: size, height: size, child: SvgPicture.asset(
      icon.assetPath, width: size, height: size,
      colorFilter: icon.assetPath.contains('/illus/') ? null : ColorFilter.mode(
        color ?? IconTheme.of(context).color ?? Theme.of(context).colorScheme.onSurface, BlendMode.srcIn),
    )));
}
'''])
    write('lib/src/icons/twake_icons.dart','\n'.join(icon_lines))
    locales = collect_locales(web_root, source)
    for locale, items in locales.items():
        write_json(out/f'lib/src/l10n/app_{locale}.arb',{'@@locale':locale,**{re.sub(r'[^a-zA-Z0-9_]','_',k):v for k,v in items.items()}})
    i18n = ['// GENERATED FILE - DO NOT EDIT BY HAND.','// Source: twake-i18n locales/*.json','class TwakeI18n {',f"  static const List<String> supportedLocales = [{', '.join(map(dart_string,locales))}];","  static String locale = 'en';",'  static const Map<String, Map<String, String>> _translations = {']
    for locale,items in locales.items():
        i18n.append(f'    {dart_string(locale)}: {{')
        i18n.extend(f'      {dart_string(k)}: {dart_string(v)},' for k,v in items.items())
        i18n.append('    },')
    i18n.extend(['  };', '''  static String t(String key, [Map<String, dynamic>? params]) {
    var value = _translations[locale.split(RegExp('[-_]')).first]?[key] ?? _translations['en']?[key] ?? key;
    if (params != null) {
      params.forEach((k, v) {
        value = value.replaceAll('{{$k}}', v.toString()).replaceAll('%{$k}', v.toString());
      });
    }
    return value;
  }
}
'''])
    write('lib/src/l10n/twake_i18n.dart','\n'.join(i18n))
    font = Path(web_root)/'public/fonts/InterVariable.ttf'
    if not font.is_file(): font = HERE/'assets/Inter.ttf'
    source['files']['font'] = str(font.resolve())
    (out/'assets/fonts').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(font,out/'assets/fonts/Inter.ttf')
    shutil.copyfile(HERE/'assets/OFL.txt',out/'assets/fonts/OFL.txt')
    versions = dict(twakeMui=mui,twakeCss=css,twakeIcons=icons)
    widget_map = load(TEMPLATES/'widget-map.json')
    widget_map['sourceVersions'] = versions
    write_json(out/'widget-map.json',widget_map)
    snapshot = {k:source[k] for k in ('typography','semantics','radius','shapeDefault','spacing','steps','components')}
    write_json(out/'design-tokens.json',snapshot)
    outputs = {str(file.relative_to(out)):digest(file) for folder in (lib,out/'assets') for file in sorted(folder.rglob('*')) if file.is_file()}
    for name in ('pubspec.yaml','design-tokens.json'): outputs[name] = digest(out/name)
    write_json(out/'version-lock.json',dict(generatedAt=now(),generator='python',webRoot=str(Path(web_root).resolve()),dependencyRoot=str(Path(dependency_root or web_root).resolve()),resolution='web-lockfile-dependencies',versions=versions,sources={k:dict(path=v,sha256=digest(v)) for k,v in source['files'].items()},outputs=outputs,iconsExported=len(entries),localesExported=list(locales)))
    return dict(outDir=str(out),widgetMapPath=str(out/'widget-map.json'),versionLockPath=str(out/'version-lock.json'),iconsCount=len(entries),localesCount=len(locales))
