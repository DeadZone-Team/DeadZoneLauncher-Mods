#!/usr/bin/env python3
"""Generate a SHA-256 verified, commit-pinned DeadZone Modpack manifest.

Usage: python3 tools/generate_manifest.py [--revision GIT_SHA]
Only Forge .jar files in repository root are published. The launcher
will only back up an obsolete jar if its SHA-256 matches the legacy list.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OWNER = "DeadZone-Team"
REPO = "DeadZoneLauncher-Mods"

def generate(revision: str) -> dict:
    if not re.fullmatch(r"[a-fA-F0-9]{40}", revision):
        raise ValueError("Expected full 40-character Git commit SHA")
    files = []
    for path in sorted(ROOT.glob("*.jar"), key=lambda p: p.name.lower()):
        with zipfile.ZipFile(path) as jar:
            if jar.testzip() is not None or "META-INF/mods.toml" not in jar.namelist():
                raise ValueError(f"Not a valid Forge jar: {path.name}")
        size = path.stat().st_size
        if not 0 < size <= 300 * 1024 * 1024:
            raise ValueError(f"Unexpected jar size: {path.name}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({
            "path": "mods/" + path.name,
            "size": size,
            "sha256": digest,
            "url": f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{revision}/{quote(path.name, safe='')}",
        })
    if not files:
        raise ValueError("No Forge mods present; refusing to publish empty manifest")
    legacy = json.loads((ROOT / "legacy-obsolete.json").read_text("utf-8"))
    names = {f["path"].casefold() for f in files}
    obsolete = []
    for entry in legacy:
        path, sha = entry["path"], entry["sha256"]
        if (not path.startswith("mods/") or not path.lower().endswith(".jar")
                or not re.fullmatch(r"[a-f0-9]{64}", sha, re.I)):
            raise ValueError("Invalid legacy entry")
        if path.casefold() not in names:
            obsolete.append({"path": path, "sha256": sha})
    return {"schemaVersion": 1, "packVersion": "mods-" + revision[:12],
            "files": files, "obsolete": obsolete}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=None)
    args = parser.parse_args()
    rev = args.revision or subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    manifest = generate(rev)
    out = ROOT / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}: {len(manifest['files'])} mods, "
          f"{len(manifest['obsolete'])} safe legacy removals, revision {rev}")
