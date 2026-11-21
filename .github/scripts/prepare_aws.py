"""Prepare the active Unity export, without stale files from older builds."""
from pathlib import Path
import gzip
import hashlib
import re
import shutil
import sys

source = Path.cwd()
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=False)
html = (source / 'index.html').read_text(encoding='utf-8')
names = re.findall(r'buildUrl \+ "/([^"/]+)"', html)
if not names:
    raise SystemExit('Could not find active Unity build paths in index.html')
files = [Path('index.html')] + [Path('Build') / name for name in names]
for directory in ('TemplateData', 'StreamingAssets'):
    folder = source / directory
    if folder.exists():
        files.extend(path.relative_to(source) for path in folder.rglob('*') if path.is_file())
for relative in files:
    original = source / relative
    if not original.is_file():
        raise SystemExit(f'Missing build asset: {relative}')
    with original.open('rb') as stream:
        if stream.read(80).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise SystemExit(f'Git LFS did not download {relative}')
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, target)
    if target.suffix in ('.data', '.wasm', '.js'):
        with target.open('rb') as stream, gzip.open(str(target) + '.gz', 'wb', compresslevel=5) as compressed:
            shutil.copyfileobj(stream, compressed)
with (output / 'release.sha256').open('w', encoding='utf-8') as manifest:
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name != 'release.sha256':
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            manifest.write(f'{digest.hexdigest()}  {path.relative_to(output).as_posix()}\n')
