"""Package the complete original experiment workspace with per-file checksums."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    paths=[]
    for directory in ("runs","live","results","graphs","assets","puzzler","tools","tests"):
        for p in (source/directory).rglob("*"):
            if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts and p.suffix not in (".pyc",".pid"):
                paths.append(p)
    paths.extend(source/name for name in ("README.md","THIRD_PARTY.lock"))
    # This archive contains experimental data, not authentication or machine state.
    token = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)")
    manifest={"scope":"Original experimental workspace, including all run trajectories, native recordings, RPC traces and frozen protocols. Byte-for-byte original files; no downloaded full reference video, caches, credentials or virtual environments.","files":{}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(args.out,"w:gz",compresslevel=4) as archive:
        for i,p in enumerate(sorted(set(paths))):
            content=p.read_bytes()
            if token.search(content):
                raise RuntimeError(f"Credential-like content detected; refusing archive: {p.relative_to(source)}")
            name=p.relative_to(source).as_posix()
            manifest["files"][name]={"size":len(content),"sha256":hashlib.sha256(content).hexdigest()}
            info=archive.gettarinfo(str(p),arcname=name)
            info.uid=info.gid=0;info.uname=info.gname="";info.mtime=0
            archive.addfile(info,io.BytesIO(content))
            if i and i%10000==0:
                print(f"Archived {i} files",flush=True)
        content=(json.dumps(manifest,indent=2)+"\n").encode()
        info=tarfile.TarInfo("evidence-manifest.json");info.size=len(content)
        archive.addfile(info,io.BytesIO(content))
    checksum=hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(args.out.suffix+".sha256").write_text(f"{checksum}  {args.out.name}\n")
    print(json.dumps({"archive":str(args.out),"files":len(paths),"bytes":args.out.stat().st_size,"sha256":checksum},indent=2),flush=True)


if __name__=="__main__":
    main()
