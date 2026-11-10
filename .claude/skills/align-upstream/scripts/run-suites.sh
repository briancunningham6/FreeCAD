#!/bin/bash
# Usage: run-suites.sh <FreeCADCmd> <label> <outdir> [elixicad-root]
# Runs the elixifree + ElixiCAD `-m freecad` pytest suites under <FreeCADCmd>.
# Identical for baseline and sync: change only the binary and label.
# Writes <outdir>/<label>-<suite>.txt (full log), -failures.txt, and -v.txt
# (per-test non-passing lines + collection errors, sort -u) for diffing.
set -u
if [ $# -lt 3 ]; then
  echo "usage: $0 <FreeCADCmd> <label> <outdir> [elixicad-root]" >&2; exit 2
fi
BIN="$1"; LABEL="$2"; OUT="$3"
ELIXICAD="${4:-/Users/user/dev/ElixiCAD}"
mkdir -p "$OUT"
PREFIX="$(cd "$(dirname "$BIN")/.." && pwd)"
# Mirror scripts/freecad-worker's dyld setup (FreeCADCmd's rpath is only /usr/local/lib)
DYLD="DYLD_LIBRARY_PATH=$PREFIX/lib:/Users/user/dev/OCCT/install/lib DYLD_FALLBACK_LIBRARY_PATH=${CONDA_PREFIX:-$HOME/miniforge3}/lib:/usr/local/lib:/usr/lib"
CLEAN="env -u FREECAD_PATH -u FREECAD_WORKER_PATH -u FREECAD_WORKER_PY -u MIX_ENV -u DYLD_LIBRARY_PATH -u DYLD_FALLBACK_LIBRARY_PATH $DYLD"

cd /Users/user/dev/FreeCAD
$CLEAN "$BIN" -c "import sys; sys.path.insert(0, '/Users/user/dev/FreeCAD/src/Mod/CadClaude'); import pytest; raise SystemExit(pytest.main(['-v', '-p', 'no:cacheprovider', '--continue-on-collection-errors', '/Users/user/dev/FreeCAD/src/Mod/CadClaude/elixifree/tests/']))" \
  > "$OUT/$LABEL-elixifree.txt" 2>&1
echo "elixifree exit=$?"; tail -1 "$OUT/$LABEL-elixifree.txt"

cd "$ELIXICAD"
$CLEAN "$BIN" -c "import sys; sys.path.insert(0, '$ELIXICAD'); import pytest; raise SystemExit(pytest.main(['-v', '-p', 'no:cacheprovider', '--continue-on-collection-errors', '-m', 'freecad', '--ignore=$ELIXICAD/.claude', '$ELIXICAD']))" \
  > "$OUT/$LABEL-elixicad.txt" 2>&1
echo "elixicad exit=$?"; tail -1 "$OUT/$LABEL-elixicad.txt"

for s in elixifree elixicad; do
  grep -E '^(FAILED|ERROR)' "$OUT/$LABEL-$s.txt" | sed 's/ - .*//' | sort > "$OUT/$LABEL-$s-failures.txt"
  { grep -E '^\S+::\S+.* (FAILED|ERROR)( |$)' "$OUT/$LABEL-$s.txt" | sed -E 's/ (FAILED|ERROR).*/ \1/'; grep -E '^_+ ERROR collecting ' "$OUT/$LABEL-$s.txt" | sed -E 's/^_+ (ERROR collecting [^ ]+) _+$/\1/'; } | sort -u > "$OUT/$LABEL-$s-v.txt"
done
echo "wrote $OUT/$LABEL-{elixifree,elixicad}{,-failures,-v}.txt"
