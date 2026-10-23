"""Package visual inputs, failures and source snapshots with a SHA-256 manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]


def build(destination):
    files=set()
    directories=[*sorted((ROOT/'runs').glob('vision*')),
                 *sorted((ROOT/'graphs').glob('vision*')),
                 ROOT/'dist/vision-scattered',ROOT/'dist/vision-scattered-final',
                 ROOT/'tests/fixtures']
    for directory in directories:
        for path in directory.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                files.add(path)
    for pattern in ['puzzler/*.py','tools/*vision*.py','tests/test_vision_contract.py',
                    'results/vision*','results/VISION.md','results/OBSERVATION_AUDIT.md',
                    'results/paper_sources.json','RUNTIME.lock','requirements-cpu.lock',
                    '.gitmodules','README.md']:
        files.update(p for p in ROOT.glob(pattern) if p.is_file())
    records=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,
                  sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(files)]
    manifest=ROOT/'dist/vision-evidence-manifest.json'
    manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps(dict(
        scope='RGB prototype development evidence, including failed and superseded attempts. '
              'Subset diagnostics are not complete assembly successes. '
              'See results/VISION.md and each run source snapshot for its input boundary.',
        files=records),indent=2)+'\n')
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(destination,'w:gz',compresslevel=6) as archive:
        archive.add(manifest,arcname='manifest.json')
        for path in sorted(files):archive.add(path,arcname=path.relative_to(ROOT).as_posix())
    # Check every payload against the manifest after writing the archive.
    with tarfile.open(destination,'r:gz') as archive:
        for record in records:
            payload=archive.extractfile(record['path']).read()
            assert hashlib.sha256(payload).hexdigest()==record['sha256'],record['path']
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix+'.sha256').write_text(f'{digest}  {destination.name}\n')
    print(json.dumps(dict(archive=str(destination),files=len(records),bytes=destination.stat().st_size,
                         sha256=digest)))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('destination')
    build(parser.parse_args().destination)
