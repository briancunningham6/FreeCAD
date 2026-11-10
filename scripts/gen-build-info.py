#!/usr/bin/env python3
"""Generate BUILD-INFO.json (schema 1) for the FreeCAD fork.

Stdlib only. Never fails the build: any error yields a manifest with an
"error" key and exit status 0.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA = 1
DIRTY_CAP = 50
SYNC_RE = re.compile(r"^Merge upstream FreeCAD main ([0-9a-f]{7,40})")


def _git(srcdir, *args):
    """Run git in srcdir; return stripped stdout, or None on any failure."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=srcdir, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def git_facts(srcdir):
    facts = {"git": None, "describe": None, "branch": None, "dirty": None,
             "dirty_paths": []}
    sha = _git(srcdir, "rev-parse", "HEAD")
    if not sha:
        return facts
    facts["git"] = sha
    facts["describe"] = _git(srcdir, "describe", "--tags", "--always") or None
    facts["branch"] = _git(srcdir, "symbolic-ref", "--short", "-q", "HEAD") or None
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=srcdir, capture_output=True, text=True, timeout=10, check=False,
        )
        if r.returncode == 0:
            paths = [ln[3:] for ln in r.stdout.splitlines() if ln.strip()]
            facts["dirty"] = bool(paths)
            facts["dirty_paths"] = paths[:DIRTY_CAP]
    except (OSError, subprocess.SubprocessError):
        pass
    return facts


def _to_utc_z(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upstream_base(srcdir):
    none = {"base": None, "base_date": None}
    out = _git(srcdir, "log", "--merges",
               "--format=%H%x00%P%x00%s")
    if not out:
        return none
    for line in out.splitlines():
        parts = line.split("\0")
        if len(parts) != 3 or not SYNC_RE.match(parts[2]):
            continue
        parents = parts[1].split()
        if len(parents) < 2:
            continue
        base = parents[1]
        date = _git(srcdir, "show", "-s", "--format=%cI", base)
        try:
            date = _to_utc_z(date) if date else None
        except ValueError:
            date = None
        return {"base": base, "base_date": date}
    return none


def build_manifest(facts, srcdir, now):
    return {
        "schema": SCHEMA,
        "built_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fork": git_facts(srcdir),
        "upstream": upstream_base(srcdir),
        "versions": facts.get("versions", {}),
        "toolchain": facts.get("toolchain", {}),
        "options": facts.get("options", {}),
    }


def _comparable(m):
    return {k: v for k, v in m.items() if k != "built_at"}


def write_if_changed(manifest, path):
    try:
        with open(path, encoding="utf-8") as f:
            if _comparable(json.load(f)) == _comparable(manifest):
                return False
    except (OSError, ValueError):
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--srcdir", required=True)
    ap.add_argument("--facts", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        with open(args.facts, encoding="utf-8") as f:
            facts = json.load(f)
        manifest = build_manifest(facts, args.srcdir, datetime.now(timezone.utc))
    except Exception as e:  # never fail the build
        manifest = {"schema": SCHEMA, "error": str(e)}
    try:
        changed = write_if_changed(manifest, args.out)
        print("BUILD-INFO.json: updated" if changed else "BUILD-INFO.json: unchanged")
    except Exception as e:
        print(f"BUILD-INFO.json: error writing manifest: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
