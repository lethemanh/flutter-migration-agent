from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent.parent.parent
GROUPS = ('routes', 'screens', 'components', 'flows', 'apiCalls')
HELPERS = {'useBreakpoints','useTheme','styled','alpha','darken','lighten','createTheme','VirtualizedTableColumn','VirtualizedTableRow','SelectChangeEvent'}

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def load(file):
    return json.loads(Path(file).read_text())

def write_json(file, value):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def digest(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()

def snake(value):
    return re.sub(r'[^a-zA-Z0-9]+', '_', re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', value)).strip('_').upper()

def pascal(value):
    return re.sub(r'(^\w|[-_]\w)', lambda m: m[0].strip('-_').upper(), value)

def flatten(value, prefix=''):
    result = {}
    for key, item in value.items():
        name = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            result.update(flatten(item, name))
        else:
            result[name] = item
    return result

def walk(root, extensions):
    import os
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {'node_modules','dist','.git','coverage','build','.venv','__pycache__','.dart_tool'})
        for name in sorted(files):
            file = Path(directory) / name
            if file.suffix in extensions:
                yield file


def discovery_fingerprint(manifest):
    """Scope fingerprint unaffected by human approval metadata."""
    content={key:value for key,value in manifest.items() if key!='approval'}
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
