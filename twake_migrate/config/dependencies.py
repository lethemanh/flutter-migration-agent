"""Fetch lockfile-pinned source archives without npm or executing package scripts."""
from pathlib import Path
import base64
import hashlib
import io
import json
import shutil
import tarfile
import tempfile
from urllib.request import urlopen
from urllib.parse import urlparse
from ..core.common import load,write_json


def fetch_design_dependencies(web_root,out_dir):
    web=Path(web_root).resolve()
    out=Path(out_dir).resolve()
    if out==web or out in web.parents: raise ValueError('Dependency cache must not overwrite the web checkout')
    lock=load(web/'package-lock.json')
    names=['@linagora/twake-mui','@linagora/twake-css','@linagora/twake-icons']
    records={name:lock['packages']['node_modules/'+name] for name in names}
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='twake-download-',dir=out) as staging:
        staging=Path(staging)
        for name,record in records.items():
            url=record['resolved']
            if urlparse(url).scheme!='https': raise ValueError('Dependency archive must use HTTPS')
            with urlopen(url,timeout=60) as response:
                if urlparse(response.url).scheme!='https': raise ValueError('Insecure archive redirect')
                archive=response.read(64*1024*1024+1)
            if len(archive)>64*1024*1024: raise ValueError('Dependency archive exceeds 64 MiB')
            hashes=record.get('integrity','').split()
            if not any(h.startswith('sha512-') and base64.b64encode(hashlib.sha512(archive).digest()).decode()==h[7:] for h in hashes): raise ValueError(f'Archive integrity mismatch: {name}')
            package_dir=staging/'node_modules'/name
            package_dir.mkdir(parents=True)
            with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
                total=0
                for member in tar:
                    parts=Path(member.name).parts
                    if not parts or parts[0]!='package' or '..' in parts or member.issym() or member.islnk(): raise ValueError('Unsafe archive member')
                    relative=Path(*parts[1:])
                    target=(package_dir/relative).resolve()
                    if not target.is_relative_to(package_dir.resolve()): raise ValueError('Unsafe archive path')
                    if member.isdir(): target.mkdir(parents=True,exist_ok=True)
                    elif member.isfile():
                        total+=member.size
                        if total>128*1024*1024: raise ValueError('Expanded package exceeds 128 MiB')
                        target.parent.mkdir(parents=True,exist_ok=True)
                        with tar.extractfile(member) as source,target.open('wb') as destination: shutil.copyfileobj(source,destination)
                    else: raise ValueError('Unsupported archive member')
            if load(package_dir/'package.json')['version']!=record['version']: raise ValueError('Archive version differs from lockfile')
        for name in names:
            target=out/'node_modules'/name
            if target.exists(): shutil.rmtree(target)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(staging/'node_modules'/name),target)
    dependencies={name:record['version'] for name,record in records.items()}
    write_json(out/'package.json',dict(private=True,dependencies=dependencies))
    write_json(out/'package-lock.json',dict(name='twake-design-sources',lockfileVersion=3,packages={'':dict(dependencies=dependencies),**{'node_modules/'+name:record for name,record in records.items()}}))
    return dict(dependencyRoot=str(out),versions=dependencies)
