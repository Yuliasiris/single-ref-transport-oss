"""Build an immutable local ZIP. No network, credentials or dependency installation."""
from __future__ import annotations
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
NAME = 'single_ref_transport'
FILES = ['single_ref_transport.py', 'README.md', 'SECURITY.md', 'examples/observe.py', 'examples/local_roundtrip.py', 'docs/releasing.md', 'PROVENANCE.md', 'LICENSE']

def package_version() -> str:
    tree = ast.parse((ROOT / "single_ref_transport.py").read_text(encoding="utf-8"))
    version = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "__version__"
                       for target in node.targets))
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("invalid package version")
    return version

def build_bytes() -> tuple[str, bytes]:
    version = package_version()
    contents = {}
    notice = ROOT / "NOTICE"
    for name in FILES + (["NOTICE"] if notice.exists() or notice.is_symlink() else []):
        source = ROOT / name
        parts = Path(name).parts
        if any((ROOT.joinpath(*parts[:i])).is_symlink() for i in range(1, len(parts) + 1)) or not source.is_file():
            raise ValueError(f"not a regular release input: {name}")
        contents[name] = source.read_bytes()
    manifest = {"name": NAME, "version": version, "files": {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(contents.items())}}
    contents["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(contents.items()):
            entry = zipfile.ZipInfo(name, (2026, 9, 21, 0, 0, 0))
            # Fixed explicitly: the default otherwise differs between Windows and Unix.
            entry.create_system = 0
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return version, buffer.getvalue()

def write_once(target: Path, data: bytes) -> None:
    if target.is_symlink():
        raise ValueError("refusing a symlink output")
    if target.exists():
        if target.read_bytes() != data:
            raise FileExistsError("same-version output has different bytes; increment version")
        return
    # Create a complete temp file, then publish without replacing an existing path.
    fd, raw_path = tempfile.mkstemp(prefix=".build-", dir=target.parent)
    temp = Path(raw_path)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != data:
                raise FileExistsError("output changed concurrently; existing bytes retained")
    finally:
        temp.unlink(missing_ok=True)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version, data = build_bytes()
    target = output / f"{NAME}-{version}.zip"
    write_once(target, data)
    print(json.dumps({"path": str(target), "version": version, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()}))

if __name__ == "__main__":
    main()
