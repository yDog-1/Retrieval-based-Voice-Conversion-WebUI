"""Restore only the verified static bundle from the pymss wheel locked in uv.lock."""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "tools/pymss/server/webui_static"


def verified_payload(wheel, manifest, lock):
    """Validate the complete archive and static subtree before any writes."""
    package = next(p for p in lock["package"] if p["name"] == manifest["package"])
    expected = "sha256:" + manifest["wheel_sha256"]
    if package["version"] != manifest["version"] or not any(
        w["hash"] == expected and w["url"] == manifest["wheel_url"]
        for w in package["wheels"]
    ):
        raise ValueError("Static provenance does not match uv.lock")
    data = wheel.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["wheel_sha256"]:
        raise ValueError("Wheel SHA-256 does not match locked provenance")
    prefix = manifest["subtree"]
    payload = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            name = info.filename.removeprefix(prefix)
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or path.as_posix() != name
                or name in payload
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError(f"Unsafe or duplicate archive path: {name}")
            payload[name] = archive.read(info)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    if hashes != manifest["files"]:
        raise ValueError("Wheel static subtree does not match the complete manifest")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="Local wheel; never downloads or installs code")
    parser.add_argument("--check", action="store_true", help="Compare without writing")
    args = parser.parse_args()
    manifest = json.loads((STATIC / "provenance.json").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    payload = verified_payload(args.wheel, manifest, lock)
    # Resolve every destination before writing, including existing symlinks.
    for name in payload:
        (STATIC / name).resolve().relative_to(STATIC.resolve())
    for name, data in payload.items():
        target = STATIC / name
        if args.check:
            if not target.is_file() or target.read_bytes() != data:
                raise ValueError(f"Missing or different asset: {name}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    print(f"{'Verified' if args.check else 'Restored'} {len(payload)} locked static files")


if __name__ == "__main__":
    main()
