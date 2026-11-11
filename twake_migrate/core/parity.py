from pathlib import Path
from .common import load, write_json, now, digest, walk
import math
import zlib
import struct


def checked_png(file):
    from PIL import Image
    # Validate every PNG chunk CRC; Pillow's load alone may ignore a bad IDAT CRC.
    data=Path(file).read_bytes()
    if data[:8]!=b'\x89PNG\r\n\x1a\n': raise ValueError('Invalid PNG signature')
    offset=8
    ended=False
    while offset+12<=len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0]
        chunk=data[offset+4:offset+8]
        end=offset+8+size
        if end+4>len(data): raise ValueError('Truncated PNG chunk')
        if zlib.crc32(data[offset+4:end])&0xffffffff != struct.unpack('>I',data[end:end+4])[0]: raise ValueError('Invalid PNG CRC')
        offset=end+4
        if chunk==b'IEND':
            ended=True
            break
    if not ended: raise ValueError('PNG IEND missing')
    with Image.open(file) as image:
        if image.format!='PNG': raise ValueError('Expected PNG')
        if image.size!=(390,844): raise ValueError(f'Expected 390x844 pixels; got {image.width}x{image.height}')
        rgba=image.convert('RGBA')
        background=Image.new('RGBA',image.size,'white')
        return Image.alpha_composite(background,rgba).convert('RGB')


def compare_images(baseline_path,capture_path,threshold=.08):
    from PIL import ImageChops
    if not math.isfinite(threshold) or not 0<=threshold<=1: raise ValueError('Invalid pixel mismatch threshold')
    try:
        baseline,capture=checked_png(baseline_path),checked_png(capture_path)
        delta=ImageChops.difference(baseline,capture)
        mask=None
        for channel in delta.split():
            current=channel.point(lambda value:255 if value>8 else 0)
            mask=current if mask is None else ImageChops.lighter(mask,current)
        different=mask.histogram()[255]
        total=390*844
        ratio=different/total
        return dict(passed=ratio<=threshold,mismatchRatio=ratio,differentPixels=different,totalPixels=total,threshold=threshold,channelTolerance=8,dimensions=dict(width=390,height=844),method='decoded-rgba-pixels')
    except (OSError,ValueError,SyntaxError,struct.error) as error: return dict(passed=False,mismatchRatio=1,reason=f'Missing or invalid PNG: {error}')


def verify_parity(manifest_path,baselines_dir,captures_dir,flow_results_path=None,threshold=.08,out_report_path=None,flutter_root=None):
    manifest=load(manifest_path)
    flow_results=load(flow_results_path) if flow_results_path and Path(flow_results_path).is_file() else {}
    reports=[]
    for screen in manifest['screens']:
        themes={mode:compare_images(Path(baselines_dir)/(screen['id'].lower()+'-'+mode+'.png'),Path(captures_dir)/(screen['id'].lower()+'-'+mode+'.png'),threshold) for mode in ('light','dark')}
        flows=[dict(flowId=f['id'],passed=flow_results.get(f['id'],{}).get('passed') is True) for f in manifest['flows'] if f['screenId']==screen['id']]
        visual=dict(passed=all(r['passed'] for r in themes.values()),themes=themes)
        reports.append(dict(screenId=screen['id'],screenName=screen.get('name',screen['id']),visualDiff=visual,flowsChecked=flows,passed=visual['passed'] and all(f['passed'] for f in flows)))
    inputs = [Path(manifest_path)]
    if flow_results_path: inputs.append(Path(flow_results_path))
    for screen in manifest['screens']:
        for mode in ('light', 'dark'):
            for directory in (baselines_dir, captures_dir):
                inputs.append(Path(directory)/(screen['id'].lower()+'-'+mode+'.png'))
    fingerprints = [dict(path=str(p.resolve()), sha256=digest(p)) for p in inputs if p.is_file()]
    flutter = Path(flutter_root).resolve() if flutter_root else None
    flutter_hashes = {str(p.relative_to(flutter)):digest(p) for p in walk(flutter/'lib', {'.dart'})} if flutter else {}
    report=dict(flutterRoot=str(flutter) if flutter else None,flutterSourceHashes=flutter_hashes,manifestSha256=digest(manifest_path),inputs=fingerprints,schemaVersion='2.0.0',comparison='decoded-rgba-pixels',requiredThemes=['light','dark'],viewport=dict(width=390,height=844),verifiedAt=now(),app=manifest['app']['name'],threshold=threshold,allPassed=bool(reports) and all(r['passed'] for r in reports),screens=reports)
    if out_report_path: write_json(out_report_path,report)
    return report
