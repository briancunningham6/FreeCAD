# Building the ElixiCad FreeCAD Fork

This guide covers building the `briancunningham6/FreeCAD` fork and connecting it
to cadClaude's persistent worker pool.

---

## Overview

The cadClaude-specific additions to this fork are **pure Python** — no C++ changes
are required for the worker pool itself. As of the 2026-08 upstream sync, upstream
FreeCAD `main` ships **official OCCT 7/8 support** (the "Make common between OCCT 7
and 8" campaign), so this fork no longer carries a bespoke OCCT-RC patch set the way
`OCCT_RC_PATCH_NOTES.md` originally documented — see that file's historical banner
for background. What remains in `src/Mod/Part/App` after the sync is small:

- **11 residual patches** that survived the upstream merge as auto-merge conflict
  resolutions (extra explicit includes, nested-iterator-style loops, an
  `NCollection_Map` adjustment in `UnifySameDomainPyImp.cpp`, and a `parent._cache`
  fix in `TopoShapeCache.cpp`) — not new RC-compatibility work, just carryover from
  reconciling the fork's history with upstream's.
- **One rc4-only guard fix** (commit `f7605d21`) in `OpenCascadeAll.h`,
  `Geometry2d.cpp`, and `Geom2d/Curve2dPyImp.cpp` for the custom
  OCCT 8.0.0-rc4 build this fork targets — see
  [Step 3, Build the Part module first](#3-build-the-part-module-first) below.

**Fork synced to upstream `d648b7b5ae` (2026-08-04).**

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
cadClaude build, but will not include the residual patches described in
[Overview](#overview) (which target this fork's specific custom OCCT 8.0.0-rc4
build).

**Runtime library path:** the installed `Part.so` (and other Part-dependent
modules) link against this custom OCCT via `@rpath`, but their `LC_RPATH` is
hardcoded to `/usr/local/lib` (upstream's build convention), which doesn't exist on
this machine. Invoking `bin/freecad-worker` from the install prefix handles this
automatically — it auto-detects the OCCT lib dir (or honors an `OCCT_LIB_DIR`
environment override) and adds it to `DYLD_LIBRARY_PATH`. If you invoke
`MacOS/FreeCADCmd` **directly**, bypassing the `freecad-worker` wrapper, you must
add `/Users/user/dev/OCCT/install/lib` to `DYLD_LIBRARY_PATH` yourself, or `import
Part` will fail with `Library not loaded: @rpath/libTKFillet.8.0.dylib`.

### System dependencies (macOS, Homebrew)

The existing build uses these Homebrew-provided paths — they must be present:

```bash
brew install cmake ninja python@3.11 pybind11 boost eigen xerces-c icu4c
```

FreeCAD also needs Qt6 + PySide6. The existing build has `BUILD_GUI=OFF`, so the GUI
Qt components are not required for headless cadClaude use — **but as of the 2026-08
sync, a headless configure still needs the full `qt` metaformula, not just
`qtbase`:**

```bash
brew install qt
```

Upstream commit `6a259f948a` moved Qt translation setup into `src/App/CMakeLists.txt`
so it now runs unconditionally, even with `BUILD_GUI=OFF`, which means the
`LinguistTools` Qt component (`lupdate`/`lrelease`) is required for *any* configure,
headless or not. `LinguistTools` is only shipped by the full `qt` formula — the
`qtbase` formula this project otherwise relies on does not include it. Do not
"clean up" the `qt` dependency in favor of `qtbase` alone; configure will fail with
`Unknown CMake command "qt6_add_translation"` if you do. (The fork's own
`cMake/FreeCAD_Helpers/SetupQt.cmake` now requests `LinguistTools` unconditionally —
see commit `b4e99de1` — so no extra CMake flag is needed to make this work; you only
need the Homebrew package present.)

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

This is the configuration that produced the working build after the 2026-08 upstream
sync (fork synced to upstream `d648b7b5ae`). It targets headless use (no GUI) and
uses the custom OCCT. The FEM pipeline drives gmsh and ccx directly from Python —
FreeCAD's FEM/Mesh modules are not needed and must be kept OFF:

```bash
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  -DENABLE_DEVELOPER_TESTS=OFF \
  -DBUILD_GUI=OFF \
  -DBUILD_FEM=OFF \
  -DBUILD_MESH=OFF \
  -DBUILD_MESH_PART=OFF \
  -DBUILD_FLAT_MESH=OFF \
  -DBUILD_MEASURE=OFF \
  -DBUILD_ASSEMBLY=OFF \
  -DBUILD_CAM=OFF \
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
  -DMEDFILE_INCLUDE_DIRS=/opt/homebrew/Cellar/med-file@5.0.0_py313/5.0.0_1/include \
  -DMEDFILE_LIBRARIES=/opt/homebrew/Cellar/med-file@5.0.0_py313/5.0.0_1/lib/libmed.dylib \
  -DOCC_INCLUDE_DIR=/Users/user/dev/OCCT/install/include/opencascade \
  -DOCC_LIBRARY_DIR=/Users/user/dev/OCCT/install/lib \
  -DOCCT_CMAKE_FALLBACK=ON \
  -DCMAKE_PREFIX_PATH="/opt/homebrew/opt/icu4c@78;/opt/homebrew/opt/pybind11;/opt/homebrew/opt/xerces-c;/opt/homebrew/opt/boost;/opt/homebrew/opt/eigen;/opt/homebrew/opt/qt"
```

> `ENABLE_DEVELOPER_TESTS=OFF` — defaults to `ON` upstream and, when `ON`, forces
> `find_package(GTest REQUIRED)`. GoogleTest isn't part of this headless toolchain and
> installing it just for an unused test suite isn't worth the weight — keep this OFF,
> consistent with only building Part + Sketcher + PartDesign + Material.
>
> `BUILD_FEM=OFF` / `BUILD_MESH=OFF` / `BUILD_MESH_PART=OFF` / `BUILD_FLAT_MESH=OFF` — the
> cadClaude FEM pipeline drives gmsh and ccx directly from Python; FreeCAD's FEM/Mesh
> C++ modules are not used. Keeping them ON causes `cmake --install` to fail: FEM
> forces Mesh and MeshPart ON as dependencies, but those modules require GUI libraries
> that are unavailable in a headless build, so their `.so` files are never produced.
>
> `BUILD_MEASURE=OFF` — the Measure module has a C++ extension (`Measure.so`) that is
> not built in a headless configuration. Leaving it ON causes `cmake --install` to fail.
>
> `BUILD_IMPORT=OFF` — the Import module has OCCT compatibility issues against this
> fork's custom OCCT build and is not needed by cadClaude (STEP export uses
> `shape.exportStep()` directly from Part).
>
> `CMAKE_OSX_SYSROOT` — must point to the stable MacOSX15.x SDK, not the beta.
> The beta SDK (`MacOSX26.x`) is missing `libz.tbd`, causing linker failures in
> FreeCADBase. Use `xcodebuild -showsdks` to list available SDKs and pick the
> highest stable `macosx15.x` entry.
>
> `BUILD_ASSEMBLY=OFF` — requires `BUILD_SPREADSHEET=ON`; neither needed for cadClaude.
>
> `BUILD_CAM=OFF` — requires a C++ extension header (`CXX/Extensions.hxx`) not
> available without the full CAM toolchain.
>
> `BUILD_MATERIAL=ON` — must be kept ON; it is a hard dependency of `BUILD_PART`.
> Always pass it explicitly: if it ever ends up OFF in the CMake cache and you
> reconfigure without specifying it, the configure step will abort.
>
> `OCCT_CMAKE_FALLBACK=ON` — required as of the 2026-08 sync. `cMake/FindOCC.cmake`
> now tries `find_package(OpenCASCADE CONFIG QUIET)` *before* honoring the explicit
> `OCC_INCLUDE_DIR`/`OCC_LIBRARY_DIR` flags above. If any other OCCT config happens to
> be discoverable on this machine's ambient CMake search paths (e.g. a conda-forge
> OCCT via miniforge), it will silently win and configure will report a version other
> than the custom `/Users/user/dev/OCCT/install` build with no error — check the
> configure log's `Found OpenCASCADE version:` line if in doubt. This flag skips that
> `find_package` shortcut entirely and forces the manual `OCC_INCLUDE_DIR`/
> `OCC_LIBRARY_DIR` path to be honored.
>
> `/opt/homebrew/opt/qt` in `CMAKE_PREFIX_PATH` — needed so `find_package(Qt6
> COMPONENTS LinguistTools)` can find `Qt6LinguistToolsConfig.cmake`, which lives
> under the full `qt` formula's prefix, not `qtbase`'s. See
> [System dependencies](#system-dependencies) above — `brew install qt` is required.
>
> To use the standard Homebrew OCCT instead, omit the `OCC_*` flags (and
> `OCCT_CMAKE_FALLBACK`, which only matters for the manual-path override) and add
> `-DCMAKE_PREFIX_PATH=/opt/homebrew` (or the conda prefix if using pixi).

### 3. Build the Part module first

The residual OCCT-compat code (see [Overview](#overview) above — 11 small
auto-merged patches plus the rc4-only guard fix) is concentrated in `Part`. Verify
it compiles cleanly before the full build:

```bash
cmake --build build --target Part --parallel
```

If this produces `OCC_VERSION_HEX >= 0x080000`-related errors (missing
`LProp_CurveUtils.hxx`, unknown `GeomLProp_CLProps2d`, etc.), you are most likely
building against an OCCT 8.0.0 **pre-release** (rc4 or similar) rather than a final
8.0.0 — see commit `f7605d21` and `OCCT_RC_PATCH_NOTES.md`'s historical banner for
the fix pattern (guarding the `OCC_VERSION_HEX >= 0x080000` branches with
`&& !defined(OCC_VERSION_DEVELOPMENT)`, which self-corrects once you build against a
true final 8.0.0 release).

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

`freecad-worker` auto-detects and adds the custom OCCT lib dir to
`DYLD_LIBRARY_PATH` for you (see [Custom OCCT](#custom-occt) above) — no extra
configuration needed in the common case. If your OCCT install lives somewhere
other than the auto-detected candidates, set `OCCT_LIB_DIR` explicitly:

```bash
export OCCT_LIB_DIR=/path/to/your/OCCT/install/lib
```

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

The FEM pipeline does **not** use FreeCAD's FEM/ccxtools stack. `ccxtools` requires
PySide (GUI) which is unavailable in headless builds. Instead, the pipeline drives
gmsh and CalculiX directly from plain Python.

### CalculiX solver (`ccx`)

The FEM analysis script calls `ccx` as a subprocess. Install it system-wide:

```bash
# macOS (not in Homebrew core — use the freecad tap)
brew tap freecad/freecad
brew install freecad/freecad/calculix@2.23

# Ubuntu / Raspberry Pi worker
sudo apt-get install -y calculix-ccx
```

Verify: `ccx --version` should print the CalculiX version string.

### Gmsh mesher (Python package)

The FEM script runs inside the FreeCAD worker. FreeCAD's embedded Python version
**depends on which build you're using**:

- The older dev build at `build/bin/FreeCADCmd` embeds **CPython 3.11.0** from
  `/Library/Frameworks/Python.framework/Versions/3.11` (a python.org-style
  framework install).
- **As of the 2026-08 upstream sync, a fresh build embeds CPython 3.13.5** via
  Homebrew (`/opt/homebrew/opt/python@3.13/Frameworks/Python.framework/Versions/3.13`,
  resolved through `/opt/homebrew/Cellar/python@3.13/3.13.5`) — a different
  interpreter build from a different distribution channel, not just a patch bump.
  **Operators: confirm which interpreter your install actually embeds** (check
  `otool -L MacOS/FreeCADCmd | grep Python`) before assuming pip packages installed
  for 3.11 are available. Regression testing for the sync only diff-checked
  pass/fail status of existing tests, not deeper 3.11-vs-3.13 stdlib-behavior
  differences (e.g. `datetime`, `tomllib`/`typing` changes) — watch for edge cases
  in production.

Install gmsh into whichever embedded interpreter your build uses, e.g. for the
2026-08-sync build:

```bash
/opt/homebrew/opt/python@3.13/bin/python3 -m pip install gmsh
```

or for the older 3.11 dev build:

```bash
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 -m pip install gmsh
```

Verify inside a FreeCAD worker session:

```python
import gmsh
print("gmsh:", gmsh.__version__)
```

### FEM render Python (pyvista + vtk)

The render script runs as a separate subprocess using `RENDER_PYTHON_PATH` (set in
`.env`). The deploy install script sets this to the pixi conda Python and installs
pyvista into it. vtk must be < 9.4 — vtk 9.5+ segfaults with the pyvista 0.43.x
offscreen renderer on macOS arm64.

```bash
# The install.sh handles this automatically via pixi Python:
$INSTALL_DIR/runtime-env/.pixi/envs/default/bin/python3 -m pip install \
  "vtk>=9.3,<9.4" "pyvista>=0.43,<0.44" numpy

# For the dev machine (miniforge3):
/Users/user/miniforge3/bin/python3 -m pip install "vtk>=9.3,<9.4" "pyvista>=0.43,<0.44" numpy
```

Verify:

```bash
python3 -c "import pyvista; print('pyvista:', pyvista.__version__)"
# pyvista: 0.43.x
```

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

**Fork synced to upstream `d648b7b5ae` (2026-08-04).** That sync merged (rather than
rebased) ~1,700 upstream commits, including upstream's official OCCT 7/8 support,
which superseded this fork's old bespoke OCCT-RC patch set (see
[Overview](#overview) and `OCCT_RC_PATCH_NOTES.md`'s historical banner). Future
syncs should diff the configure flags and `Part` residual patches against what's
documented here — both drifted materially between the fork's previous sync and this
one, and are likely to drift again.

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
