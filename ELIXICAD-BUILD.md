# Building the ElixiCad FreeCAD Fork

This guide covers building the `briancunningham6/FreeCAD` fork and connecting it
to cadClaude's persistent worker pool.

---

## Overview

The cadClaude-specific additions to this fork are **pure Python** — no C++ changes
are required for the worker pool itself. The only C++ work in this fork is the OCCT
RC compatibility patches (documented in `OCCT_RC_PATCH_NOTES.md`), which are needed
to build against the custom OCCT at `/Users/user/dev/OCCT/install`.

This means:

- **If you have an existing build**, you can install the new Python files without
  recompiling anything.
- **If you are doing a fresh build**, follow the full steps below.

---

## Prerequisites

### Custom OCCT

This fork builds against a custom (unreleased RC) OpenCASCADE at:

```
/Users/user/dev/OCCT/install
```

The standard `occt >= 7.8` from Homebrew or conda will also work for a headless
cadClaude build, but will not include the OCCT RC patches.

### System dependencies (macOS, Homebrew)

The existing build uses these Homebrew-provided paths — they must be present:

```bash
brew install cmake ninja python@3.11 pybind11 boost eigen xerces-c icu4c
```

FreeCAD also needs Qt6 + PySide6. The existing build has `BUILD_GUI=OFF`, so Qt
is not required for headless cadClaude use.

---

## Quick path: install without recompiling

The worker pool additions (`cadclaude_worker.py`, `freecad-worker`) are pure Python
and shell. If you already have a working build in `build/`, just run the install:

```bash
cd /Users/user/dev/FreeCAD

# Install to a local prefix (avoids sudo, keeps /usr/local clean)
cmake --install build/ --prefix ~/freecad-cadclaude

# Verify the new files landed
ls ~/freecad-cadclaude/bin/freecad-worker
ls ~/freecad-cadclaude/Mod/CadClaude/cadclaude_worker.py
```

Then skip ahead to [Connecting to cadClaude](#connecting-to-cadclaude).

---

## Full build from scratch

### 1. Clone and initialise submodules

```bash
git clone https://github.com/briancunningham6/FreeCAD.git ~/dev/FreeCAD
cd ~/dev/FreeCAD
git submodule update --init --recursive
```

### 2. Configure

This is the configuration that produced the working build at `build/`.
It targets headless use (no GUI) and uses the custom OCCT. FEM is enabled
for structural analysis via `ObjectsFem`, `femtools.ccxtools`, and
`femmesh.gmshtools`:

```bash
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  -DBUILD_GUI=OFF \
  -DBUILD_FEM=ON \
  -DBUILD_ROBOT=OFF \
  -DBUILD_ARCH=OFF \
  -DBUILD_BIM=OFF \
  -DBUILD_DRAFT=OFF \
  -DBUILD_SHIP=OFF \
  -DBUILD_PATH=OFF \
  -DBUILD_TECHDRAW=OFF \
  -DBUILD_SURFACE=OFF \
  -DBUILD_POINTS=OFF \
  -DBUILD_INSPECTION=OFF \
  -DBUILD_REVERSEENGINEERING=OFF \
  -DBUILD_OPENSCAD=OFF \
  -DBUILD_SPREADSHEET=OFF \
  -DBUILD_IMPORT=OFF \
  -DBUILD_MATERIAL=ON \
  -DOCC_INCLUDE_DIR=/Users/user/dev/OCCT/install/include/opencascade \
  -DOCC_LIBRARY_DIR=/Users/user/dev/OCCT/install/lib \
  -DCMAKE_PREFIX_PATH="/opt/homebrew/opt/icu4c@78;/opt/homebrew/opt/pybind11;/opt/homebrew/opt/xerces-c;/opt/homebrew/opt/boost;/opt/homebrew/opt/eigen"
```

> `BUILD_IMPORT=OFF` — the Import module has OCCT RC compatibility issues and is
> not needed by cadClaude (STEP export uses `shape.exportStep()` directly from Part).
>
> `CMAKE_OSX_SYSROOT` — must point to the stable MacOSX15.x SDK, not the beta.
> The beta SDK (`MacOSX26.x`) is missing `libz.tbd`, causing linker failures in
> SMESH and FreeCADBase. Use `xcodebuild -showsdks` to list available SDKs and
> pick the highest stable `macosx15.x` entry.
>
> `BUILD_MATERIAL=ON` — must be kept ON; it is a hard dependency of `BUILD_PART`.
> Always pass it explicitly: if it ever ends up OFF in the CMake cache and you
> reconfigure without specifying it, the configure step will abort.
>
> To use the standard Homebrew OCCT instead, omit the `OCC_*` flags and add
> `-DCMAKE_PREFIX_PATH=/opt/homebrew` (or the conda prefix if using pixi).

### 3. Build the Part module first

The OCCT RC patches are concentrated in `Part`. Verify it compiles cleanly
before the full build:

```bash
cmake --build build --target Part --parallel
```

If this produces errors, refer to `OCCT_RC_PATCH_NOTES.md` for the fix pattern.

### 4. Full build

```bash
cmake --build build --parallel
```

### 5. Install

Install to a local prefix so sudo is not required and `/usr/local` is not
polluted:

```bash
cmake --install build --prefix ~/freecad-cadclaude
```

The install layout will be:

```
~/freecad-cadclaude/
  bin/
    FreeCADCmd          ← headless FreeCAD binary
    freecad-worker      ← ElixiCad launcher script  (from scripts/)
  Mod/
    CadClaude/
      cadclaude_worker.py
      Init.py
      InitGui.py
    Part/
      ...
```

---

## Connecting to cadClaude

### Option A — using the installed prefix (recommended)

Set a single environment variable pointing to the launcher script:

```bash
export FREECAD_WORKER_PATH=~/freecad-cadclaude/bin/freecad-worker
```

Add this to your shell's `~/.zshrc` or to `elixicad/.env` so it is always set.

Then start ElixiCad normally:

```bash
cd /Users/user/dev/cadClaude/elixicad
FREECAD_WORKER_PATH=~/freecad-cadclaude/bin/freecad-worker mix phx.server
```

On startup you should see two log lines confirming the pool is warm:

```
[info] FreeCAD worker ready (OS PID 12345)
[info] FreeCAD worker ready (OS PID 12346)
```

### Option B — dev workflow, no install required

Point directly at the build directory and source tree — no `cmake --install` needed:

```bash
export FREECAD_PATH=/Users/user/dev/FreeCAD/build/bin/FreeCADCmd
export FREECAD_WORKER_PY=/Users/user/dev/FreeCAD/src/Mod/CadClaude/cadclaude_worker.py
export FREECAD_WORKER_PATH=/Users/user/dev/FreeCAD/scripts/freecad-worker
```

The `freecad-worker` script honours all three env vars, so changes to
`cadclaude_worker.py` are picked up immediately without reinstalling.

### elixicad/.env

Create `elixicad/.env` (already gitignored by Phoenix) with whichever option
you chose:

```bash
# Option A
FREECAD_WORKER_PATH=/Users/user/freecad-cadclaude/bin/freecad-worker

# Option B (dev, no install)
# FREECAD_WORKER_PATH=/Users/user/dev/FreeCAD/scripts/freecad-worker
# FREECAD_PATH=/Users/user/dev/FreeCAD/build/bin/FreeCADCmd
# FREECAD_WORKER_PY=/Users/user/dev/FreeCAD/src/Mod/CadClaude/cadclaude_worker.py
```

---

## FEM dependencies

FEM execution requires two external tools beyond the FreeCAD build itself.

### CalculiX solver

`femtools.ccxtools` shells out to the `ccx` binary. Install it before running
any FEM analysis:

```bash
# macOS
brew install calculix

# Ubuntu / Raspberry Pi worker
sudo apt-get install -y calculix-ccx
```

Verify: `ccx --version` should print the CalculiX version string.

### Gmsh mesher

`femmesh.gmshtools` calls the `gmsh` Python package. Install it into the Python
environment that FreeCAD uses:

```bash
# Using the installed prefix
~/freecad-cadclaude/bin/python3 -m pip install gmsh

# Using the build directory (Option B dev workflow)
/opt/homebrew/bin/python3.11 -m pip install gmsh
```

### Verify FEM modules load

```python
import ObjectsFem
import FreeCAD
from femtools import ccxtools
from femmesh import gmshtools
print("FEM workbench OK")
```

Run this inside a FreeCAD worker session or via `FreeCADCmd` to confirm all
FEM imports succeed before attempting a full analysis run.

---

## Verification

### 1. Test the worker manually

```bash
# Start the worker in one terminal
FREECAD_PATH=/Users/user/dev/FreeCAD/build/bin/FreeCADCmd \
FREECAD_WORKER_PY=/Users/user/dev/FreeCAD/src/Mod/CadClaude/cadclaude_worker.py \
  /Users/user/dev/FreeCAD/scripts/freecad-worker

# You should see:
# READY
```

Then type a script request (length + newline + script bytes):

```
53
import FreeCAD; print("version:", FreeCAD.Version()[0])
```

Expected response:

```
RESULT_START
version: 1
RESULT_END
```

### 2. Test via ElixiCad

```bash
cd /Users/user/dev/cadClaude/elixicad
mix phx.server
```

Trigger a model generation through the UI or API. The lifecycle event log should
show `"Starting FreeCAD execution (pooled)"` and `duration_ms` well under 1000ms
for simple shapes (vs 5000–10000ms previously).

---

## Keeping the fork up to date

```bash
cd /Users/user/dev/FreeCAD
git fetch upstream
git rebase upstream/main
git push origin main
```

After rebasing, rebuild and reinstall only if C++ files changed:

```bash
cmake --build build --parallel
cmake --install build --prefix ~/freecad-cadclaude
```

If only Python files in `src/Mod/CadClaude/` changed, you can skip the build
and just re-run the install step.
