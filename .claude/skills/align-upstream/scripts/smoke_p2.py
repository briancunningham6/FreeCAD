"""Protocol-2 smoke: launch freecad-worker the way ElixiHub does.

ElixiHub runs ElixiCAD's worker (FREECAD_WORKER_PY) with ELIXIFREE_PATH set, not
the fork's own worker. Both are derived from --elixicad unless --no-worker-env.

usage: smoke_p2.py <freecad-worker> [--elixicad ROOT] [--no-worker-env] [--expect-git SHA10]
"""
import argparse
import json
import os
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("worker")
ap.add_argument("--elixicad", default="/Users/user/dev/ElixiCAD")
ap.add_argument("--no-worker-env", action="store_true",
                help="do not set FREECAD_WORKER_PY / ELIXIFREE_PATH (fork's own worker)")
ap.add_argument("--expect-git", metavar="SHA10",
                help="fail unless the ENGINE line's runtime.freecad_git equals this")
args = ap.parse_args()

env = {k: v for k, v in os.environ.items()
       if k not in ("FREECAD_PATH", "FREECAD_WORKER_PATH", "FREECAD_WORKER_PY", "MIX_ENV")}
if not args.no_worker_env:
    ws = f"{args.elixicad}/freecad-workspace"
    env.update(FREECAD_WORKER_PY=f"{ws}/cadclaude_worker.py", ELIXIFREE_PATH=ws)

p = subprocess.Popen([args.worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, env=env)

# Read preamble lines (ENGINE, ...) until READY.
engine = None
ready = ""
while True:
    line = p.stdout.readline().decode().rstrip()
    if not line:
        break
    if line.startswith("ENGINE "):
        print("ENGINE line:", line[:300] + ("..." if len(line) > 300 else ""))
        try:
            engine = json.loads(line[len("ENGINE "):])
        except ValueError:
            engine = {}
    elif line.startswith("READY"):
        ready = line
        print("READY line:", line)
        break
    else:
        print("line:", line[:120])

script = (b"import Part, elixifree\n"
          b"b=Part.makeBox(10,10,10).cut(Part.makeCylinder(2,10))\n"
          b"print('VOL', round(b.Volume,6), b.isValid(), elixifree.__file__)\n")
out = []
if ready:
    p.stdin.write(f"{len(script)} job-42\n".encode() + script)
    p.stdin.flush()
    while True:
        l = p.stdout.readline().decode()
        if not l:
            break
        out.append(l.rstrip("\n"))
        if l.startswith(("RESULT_END", "ERROR_END")):
            break
print("\n".join(out))
try:
    p.stdin.write(b"EXIT\n")
    p.stdin.flush()
except OSError:
    pass
p.wait(timeout=30)

ok = bool(ready) and bool(out) and out[0] == "RESULT_START job-42" and out[-1] == "RESULT_END job-42"
if args.expect_git:
    got = ((engine or {}).get("runtime") or {}).get("freecad_git")
    if engine is None:
        print(f"EXPECT-GIT FAIL: no ENGINE line (wanted {args.expect_git})")
        ok = False
    elif got != args.expect_git:
        print(f"EXPECT-GIT FAIL: ENGINE runtime.freecad_git={got!r}, wanted {args.expect_git!r}")
        ok = False
    else:
        print(f"EXPECT-GIT OK: {got}")
print("SMOKE P2:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
