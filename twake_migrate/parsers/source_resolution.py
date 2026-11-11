"""Read static TS/bundler alias definitions without executing application code."""
from pathlib import Path
from .javascript import parse, variable, evaluate, descendants, string, text
from ..core.common import walk, digest


def source_config_hashes(web):
    return {p.relative_to(web).as_posix():digest(p) for p in walk(web,{'.json'}) if p.name.startswith('tsconfig') or p.name in {'package.json','package-lock.json','jsconfig.json'}}


def alias_definitions(web, parsed, overrides=None):
    definitions=[];review=[]
    configs={}
    for file in walk(web,{'.json'}):
        if not (file.name.startswith('tsconfig') or file.name=='jsconfig.json'):continue
        try:configs[file]=evaluate(variable(parse('const config = '+file.read_text()),'config'))
        except ValueError:review.append(dict(kind='source-config',sourceFile=file.relative_to(web).as_posix(),sourceLine=1,reason='Resolve unsupported JSONC/TS config shape'))
    def options(file,seen=None):
        seen=set() if seen is None else seen
        if file in seen:return {}
        seen.add(file);config=configs.get(file,{})
        result={}
        extended=config.get('extends')
        if isinstance(extended,str) and extended.startswith('.'):
            parent=(file.parent/extended).resolve()
            if parent.suffix!='.json':parent=Path(str(parent)+'.json')
            result.update(options(parent,seen))
        opts=config.get('compilerOptions',{})
        base=file.parent/opts.get('baseUrl','.')
        for key,values in opts.get('paths',{}).items():
            result[key]=[str((base/value).resolve()) for value in values]
        return result
    for file in configs:
        definitions.append((file.parent,options(file)))
    for file,root in parsed.items():
        if not any(name in file.name for name in ('config','aliases','Aliases')):continue
        mappings={}
        for node in descendants(root,'pair'):
            if text(node.child_by_field_name('key')).strip("'\"")!='alias':continue
            value=node.child_by_field_name('value')
            if value is None or value.type!='object':continue
            for item in value.named_children:
                if item.type!='pair':
                    if item.type=='spread_element':review.append(dict(kind='bundler-alias-spread',sourceFile=file.relative_to(web).as_posix(),sourceLine=item.start_point.row+1,reason='Inspect dynamic alias factory; provide verified sourceAliases overrides when needed'))
                    continue
                key=text(item.child_by_field_name('key')).strip("'\"")
                target=item.child_by_field_name('value')
                if target.type=='call_expression' and text(target.child_by_field_name('function')) in {'path.resolve','resolve','path.join','join'}:
                    args=target.child_by_field_name('arguments').named_children
                    if args and text(args[0])=='__dirname' and all(a.type=='string' for a in args[1:]):
                        mappings[key]=[str(file.parent.joinpath(*(string(a) for a in args[1:])).resolve())]
                elif target.type=='string':mappings[key]=[str((file.parent/string(target)).resolve())]
        if mappings:definitions.append((file.parent,mappings))
    if overrides:definitions.append((web,{key:[str(Path(value).resolve())] for key,value in overrides.items()}))
    return definitions,review


def module_target(file,specifier,files,definitions,overrides=None):
    bases=[]
    if specifier.startswith('.'):bases.append((file.parent/specifier).resolve())
    if overrides:
        for key,base in sorted(overrides.items(),key=lambda entry:-len(entry[0])):
            if specifier==key or specifier.startswith(key.rstrip('/')+'/'):
                bases.append((Path(base)/specifier[len(key):].lstrip('/')).resolve())
    # Nearest config first; a bundler alias at the same root supersedes its TS alias.
    for root,mappings in sorted(reversed(definitions),key=lambda entry:-len(entry[0].parts)):
        if not file.is_relative_to(root):continue
        for pattern,targets in sorted(mappings.items(),key=lambda entry:-len(entry[0])):
            prefix,_,suffix=pattern.partition('*')
            if '*' in pattern:
                if not specifier.startswith(prefix) or suffix and not specifier.endswith(suffix):continue
                middle=specifier[len(prefix):len(specifier)-len(suffix) if suffix else None]
                bases.extend(Path(target.replace('*',middle)).resolve() for target in targets)
            elif specifier==pattern or specifier.startswith(pattern.rstrip('/')+'/'):
                bases.extend((Path(target)/specifier[len(pattern):].lstrip('/')).resolve() for target in targets)
    for base in bases:
        candidates=[base,*(Path(str(base)+ext) for ext in ('.ts','.tsx','.js','.jsx')),*(base/('index'+ext) for ext in ('.ts','.tsx','.js','.jsx'))]
        found=next((p for p in candidates if p in files),None)
        if found:return found
    return None
