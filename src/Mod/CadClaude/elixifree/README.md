# ElixiFree

A declarative Python library for generating CAD geometry inside FreeCAD.

Instead of writing 50-line FreeCAD API scripts, you write 5-line builder expressions:

```python
# Before ElixiFree
import FreeCAD, Part
from FreeCAD import Vector
doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Model")
wall = Part.makeBox(4000, 122, 2440)
groove_l = Part.makeBox(45, 50, 2440, Vector(0, 11, 0))
groove_r = Part.makeBox(45, 50, 2440, Vector(3955, 11, 0))
wall = wall.cut(groove_l).cut(groove_r)
door_void = Part.makeBox(900, 122, 2100, Vector(1550, 0, 0))
wall = wall.cut(door_void)
feature = doc.addObject("Part::Feature", "Body")
feature.Shape = wall
doc.recompute()

# With ElixiFree
from elixifree.domains.sip import Wall
result = (Wall(span=4000, height=2440, stock="SIP-100")
    .opening(x=1550, z=0, width=900, height=2100)
    .build())
result.add_to_doc("Body")
```

---

## Architecture

ElixiFree has two layers:

### Core layer (`elixifree`)

Domain-agnostic geometry primitives over FreeCAD's `Part` module. All functions return `Part.Shape`.

```python
from elixifree import box, cylinder, cut, fuse, translate, mirror, fillet, chamfer, add_to_doc
```

### Domain layer (`elixifree.domains.*`)

Construction-domain builders that encode domain knowledge (stock tables, groove dimensions, interface conventions) and expose a fluent API. Each builder returns a `BuildResult`.

```python
from elixifree.domains.sip import Wall, RoofPanel, Foundation, sip_constants
```

### Gap logging

When a builder cannot express a geometry detail declaratively, it records a gap:

```python
# ElixiFree gap: pitched roof panels not yet supported declaratively
```

Gaps are collected in `BuildResult.gaps` and surfaced in the ElixiCAD Lab UI for future library development.

---

## Installation

ElixiFree runs inside FreeCAD's embedded Python interpreter. It does not require a separate install step — place the `elixifree/` directory on `sys.path`.

For the ElixiCAD worker, files are deployed to:
```
/Users/user/freecad-cadclaude/Mod/CadClaude/elixifree/
```

### Why no FreeCAD rebuild is needed

ElixiFree is pure Python. It sits entirely above the FreeCAD binary:

```
FreeCAD binary  (custom build — never touched by ElixiFree changes)
  └── Python interpreter  (embedded in the binary)
        └── Part module  (C extension compiled into the binary)
              └── elixifree/  (plain .py files on disk ← what we edit)
                    ├── __init__.py
                    ├── builder.py
                    └── domains/sip.py
```

ElixiFree calls standard FreeCAD Part API (`Part.makeBox`, `shape.cut`, etc.) — stable APIs that have been unchanged for years. It never touches the compiled layer beneath them.

**Updating ElixiFree is just a file copy:**

```bash
cp elixifree/domains/sip.py /path/to/worker/elixifree/domains/sip.py
rm -rf /path/to/worker/elixifree/__pycache__   # clear stale bytecode
```

Python reimports the updated `.py` file on the next worker execution. No FreeCAD restart, no compile step, no build toolchain required.

**The one hard constraint:** ElixiFree can only call FreeCAD APIs that already exist in the binary. Adding new geometry operations or fixing OCCT bugs requires a FreeCAD rebuild. Adding new builders, domain modules, or utility functions in ElixiFree never does.

---

## Quick Start

### Generic CAD

```python
from elixifree import box, cut, add_to_doc

# Open-top box: 500×300×200mm, 5mm walls
outer = box(500, 300, 200)
inner = box(490, 290, 200, at=(5, 5, 5))
result = cut(outer, inner)
add_to_doc(result, "Body")
```

### SIP building components

```python
from elixifree.domains.sip import Wall, RoofPanel, Foundation, sip_constants

# Wall with a door, spanning along Y axis (east/west orientation)
result = (Wall(span=3000, height=2440, stock="SIP-100")
    .orient("Y")
    .opening(x=1050, z=0, width=900, height=2100)
    .corner_spline(side="left")
    .corner_spline(side="right")
    .build())
result.add_to_doc("Body")

# Look up stock dimensions without hardcoding
c = sip_constants("SIP-100")
# c["face"]=11, c["core"]=100, c["total"]=122
```

---

## SIP stock values

| Name    | Face (OSB) | Core (EPS) | Total |
|---------|-----------|------------|-------|
| SIP-100 | 11mm      | 100mm      | 122mm |
| SIP-150 | 11mm      | 150mm      | 172mm |
| SIP-200 | 11mm      | 200mm      | 222mm |
| SIP-250 | 11mm      | 250mm      | 272mm |
| SIP-300 | 11mm      | 300mm      | 322mm |

---

## Wall builder reference

| Method | Description |
|--------|-------------|
| `Wall(span, height, stock)` | Create a wall. Default stock: SIP-200. |
| `.opening(x, z, width, height)` | Cut a door or window void. x from left edge, z from bottom. |
| `.orient("Y")` | Rotate so span runs along Y (east/west walls). Default: X. |
| `.corner_spline(side)` | Add a protruding 45mm spline at `"left"` or `"right"` edge. |
| `.inner_groove(x, width=45, depth=50)` | Cut a spline receiver groove on the inner face (Y=0). |
| `.build()` | Build and return a `BuildResult`. |

---

## Adding a new domain

1. Create `elixifree/domains/<domain>.py`
2. Subclass `ComponentBuilder` for each component type
3. Implement `_validate()`, `_build_geometry()`, `_params()`
4. Export from `elixifree/domains/__init__.py`
5. Add tests in `elixifree/tests/test_domains_<domain>.py`

See [elixifree/domains/sip.py](domains/sip.py) for a complete example.

---

## Running tests

Tests run under FreeCAD's Python interpreter:

```bash
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD \
  -c "import sys; sys.path.insert(0, 'src/Mod/CadClaude'); \
      import pytest; raise SystemExit(pytest.main(['-v', 'src/Mod/CadClaude/elixifree/tests/']))"
```

The `builder` tests (`test_builder.py`) can also run under standard Python since they do not import FreeCAD.

---

## File structure

```
elixifree/
├── __init__.py          Core geometry primitives (box, cut, fuse, …)
├── builder.py           BuildResult, BuildError, ComponentBuilder base class
├── sip.py               Low-level SIP constructability functions (panel, groove, …)
├── domains/
│   ├── __init__.py
│   └── sip.py           Design-stage SIP builders (Wall, RoofPanel, Foundation)
├── tests/
│   ├── conftest.py      Shared sys.path setup
│   ├── test_builder.py  BuildResult / BuildError / ComponentBuilder
│   ├── test_core.py     Core primitives
│   └── test_domains_sip.py  SIP domain builders
├── README.md            This file
└── CHANGELOG.md         Version history
```

---

## Design principles

1. **Declarative over imperative** — builders accept parameters, not geometry instructions
2. **No document state in builders** — all geometry is returned as `Part.Shape`; document management is the caller's responsibility
3. **Fail loudly on invalid parameters** — `BuildError` is raised early so scripts fail at the builder call, not deep in OCCT
4. **Gap logging over silent omission** — when geometry can't be expressed declaratively, log it with `_log_gap()` so the gap is visible and trackable
5. **Design intent, not construction detail** — builders produce design-stage solids; panel splits, plates, and splines belong in the constructability layer
